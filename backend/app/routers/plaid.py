"""Plaid Link + /transactions/sync HTTP surface.

Four endpoints:

- ``POST /api/plaid/link-token`` — bootstrap Plaid Link in the browser.
- ``POST /api/plaid/exchange`` — exchange public_token, create Item + EUR
  Accounts, run the first sync.
- ``POST /api/plaid/items/{id}/sync`` — manual re-sync (rate-limited).
- ``DELETE /api/plaid/items/{id}`` — unlink + cascade delete.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import CurrentUser, DbSession
from app.models import Account, PlaidItem
from app.schemas.plaid import (
    ExchangeRequest,
    ExchangeResponse,
    LinkTokenResponse,
    PlaidItemResponse,
    SkippedAccount,
    SyncResponse,
)
from app.services.encryption import encrypt
from app.services.plaid_amount import NonEurCurrencyError, ensure_eur
from app.services.plaid_client import PlaidClient, PlaidError, get_plaid_client
from app.services.plaid_sync import SyncSummary, sync_item

router = APIRouter(prefix="/api/plaid", tags=["plaid"])

PlaidDep = Annotated[PlaidClient, Depends(get_plaid_client)]

# Rate limit: reject manual sync if the previous one finished less than this
# ago. Keeps free-tier Plaid quota safe from button-mashing.
SYNC_RATE_LIMIT = timedelta(seconds=30)


def _map_plaid_error(exc: PlaidError) -> HTTPException:
    if exc.code == "PLAID_NOT_CONFIGURED":
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail={"error_code": exc.code, "message": str(exc)},
    )


async def _get_owned_item(db: AsyncSession, user_id: int, item_id: int) -> PlaidItem:
    item = await db.get(PlaidItem, item_id)
    if item is None or item.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plaid item not found")
    return item


def _map_account_type(plaid_type: str | None, plaid_subtype: str | None) -> str:
    if plaid_type == "depository":
        if plaid_subtype in {"savings", "cd", "money market"}:
            return "savings"
        return "checking"
    if plaid_type == "credit":
        return "credit"
    if plaid_type == "loan":
        return "loan"
    return plaid_subtype or plaid_type or "checking"


def _summary_to_response(summary: SyncSummary, item: PlaidItem) -> SyncResponse:
    return SyncResponse(
        added=summary.added,
        modified=summary.modified,
        removed=summary.removed,
        skipped_pending=summary.skipped_pending,
        skipped_non_eur=summary.skipped_non_eur,
        skipped_unknown_account=summary.skipped_unknown_account,
        last_synced_at=item.last_synced_at,
        error_code=summary.error_code,
        touched_account_ids=summary.touched_account_ids,
    )


@router.post("/link-token", response_model=LinkTokenResponse)
async def create_link_token(
    current_user: CurrentUser,
    plaid: PlaidDep,
) -> LinkTokenResponse:
    try:
        token = await plaid.create_link_token(current_user.id)
    except PlaidError as exc:
        raise _map_plaid_error(exc) from exc
    return LinkTokenResponse(link_token=token)


@router.post("/exchange", response_model=ExchangeResponse, status_code=status.HTTP_201_CREATED)
async def exchange_public_token(
    payload: ExchangeRequest,
    db: DbSession,
    current_user: CurrentUser,
    plaid: PlaidDep,
) -> ExchangeResponse:
    try:
        exchange = await plaid.exchange_public_token(payload.public_token)
        plaid_accounts = await plaid.get_accounts(exchange.access_token)
        institution_name = await plaid.get_institution_name(exchange.access_token)
    except PlaidError as exc:
        raise _map_plaid_error(exc) from exc

    eur_accounts: list[dict[str, Any]] = []
    skipped: list[SkippedAccount] = []
    for pa in plaid_accounts:
        balances = pa.get("balances") or {}
        try:
            ensure_eur(
                balances.get("iso_currency_code"),
                balances.get("unofficial_currency_code"),
            )
        except NonEurCurrencyError:
            skipped.append(
                SkippedAccount(
                    plaid_account_id=pa["account_id"],
                    name=pa.get("name") or pa.get("official_name") or "",
                    reason=(
                        f"currency {balances.get('unofficial_currency_code') or balances.get('iso_currency_code')!r}"
                        " is not EUR"
                    ),
                )
            )
            continue
        eur_accounts.append(pa)

    if not eur_accounts:
        # No usable accounts — remove the Item from Plaid so the orphaned
        # access token doesn't linger, and reject with a clear error.
        try:
            await plaid.remove_item(exchange.access_token)
        except PlaidError:
            pass
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No EUR-denominated accounts found on this item. ZeroBudget is EUR-only.",
        )

    item = PlaidItem(
        user_id=current_user.id,
        plaid_item_id=exchange.item_id,
        access_token_encrypted=encrypt(exchange.access_token),
        institution_name=institution_name,
    )
    db.add(item)
    await db.flush()

    created_accounts: list[Account] = []
    for pa in eur_accounts:
        acc = Account(
            user_id=current_user.id,
            name=pa.get("name") or pa.get("official_name") or "Account",
            type=_map_account_type(pa.get("type"), pa.get("subtype")),
            plaid_item_id=item.id,
            plaid_account_id=pa["account_id"],
            plaid_mask=pa.get("mask"),
            plaid_official_name=pa.get("official_name"),
        )
        db.add(acc)
        created_accounts.append(acc)
    await db.flush()

    try:
        summary = await sync_item(db, item, plaid)
    except PlaidError as exc:
        await db.rollback()
        raise _map_plaid_error(exc) from exc

    await db.commit()
    await db.refresh(item)

    return ExchangeResponse(
        item=PlaidItemResponse.model_validate(item),
        account_ids=[a.id for a in created_accounts],
        skipped_accounts=skipped,
        sync=_summary_to_response(summary, item),
    )


@router.post("/items/{item_id}/sync", response_model=SyncResponse)
async def sync_now(
    item_id: int,
    db: DbSession,
    current_user: CurrentUser,
    plaid: PlaidDep,
) -> SyncResponse:
    item = await _get_owned_item(db, current_user.id, item_id)

    if item.last_synced_at is not None:
        last = item.last_synced_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - last < SYNC_RATE_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Sync was run less than {SYNC_RATE_LIMIT.seconds}s ago. Try again shortly.",
            )

    try:
        summary = await sync_item(db, item, plaid)
    except PlaidError as exc:
        await db.commit()  # persist item.last_error_code set inside sync_item
        raise _map_plaid_error(exc) from exc

    await db.commit()
    await db.refresh(item)
    return _summary_to_response(summary, item)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_item(
    item_id: int,
    db: DbSession,
    current_user: CurrentUser,
    plaid: PlaidDep,
) -> None:
    item = await _get_owned_item(db, current_user.id, item_id)
    from app.services.encryption import decrypt

    try:
        access_token = decrypt(item.access_token_encrypted)
        await plaid.remove_item(access_token)
    except PlaidError:
        # Plaid-side remove may fail (e.g. already removed); we still want to
        # drop local rows so the user isn't stuck.
        pass

    await db.delete(item)
    await db.commit()


@router.get("/items", response_model=list[PlaidItemResponse])
async def list_items(
    db: DbSession,
    current_user: CurrentUser,
) -> list[PlaidItemResponse]:
    rows = (
        await db.execute(
            select(PlaidItem)
            .where(PlaidItem.user_id == current_user.id)
            .order_by(PlaidItem.id)
        )
    ).scalars().all()
    return [PlaidItemResponse.model_validate(r) for r in rows]
