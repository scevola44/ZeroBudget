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
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.models import Account, BankConnection, SyncRun, Transaction
from app.services.bank_amount import (
    NonEurCurrencyError,
    bank_amount_to_cents,
    bank_balance_amount_to_cents,
)
from app.services.banking_client import BankingClient, BankingError
from app.services.encryption import decrypt
from app.services.payees import resolve_payee
from app.services.synthetic_payees import OPENING_BALANCE_PAYEE

logger = logging.getLogger(__name__)

PENDING_STATUS = "PDNG"
# Preference order for picking a single balance out of an account's balance
# list (Enable Banking's full BalanceStatus enum: CLAV, CLBD, FWAV, INFO,
# ITAV, ITBD, OPAV, OPBD, OTHR, PRCD, VALU, XPCD). We only ever import
# BOOK-status transactions (PDNG ones are skipped), so a "booked" balance is
# the more consistent match for reconciliation than an "available" one,
# which nets out holds/pending debits we don't have matching transactions
# for. Order: closing booked > interim booked > closing available >
# interim available > expected (last resort — may include non-booked
# forecasted movements). Deliberately excludes OPBD/OPAV (start-of-period,
# not current), PRCD (previous period's close), and FWAV (a future date) —
# those are stale/forward-looking, not "the balance right now". A bank that
# only returns one of those, or an unlisted type, falls through to the
# first balance in the list (see ``_select_balance``).
_BALANCE_TYPE_PREFERENCE = ("CLBD", "ITBD", "CLAV", "ITAV", "XPCD")


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
    skipped_unparseable_date: int = 0
    error_code: str | None = None
    # Account IDs that have fresh data — the router can use this to hint
    # cache invalidation on the frontend.
    touched_account_ids: list[int] = field(default_factory=list)


def external_transaction_id(account_id: int, txn: dict[str, Any]) -> str:
    """Stable dedup key for an imported transaction.

    ``entry_reference`` is only unique per account, so the local account id
    is always prefixed. Some banks omit it; then we hash the fields that
    don't change across re-fetches. Known limitation: two byte-identical
    same-day transactions collapse into one under the hash fallback.
    """
    entry_reference = txn.get("entry_reference")
    if entry_reference:
        return f"{account_id}:{entry_reference}"
    amount = (txn.get("transaction_amount") or {}).get("amount", "")
    remittance = "|".join(txn.get("remittance_information") or [])
    counterparty = (
        (txn.get("creditor") or {}).get("name")
        or (txn.get("debtor") or {}).get("name")
        or ""
    )
    fingerprint = "|".join(
        [
            str(txn.get("booking_date", "")),
            str(amount),
            str(txn.get("credit_debit_indicator", "")),
            counterparty,
            remittance,
        ]
    )
    digest = hashlib.sha256(fingerprint.encode()).hexdigest()[:32]
    return f"{account_id}:h:{digest}"


def _payee(txn: dict[str, Any]) -> str:
    if txn.get("credit_debit_indicator") == "CRDT":
        counterparty = (txn.get("debtor") or {}).get("name")
    else:
        counterparty = (txn.get("creditor") or {}).get("name")
    if counterparty:
        return counterparty
    remittance = txn.get("remittance_information") or []
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


def _select_balance(balances: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Pick one balance entry per ``_BALANCE_TYPE_PREFERENCE``, else the first available."""
    by_type = {b.get("balance_type"): b for b in balances}
    for balance_type in _BALANCE_TYPE_PREFERENCE:
        if balance_type in by_type:
            return by_type[balance_type]
    return balances[0] if balances else None


async def _import_opening_balance(
    db: AsyncSession,
    connection: BankConnection,
    client: BankingClient,
    account: Account,
    date_from: date,
) -> None:
    """Insert a one-time reconciling transaction so the derived balance matches the bank.

    Only the imported transaction window is ever fetched (see module docstring),
    so a freshly linked account's derived balance is short by whatever predates
    that window. This bridges the gap with a single uncategorized transaction —
    the same mechanism a user relies on today to set a manual account's balance —
    rather than storing a balance separately from the transaction ledger.

    Best-effort: any failure to fetch or parse the bank's balance is logged and
    skipped, leaving the account exactly as under the old behavior.
    """
    external_id = f"{account.id}:opening_balance"
    existing = (
        await db.execute(
            select(Transaction).where(Transaction.external_transaction_id == external_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return

    try:
        balances = await client.get_balances(account.bank_account_uid)
    except BankingError:
        logger.warning(
            "banking: could not fetch balance for account %s, opening balance not imported",
            account.id,
        )
        return
    balance = _select_balance(balances)
    if balance is None:
        return
    amount_info = balance.get("balance_amount") or {}
    try:
        bank_balance_cents = bank_balance_amount_to_cents(
            amount_info.get("amount", ""), amount_info.get("currency")
        )
    except (NonEurCurrencyError, ValueError):
        logger.warning(
            "banking: unparseable balance for account %s, opening balance not imported",
            account.id,
        )
        return

    imported_total = await db.scalar(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            Transaction.account_id == account.id
        )
    )
    delta = bank_balance_cents - int(imported_total or 0)
    if delta == 0:
        return

    db.add(
        Transaction(
            user_id=connection.user_id,
            account_id=account.id,
            # Sorts before every transaction imported by this sync's window.
            date=date_from - timedelta(days=1),
            payee=OPENING_BALANCE_PAYEE,
            # payee_id left NULL: this describes a bookkeeping reconciliation,
            # not a real counterparty (see services.payees.resolve_payee).
            memo=(
                "Balance imported from the bank on connection; covers transactions "
                "older than the sync window."
            ),
            amount_cents=delta,
            external_transaction_id=external_id,
        )
    )


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

    is_first_sync = connection.last_synced_at is None
    window_days = settings.sync_first_fetch_days if is_first_sync else settings.sync_fetch_days
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
            summary.skipped_unknown_account += 1
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
            txn_date = _parse_date(txn.get("booking_date") or txn.get("value_date"))
            if txn_date is None:
                logger.warning(
                    "banking: transaction missing booking_date/value_date, skipping: %r",
                    txn,
                )
                summary.skipped_unparseable_date += 1
                continue
            amount_info = txn.get("transaction_amount") or {}
            try:
                amount_cents = bank_amount_to_cents(
                    amount_info.get("amount", ""),
                    amount_info.get("currency"),
                    txn.get("credit_debit_indicator", ""),
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
                payee = _payee(txn)
                db.add(
                    Transaction(
                        user_id=connection.user_id,
                        account_id=account.id,
                        date=txn_date,
                        payee=payee,
                        payee_id=await resolve_payee(db, connection.user_id, payee),
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

        if is_first_sync:
            await db.flush()
            await _import_opening_balance(db, connection, client, account, date_from)

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
