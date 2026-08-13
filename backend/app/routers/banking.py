"""Enable Banking HTTP surface.

Endpoints under ``/api/banking``:

- ``GET  /aspsps`` — banks available for linking.
- ``POST /connections`` — start the redirect-based bank authorization.
- ``POST /connections/callback`` — complete it: create session, connection,
  accounts, and run the first sync.
- ``GET  /connections`` / ``DELETE /connections/{id}`` — list / unlink.
- ``POST /sync`` — manual global sync run (quota-guarded).
- ``GET  /sync/status`` — quota + scheduling info for the UI.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.models import Account, BankAuthRequest, BankConnection, SyncRun
from app.schemas.banking import (
    AspspResponse,
    BankConnectionResponse,
    CallbackRequest,
    CallbackResponse,
    ConnectionSyncResult,
    ConnectRequest,
    ConnectResponse,
    GlobalSyncResponse,
    SkippedAccount,
    SyncStatusResponse,
)
from app.services.bank_amount import NonEurCurrencyError, ensure_eur, is_unknown_currency
from app.services.bank_sync import SyncSummary, run_global_sync, select_balance, sync_connection
from app.services.banking_client import BankingClient, BankingError, get_banking_client
from app.services.encryption import decrypt, encrypt
from app.services.sync_quota import latest_run, quota_remaining, runs_today
from app.services.sync_scheduler import auto_sync_interval

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/banking", tags=["banking"])

BankingDep = Annotated[BankingClient, Depends(get_banking_client)]

# Anti-mash guard on top of the daily quota: reject a manual sync if the
# previous run finished less than this ago.
SYNC_COOLDOWN = timedelta(seconds=30)
# A started-but-never-completed bank authorization is invalid after this.
AUTH_REQUEST_TTL = timedelta(hours=1)


def _map_banking_error(exc: BankingError) -> HTTPException:
    if exc.code == "BANKING_NOT_CONFIGURED":
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={"error_code": exc.code, "message": str(exc)},
    )


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _summary_to_result(summary: SyncSummary, connection: BankConnection) -> ConnectionSyncResult:
    return ConnectionSyncResult(
        connection_id=connection.id,
        aspsp_name=connection.aspsp_name,
        added=summary.added,
        modified=summary.modified,
        skipped_pending=summary.skipped_pending,
        skipped_non_eur=summary.skipped_non_eur,
        skipped_unknown_account=summary.skipped_unknown_account,
        skipped_unparseable_date=summary.skipped_unparseable_date,
        skipped_deleted=summary.skipped_deleted,
        error_code=summary.error_code,
        touched_account_ids=summary.touched_account_ids,
    )


async def _sync_status(db: AsyncSession) -> SyncStatusResponse:
    settings = get_settings()
    used = await runs_today(db)
    last = await latest_run(db)
    next_auto: datetime | None = None
    if settings.sync_mode == "auto" and last is not None:
        next_auto = _as_utc(last.started_at) + auto_sync_interval(settings)
    return SyncStatusResponse(
        mode=settings.sync_mode,
        max_per_day=settings.sync_max_per_day,
        used_today=used,
        remaining_today=max(settings.sync_max_per_day - used, 0),
        last_run_at=last.started_at if last else None,
        next_auto_sync_at=next_auto,
    )


@router.get("/aspsps", response_model=list[AspspResponse])
async def list_aspsps(
    current_user: CurrentUser,
    banking: BankingDep,
) -> list[AspspResponse]:
    settings = get_settings()
    try:
        aspsps = await banking.list_aspsps(settings.banking_countries_list)
    except BankingError as exc:
        raise _map_banking_error(exc) from exc
    return [
        AspspResponse(name=a["name"], country=a["country"], logo=a.get("logo"))
        for a in aspsps
    ]


@router.post("/connections", response_model=ConnectResponse, status_code=status.HTTP_201_CREATED)
async def start_connection(
    payload: ConnectRequest,
    db: DbSession,
    current_user: CurrentUser,
    banking: BankingDep,
) -> ConnectResponse:
    settings = get_settings()
    if not settings.enable_banking_redirect_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ENABLE_BANKING_REDIRECT_URL is not configured.",
        )
    state = uuid.uuid4().hex
    try:
        authorization_url = await banking.start_auth(
            payload.aspsp_name,
            payload.aspsp_country.upper(),
            state,
            settings.enable_banking_redirect_url,
        )
    except BankingError as exc:
        raise _map_banking_error(exc) from exc

    db.add(
        BankAuthRequest(
            user_id=current_user.id,
            state=state,
            aspsp_name=payload.aspsp_name,
            aspsp_country=payload.aspsp_country.upper(),
            scope=payload.scope,
        )
    )
    await db.commit()
    return ConnectResponse(authorization_url=authorization_url, state=state)


def _parse_valid_until(session: dict[str, Any]) -> datetime | None:
    raw = (session.get("access") or {}).get("valid_until")
    if not raw:
        return None
    try:
        return _as_utc(datetime.fromisoformat(str(raw).replace("Z", "+00:00")))
    except ValueError:
        return None


def _account_display_name(raw: dict[str, Any], aspsp_name: str) -> str:
    return raw.get("name") or raw.get("product") or aspsp_name


@router.post(
    "/connections/callback",
    response_model=CallbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def complete_connection(
    payload: CallbackRequest,
    db: DbSession,
    current_user: CurrentUser,
    banking: BankingDep,
) -> CallbackResponse:
    auth_request = (
        await db.execute(
            select(BankAuthRequest).where(BankAuthRequest.state == payload.state)
        )
    ).scalar_one_or_none()
    if auth_request is None or auth_request.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown or foreign authorization state.",
        )
    if datetime.now(timezone.utc) - _as_utc(auth_request.created_at) > AUTH_REQUEST_TTL:
        await db.delete(auth_request)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authorization expired. Start the bank connection again.",
        )

    try:
        session = await banking.create_session(payload.code)
    except BankingError as exc:
        raise _map_banking_error(exc) from exc

    raw_accounts: list[dict[str, Any]] = session.get("accounts") or []
    eur_accounts: list[dict[str, Any]] = []
    skipped: list[SkippedAccount] = []
    for raw in raw_accounts:
        currency = raw.get("currency")
        try:
            ensure_eur(currency)
        except NonEurCurrencyError:
            reason = f"currency {currency!r} is not EUR"
            balance_currency: str | None = None
            # Enable Banking's account-list currency can't always be trusted for
            # multi-currency wallets (e.g. PayPal reports "XXX", ISO 4217's
            # "no currency" sentinel, at this endpoint even when its balance
            # is EUR). When the signal is unknown rather than a confident
            # non-EUR value, check the balance before giving up on the account.
            if is_unknown_currency(currency):
                uid = raw.get("uid")
                if uid:
                    try:
                        balances = await banking.get_balances(uid)
                    except BankingError as exc:
                        balances = []
                        # Temporary diagnostic: surfaces why the balance fallback
                        # didn't confirm EUR, so a real fix can be scoped precisely
                        # instead of guessed at.
                        logger.warning(
                            "Enable Banking balance fallback failed: aspsp=%r uid=%r error=%r",
                            auth_request.aspsp_name,
                            uid,
                            exc,
                        )
                    else:
                        logger.warning(
                            "Enable Banking balance fallback: aspsp=%r uid=%r balances=%r",
                            auth_request.aspsp_name,
                            uid,
                            [
                                {
                                    "balance_type": b.get("balance_type"),
                                    "currency": (b.get("balance_amount") or {}).get("currency"),
                                }
                                for b in balances
                            ],
                        )
                    balance = select_balance(balances)
                    if balance is not None:
                        balance_currency = (balance.get("balance_amount") or {}).get("currency")
                        try:
                            ensure_eur(balance_currency)
                        except NonEurCurrencyError:
                            pass
                        else:
                            eur_accounts.append(raw)
                            continue
                reason = f"{reason} (balance check found {balance_currency!r})"
            logger.warning(
                "Enable Banking account rejected: aspsp=%r uid=%r currency=%r "
                "balance_currency=%r product=%r",
                auth_request.aspsp_name,
                raw.get("uid"),
                currency,
                balance_currency,
                raw.get("product"),
            )
            skipped.append(
                SkippedAccount(
                    name=_account_display_name(raw, auth_request.aspsp_name),
                    reason=reason,
                )
            )
            continue
        eur_accounts.append(raw)

    if not eur_accounts:
        # No usable accounts — revoke the session so the orphaned consent
        # doesn't linger, and reject with a clear error.
        session_id = session.get("session_id")
        if session_id:
            try:
                await banking.delete_session(session_id)
            except BankingError:
                pass
        await db.delete(auth_request)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No EUR-denominated accounts found at this bank. ZeroBudget is EUR-only.",
        )

    connection = BankConnection(
        user_id=current_user.id,
        session_id_encrypted=encrypt(session["session_id"]),
        aspsp_name=auth_request.aspsp_name,
        aspsp_country=auth_request.aspsp_country,
        valid_until=_parse_valid_until(session),
    )
    db.add(connection)
    await db.flush()

    created_accounts: list[Account] = []
    for raw in eur_accounts:
        iban = (raw.get("account_id") or {}).get("iban")
        acc = Account(
            user_id=current_user.id,
            name=_account_display_name(raw, auth_request.aspsp_name),
            type="checking",
            scope=auth_request.scope,
            bank_connection_id=connection.id,
            bank_account_uid=raw.get("uid"),
            bank_account_mask=iban[-4:] if iban else None,
            bank_product_name=raw.get("product"),
        )
        db.add(acc)
        created_accounts.append(acc)
    await db.delete(auth_request)
    await db.flush()

    # First sync costs API calls, so it's recorded as a quota-counted run —
    # but linking is a deliberate one-time action, never blocked by quota.
    run = SyncRun(
        started_at=datetime.now(timezone.utc),
        trigger=SyncRun.TRIGGER_LINK,
        status=SyncRun.STATUS_OK,
    )
    db.add(run)
    try:
        summary = await sync_connection(db, connection, banking)
    except BankingError as exc:
        await db.rollback()
        raise _map_banking_error(exc) from exc
    run.added = summary.added
    run.modified = summary.modified

    await db.commit()
    await db.refresh(connection)

    return CallbackResponse(
        connection=BankConnectionResponse.model_validate(connection),
        account_ids=[a.id for a in created_accounts],
        skipped_accounts=skipped,
        sync=_summary_to_result(summary, connection),
    )


@router.post("/sync", response_model=GlobalSyncResponse)
async def sync_now(
    db: DbSession,
    current_user: CurrentUser,
    banking: BankingDep,
) -> GlobalSyncResponse:
    settings = get_settings()

    remaining = await quota_remaining(db, settings)
    if remaining <= 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Daily sync limit of {settings.sync_max_per_day} reached. "
                "The quota resets at midnight UTC."
            ),
        )
    last = await latest_run(db)
    if last is not None and datetime.now(timezone.utc) - _as_utc(last.started_at) < SYNC_COOLDOWN:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Sync was run less than {SYNC_COOLDOWN.seconds}s ago. Try again shortly.",
        )

    run, summaries = await run_global_sync(db, banking, SyncRun.TRIGGER_MANUAL, settings)
    await db.commit()

    own_connections = (
        (
            await db.execute(
                select(BankConnection)
                .where(BankConnection.user_id == current_user.id)
                .order_by(BankConnection.id)
            )
        )
        .scalars()
        .all()
    )
    results = [
        _summary_to_result(summaries[c.id], c) for c in own_connections if c.id in summaries
    ]
    return GlobalSyncResponse(
        status=run.status,
        connections=results,
        quota=await _sync_status(db),
    )


@router.get("/sync/status", response_model=SyncStatusResponse)
async def sync_status(
    db: DbSession,
    current_user: CurrentUser,
) -> SyncStatusResponse:
    return await _sync_status(db)


@router.get("/connections", response_model=list[BankConnectionResponse])
async def list_connections(
    db: DbSession,
    current_user: CurrentUser,
) -> list[BankConnectionResponse]:
    rows = (
        (
            await db.execute(
                select(BankConnection)
                .where(BankConnection.user_id == current_user.id)
                .order_by(BankConnection.id)
            )
        )
        .scalars()
        .all()
    )
    return [BankConnectionResponse.model_validate(r) for r in rows]


@router.delete("/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_connection(
    connection_id: int,
    db: DbSession,
    current_user: CurrentUser,
    banking: BankingDep,
) -> None:
    connection = await db.get(BankConnection, connection_id)
    if connection is None or connection.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Bank connection not found"
        )

    try:
        session_id = decrypt(connection.session_id_encrypted)
        await banking.delete_session(session_id)
    except Exception:
        # Provider-side revoke may fail (e.g. session already expired, or the
        # encryption key rotated); we still want to drop local rows so the
        # user isn't stuck.
        pass

    await db.delete(connection)
    await db.commit()
