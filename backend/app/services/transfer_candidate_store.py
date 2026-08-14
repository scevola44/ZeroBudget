"""Keeps ``transfer_match_candidates`` in sync with the transactions table.

``transfer_match.py`` stays pure and DB-free — this module is the ORM-facing
half, mirroring how ``txn_rows.py`` sits in front of ``budget_calc``. It is the
only writer of ``TransferMatchCandidate`` rows.

The table is a cache of ``transfer_match.is_match`` pairs among linkable
transactions, not a verdict: a row means "these two could be a transfer's two
legs," never "this is a transfer." Confirmed links still live entirely on
``Transaction.transfer_peer_id`` (see ``routers/transactions.py``), so nothing
here can become a second source of truth for ``budget_calc``'s inputs — the
concern that sank the staging table ROADMAP.md's Phase 6 originally
considered.

``sync_candidates_for`` is idempotent and self-correcting: it always deletes
whatever is currently stored for a transaction before re-deriving it from that
transaction's current state, so callers never need to diff old vs. new field
values — just call it once per transaction id after any write that could
change whether that row matches another (create, edit date/amount/account/
category, link, unlink). A plain delete needs no call at all: both FK columns
on ``TransferMatchCandidate`` cascade.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Transaction, TransactionSplit, TransferMatchCandidate
from app.services.transfer_match import (
    TRANSFER_MATCH_WINDOW_DAYS,
    MatchRow,
    find_candidates,
    is_linkable,
    select_disjoint_pairs,
)
from app.services.txn_rows import load_payee_names


async def linkable_transactions_between(
    db: AsyncSession, user_id: int, start_date: date, end_date: date
) -> list[Transaction]:
    """Unlinked, unsplit transactions in a date window, the raw material for
    matching.

    Narrowed in SQL only by ownership, date and split status — all cheap
    filters that are purely about not loading the whole ledger and not
    offering rows that could never legally become a transfer leg. Which of
    the rest actually pair is ``transfer_match``'s call alone, so the rule
    lives in exactly one place. A split transaction is excluded outright: it
    already has its category-free line-items, and letting it become a
    transfer would require reasoning about splits inside every transfer
    response shape.
    """
    has_splits = (
        select(TransactionSplit.id)
        .where(TransactionSplit.transaction_id == Transaction.id)
        .exists()
    )
    stmt = select(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.transfer_peer_id.is_(None),
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        ~has_splits,
    )
    return list((await db.execute(stmt)).scalars().all())


def to_match_row(txn: Transaction, payee_names: dict[int, str]) -> MatchRow:
    return MatchRow(
        id=txn.id,
        account_id=txn.account_id,
        category_id=txn.category_id,
        date=txn.date,
        amount_cents=txn.amount_cents,
        payee=payee_names.get(txn.payee_id, "") if txn.payee_id is not None else "",
        transfer_peer_id=txn.transfer_peer_id,
    )


def _pair(a_id: int, b_id: int) -> tuple[int, int]:
    return (a_id, b_id) if a_id < b_id else (b_id, a_id)


async def _clear_candidates_for(db: AsyncSession, transaction_id: int) -> None:
    await db.execute(
        delete(TransferMatchCandidate).where(
            or_(
                TransferMatchCandidate.transaction_lo_id == transaction_id,
                TransferMatchCandidate.transaction_hi_id == transaction_id,
            )
        )
    )


async def sync_candidates_for(db: AsyncSession, user_id: int, transaction_id: int) -> None:
    """Recompute persisted transfer-match candidates touching ``transaction_id``.

    Safe to call unconditionally after any transaction write — a row that
    isn't linkable (categorized status aside; see ``is_linkable``) simply ends
    up with nothing stored for it.
    """
    await _clear_candidates_for(db, transaction_id)

    txn = await db.get(Transaction, transaction_id)
    if txn is None or txn.user_id != user_id:
        return

    payee_names = await load_payee_names(db, [txn])
    target = to_match_row(txn, payee_names)
    if not is_linkable(target):
        return

    window = timedelta(days=TRANSFER_MATCH_WINDOW_DAYS)
    rows = [
        row
        for row in await linkable_transactions_between(
            db, user_id, txn.date - window, txn.date + window
        )
        if row.id != transaction_id
    ]
    other_payee_names = await load_payee_names(db, rows)
    matches = find_candidates(target, [to_match_row(row, other_payee_names) for row in rows])

    for match in matches:
        lo_id, hi_id = _pair(transaction_id, match.id)
        db.add(
            TransferMatchCandidate(
                user_id=user_id, transaction_lo_id=lo_id, transaction_hi_id=hi_id
            )
        )


async def suggested_transfer_pairs_between(
    db: AsyncSession, user_id: int, start_date: date, end_date: date
) -> list[tuple[Transaction, Transaction]]:
    """Disjoint (outflow, inflow) pairs touching ``[start_date, end_date]``,
    drawn from the persisted candidate table — the store-backed equivalent of
    ``transfer_match.suggest_pairs``, read as an indexed join instead of a
    fresh date-windowed scan.

    "Touching" means either leg's own date falls in range, not both: a
    transfer dated right at the edge of a caller's range (e.g. the last day of
    a month view) can have its other leg just outside it, and a pair is only
    ever stored once both legs already satisfy ``is_match``'s own (tighter)
    date window — so no extra padding is needed here the way the pre-store
    heuristic needed it.

    Only uncategorized rows are offered, mirroring ``suggest_pairs``: a
    category is a deliberate statement that the row is spending, and a
    suggestion should never invite the user to undo their own intent with one
    click — explicit linking may still override it.
    """
    lo = aliased(Transaction)
    hi = aliased(Transaction)
    stmt = (
        select(lo, hi)
        .select_from(TransferMatchCandidate)
        .join(lo, TransferMatchCandidate.transaction_lo_id == lo.id)
        .join(hi, TransferMatchCandidate.transaction_hi_id == hi.id)
        .where(
            TransferMatchCandidate.user_id == user_id,
            lo.category_id.is_(None),
            hi.category_id.is_(None),
            or_(
                and_(lo.date >= start_date, lo.date <= end_date),
                and_(hi.date >= start_date, hi.date <= end_date),
            ),
        )
    )
    rows = (await db.execute(stmt)).all()
    payee_names = await load_payee_names(db, [txn for pair in rows for txn in pair])

    by_id: dict[int, Transaction] = {}
    matched: list[tuple[MatchRow, MatchRow]] = []
    for lo_txn, hi_txn in rows:
        by_id[lo_txn.id] = lo_txn
        by_id[hi_txn.id] = hi_txn
        lo_row, hi_row = to_match_row(lo_txn, payee_names), to_match_row(hi_txn, payee_names)
        matched.append((lo_row, hi_row) if lo_row.amount_cents < 0 else (hi_row, lo_row))

    return [
        (by_id[pair.outflow_id], by_id[pair.inflow_id]) for pair in select_disjoint_pairs(matched)
    ]
