"""Transaction sync orchestration — the heart of the Plaid integration.

Split out from the router so it can be unit-tested against a fake
``PlaidClient`` without spinning up FastAPI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, PlaidItem, Transaction
from app.services.encryption import decrypt
from app.services.plaid_amount import NonEurCurrencyError, plaid_amount_to_cents
from app.services.plaid_client import PlaidClient, PlaidError


@dataclass
class SyncSummary:
    added: int = 0
    modified: int = 0
    removed: int = 0
    skipped_pending: int = 0
    skipped_non_eur: int = 0
    skipped_unknown_account: int = 0
    error_code: str | None = None
    # Account IDs that have fresh data — the router can use this to hint
    # cache invalidation on the frontend.
    touched_account_ids: list[int] = field(default_factory=list)


def _parse_date(raw: Any) -> date:
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    return date.fromisoformat(str(raw))


async def sync_item(
    db: AsyncSession,
    item: PlaidItem,
    plaid_client: PlaidClient,
) -> SyncSummary:
    """Pull /transactions/sync deltas and apply them to the DB.

    Pending transactions are skipped (product rule). Non-EUR transactions are
    skipped defensively — we already reject non-EUR accounts at link time,
    but Plaid is free to return multi-currency data so we gate here too.

    User-owned fields (category, memo, payee once set) are preserved on
    ``modified`` events; only ``date`` and ``amount_cents`` are updated.
    """
    summary = SyncSummary()

    access_token = decrypt(item.access_token_encrypted)
    try:
        result = await plaid_client.sync_transactions(access_token, item.transactions_cursor)
    except PlaidError as exc:
        item.last_error_code = exc.code
        await db.flush()
        summary.error_code = exc.code
        raise

    account_rows = (
        await db.execute(
            select(Account).where(Account.plaid_item_id == item.id)
        )
    ).scalars().all()
    account_by_plaid_id = {a.plaid_account_id: a for a in account_rows if a.plaid_account_id}
    touched: set[int] = set()

    for txn in result.added:
        if txn.get("pending"):
            summary.skipped_pending += 1
            continue
        account = account_by_plaid_id.get(txn.get("account_id"))
        if account is None:
            summary.skipped_unknown_account += 1
            continue
        try:
            amount_cents = plaid_amount_to_cents(
                txn["amount"],
                txn.get("iso_currency_code"),
                txn.get("unofficial_currency_code"),
            )
        except NonEurCurrencyError:
            summary.skipped_non_eur += 1
            continue

        plaid_txn_id = txn["transaction_id"]
        existing = (
            await db.execute(
                select(Transaction).where(Transaction.plaid_transaction_id == plaid_txn_id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            # Re-delivered by Plaid after a previous successful sync. Idempotent skip.
            continue

        db.add(
            Transaction(
                user_id=item.user_id,
                account_id=account.id,
                date=_parse_date(txn["date"]),
                payee=txn.get("merchant_name") or txn.get("name") or "",
                memo="",
                amount_cents=amount_cents,
                plaid_transaction_id=plaid_txn_id,
            )
        )
        summary.added += 1
        touched.add(account.id)

    for txn in result.modified:
        plaid_txn_id = txn["transaction_id"]
        existing = (
            await db.execute(
                select(Transaction).where(Transaction.plaid_transaction_id == plaid_txn_id)
            )
        ).scalar_one_or_none()
        if existing is None:
            # Modified a row we never imported (e.g. it was pending when first
            # seen). Treat as a new addition if posted + EUR.
            if txn.get("pending"):
                summary.skipped_pending += 1
                continue
            account = account_by_plaid_id.get(txn.get("account_id"))
            if account is None:
                summary.skipped_unknown_account += 1
                continue
            try:
                amount_cents = plaid_amount_to_cents(
                    txn["amount"],
                    txn.get("iso_currency_code"),
                    txn.get("unofficial_currency_code"),
                )
            except NonEurCurrencyError:
                summary.skipped_non_eur += 1
                continue
            db.add(
                Transaction(
                    user_id=item.user_id,
                    account_id=account.id,
                    date=_parse_date(txn["date"]),
                    payee=txn.get("merchant_name") or txn.get("name") or "",
                    memo="",
                    amount_cents=amount_cents,
                    plaid_transaction_id=plaid_txn_id,
                )
            )
            summary.added += 1
            touched.add(account.id)
            continue

        try:
            amount_cents = plaid_amount_to_cents(
                txn["amount"],
                txn.get("iso_currency_code"),
                txn.get("unofficial_currency_code"),
            )
        except NonEurCurrencyError:
            summary.skipped_non_eur += 1
            continue
        # Preserve user-owned fields (category_id, memo, payee). Update only
        # what Plaid authoritatively owns.
        existing.date = _parse_date(txn["date"])
        existing.amount_cents = amount_cents
        summary.modified += 1
        touched.add(existing.account_id)

    for txn in result.removed:
        plaid_txn_id = txn["transaction_id"]
        existing = (
            await db.execute(
                select(Transaction).where(Transaction.plaid_transaction_id == plaid_txn_id)
            )
        ).scalar_one_or_none()
        if existing is None:
            continue
        touched.add(existing.account_id)
        await db.delete(existing)
        summary.removed += 1

    item.transactions_cursor = result.next_cursor
    item.last_synced_at = datetime.now(timezone.utc)
    item.last_error_code = None
    summary.touched_account_ids = sorted(touched)
    # Flush so pending INSERT/UPDATE/DELETE statements hit the DB. The caller
    # still owns whether to commit — they may choose to roll back if a later
    # step fails.
    await db.flush()
    return summary
