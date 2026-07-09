"""Transaction sync orchestration — the heart of the Enable Banking integration.

Split out from the router so it can be unit-tested against a fake
``BankingClient`` without spinning up FastAPI.

Enable Banking has no Plaid-style delta API, so each sync re-fetches a date
window per account and dedups locally via ``Transaction.external_transaction_id``.
Consequences, by design:

- No deletion detection: a transaction removed at the bank stays in ZeroBudget.
- "Modified" means a re-fetched row whose date/amount changed; user-owned
  fields (category, memo, payee once set) are never touched.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.models import Account, BankConnection, SyncRun, Transaction
from app.services.bank_amount import NonEurCurrencyError, bank_amount_to_cents
from app.services.banking_client import BankingClient, BankingError
from app.services.encryption import decrypt

PENDING_STATUS = "PDNG"


@dataclass
class SyncSummary:
    added: int = 0
    modified: int = 0
    # Always 0 — Enable Banking has no delta API, so deletions at the bank
    # are undetectable. Kept for response-schema stability.
    removed: int = 0
    skipped_pending: int = 0
    skipped_non_eur: int = 0
    skipped_unknown_account: int = 0
    error_code: str | None = None
    # Account IDs that have fresh data — the router can use this to hint
    # cache invalidation on the frontend.
    touched_account_ids: list[int] = field(default_factory=list)


def external_transaction_id(account_id: int, txn: dict[str, Any]) -> str:
    """Stable dedup key for an imported transaction.

    ``entryReference`` is only unique per account, so the local account id
    is always prefixed. Some banks omit it; then we hash the fields that
    don't change across re-fetches. Known limitation: two byte-identical
    same-day transactions collapse into one under the hash fallback.
    """
    entry_reference = txn.get("entryReference")
    if entry_reference:
        return f"{account_id}:{entry_reference}"
    amount = (txn.get("transactionAmount") or {}).get("amount", "")
    remittance = "|".join(txn.get("remittanceInformation") or [])
    counterparty = (
        (txn.get("creditor") or {}).get("name")
        or (txn.get("debtor") or {}).get("name")
        or ""
    )
    fingerprint = "|".join(
        [
            str(txn.get("bookingDate", "")),
            str(amount),
            str(txn.get("creditDebitIndicator", "")),
            counterparty,
            remittance,
        ]
    )
    digest = hashlib.sha256(fingerprint.encode()).hexdigest()[:32]
    return f"{account_id}:h:{digest}"


def _payee(txn: dict[str, Any]) -> str:
    if txn.get("creditDebitIndicator") == "CRDT":
        counterparty = (txn.get("debtor") or {}).get("name")
    else:
        counterparty = (txn.get("creditor") or {}).get("name")
    if counterparty:
        return counterparty
    remittance = txn.get("remittanceInformation") or []
    return remittance[0] if remittance else ""


def _parse_date(raw: Any) -> date | None:
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    if not raw:
        return None
    return date.fromisoformat(str(raw))


def _as_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


async def sync_connection(
    db: AsyncSession,
    connection: BankConnection,
    client: BankingClient,
    settings: Settings | None = None,
) -> SyncSummary:
    """Re-fetch the transaction window for every account on this connection.

    Pending transactions are skipped (product rule, same as the old Plaid
    flow). Non-EUR transactions are skipped defensively — non-EUR accounts
    are rejected at link time, but the gate stays here too.

    On failure the connection's ``last_error_code`` is recorded and flushed
    before re-raising, so callers can commit the error state. The caller
    owns the final commit/rollback.
    """
    settings = settings or get_settings()
    summary = SyncSummary()

    if connection.valid_until is not None and _as_utc(connection.valid_until) < datetime.now(
        timezone.utc
    ):
        connection.last_error_code = "SESSION_EXPIRED"
        await db.flush()
        summary.error_code = "SESSION_EXPIRED"
        raise BankingError(
            "SESSION_EXPIRED",
            f"Consent for {connection.aspsp_name} expired; the bank must be re-authorized.",
        )

    window_days = (
        settings.sync_first_fetch_days
        if connection.last_synced_at is None
        else settings.sync_fetch_days
    )
    date_from = date.today() - timedelta(days=window_days)

    account_rows = (
        (
            await db.execute(
                select(Account).where(Account.bank_connection_id == connection.id)
            )
        )
        .scalars()
        .all()
    )
    touched: set[int] = set()

    for account in account_rows:
        if not account.bank_account_uid:
            continue
        try:
            transactions = await client.get_transactions(account.bank_account_uid, date_from)
        except BankingError as exc:
            connection.last_error_code = exc.code
            await db.flush()
            summary.error_code = exc.code
            raise

        for txn in transactions:
            if txn.get("status") == PENDING_STATUS:
                summary.skipped_pending += 1
                continue
            txn_date = _parse_date(txn.get("bookingDate") or txn.get("valueDate"))
            if txn_date is None:
                continue
            amount_info = txn.get("transactionAmount") or {}
            try:
                amount_cents = bank_amount_to_cents(
                    amount_info.get("amount", ""),
                    amount_info.get("currency"),
                    txn.get("creditDebitIndicator", ""),
                )
            except NonEurCurrencyError:
                summary.skipped_non_eur += 1
                continue

            external_id = external_transaction_id(account.id, txn)
            existing = (
                await db.execute(
                    select(Transaction).where(
                        Transaction.external_transaction_id == external_id
                    )
                )
            ).scalar_one_or_none()

            if existing is None:
                db.add(
                    Transaction(
                        user_id=connection.user_id,
                        account_id=account.id,
                        date=txn_date,
                        payee=_payee(txn),
                        memo="",
                        amount_cents=amount_cents,
                        external_transaction_id=external_id,
                    )
                )
                summary.added += 1
                touched.add(account.id)
            elif existing.date != txn_date or existing.amount_cents != amount_cents:
                # Preserve user-owned fields (category_id, memo, payee).
                # Update only what the bank authoritatively owns.
                existing.date = txn_date
                existing.amount_cents = amount_cents
                summary.modified += 1
                touched.add(existing.account_id)

    connection.last_synced_at = datetime.now(timezone.utc)
    connection.last_error_code = None
    summary.touched_account_ids = sorted(touched)
    # Flush so pending INSERT/UPDATE statements hit the DB. The caller still
    # owns whether to commit — they may choose to roll back if a later step
    # fails.
    await db.flush()
    return summary


async def run_global_sync(
    db: AsyncSession,
    client: BankingClient,
    trigger: str,
    settings: Settings | None = None,
) -> tuple[SyncRun, dict[int, SyncSummary]]:
    """Sync every bank connection in the system as one quota-counted run.

    The ``SyncRun`` row is inserted up front: a partially failed run still
    spent API calls, so it still counts against the daily quota. Individual
    connection failures mark the run ``partial`` but never abort it.
    """
    run = SyncRun(
        started_at=datetime.now(timezone.utc),
        trigger=trigger,
        status=SyncRun.STATUS_OK,
    )
    db.add(run)
    await db.flush()

    connections = (
        (await db.execute(select(BankConnection).order_by(BankConnection.id)))
        .scalars()
        .all()
    )

    summaries: dict[int, SyncSummary] = {}
    failures = 0
    for connection in connections:
        try:
            summaries[connection.id] = await sync_connection(db, connection, client, settings)
        except BankingError as exc:
            failures += 1
            summaries[connection.id] = SyncSummary(error_code=exc.code)

    run.added = sum(s.added for s in summaries.values())
    run.modified = sum(s.modified for s in summaries.values())
    if failures:
        run.status = (
            SyncRun.STATUS_ERROR if failures == len(connections) else SyncRun.STATUS_PARTIAL
        )
    await db.flush()
    return run, summaries
