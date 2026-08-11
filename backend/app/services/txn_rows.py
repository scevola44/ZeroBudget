"""Turn ORM transaction rows into the plain ``TxnRow``s the calc modules take.

Both ``routers/budget.py`` and ``routers/insights.py`` need this, and they must
agree exactly: ``insights_calc`` re-implements ``budget_calc``'s rollover walk,
and the two are pinned against each other by
``test_insights_calc.py::test_month_end_balances_match_compute_category_balances``
and ``test_insights_api.py::test_insights_reconciles_with_the_budget_page_for_the_same_month``.
Building the rows in one place is what stops the transfer rule drifting between
them and quietly breaking those tests. Both routers must also build and pass
``account_on_budget`` identically for the same reason.
"""

from collections.abc import Sequence

from sqlalchemy import select

from app.models import Transaction, TransactionSplit
from app.models.scope import PERSONAL
from app.services.budget_calc import TxnRow


async def load_splits_by_transaction_id(
    db, transactions: Sequence[Transaction]
) -> dict[int, list[TransactionSplit]]:
    """Map transaction id -> its split lines, for every transaction that has any."""
    txn_ids = [t.id for t in transactions]
    if not txn_ids:
        return {}
    result = await db.execute(
        select(TransactionSplit).where(TransactionSplit.transaction_id.in_(txn_ids))
    )
    by_txn_id: dict[int, list[TransactionSplit]] = {}
    for split in result.scalars().all():
        by_txn_id.setdefault(split.transaction_id, []).append(split)
    return by_txn_id


async def load_peer_account_ids(
    db, transactions: Sequence[Transaction]
) -> dict[int, int]:
    """Map peer transaction id -> the account holding it, for every transfer leg.

    Loaded explicitly rather than read off ``transactions`` because the two legs
    of a transfer do not necessarily share a date: a pair linked from two bank
    imports keeps each bank's own booking date, so a date-windowed query can
    return one leg without the other.
    """
    peer_ids = {t.transfer_peer_id for t in transactions if t.transfer_peer_id is not None}
    if not peer_ids:
        return {}
    result = await db.execute(
        select(Transaction.id, Transaction.account_id).where(Transaction.id.in_(peer_ids))
    )
    return {row[0]: row[1] for row in result.all()}


def build_txn_rows(
    transactions: Sequence[Transaction],
    account_scope: dict[int, str],
    account_on_budget: dict[int, bool],
    peer_account_id: dict[int, int],
    splits_by_txn_id: dict[int, list[TransactionSplit]] | None = None,
) -> list[TxnRow]:
    """Join each transaction to its account's scope and its transfer peer's.

    ``peer_account_id`` covers every ``transfer_peer_id`` in ``transactions`` —
    build it with ``load_peer_account_ids``. A transaction with split lines
    (``splits_by_txn_id``, from ``load_splits_by_transaction_id``) emits one
    row per line instead of one row for the parent — ``budget_calc.py`` never
    sees the parent's own ``category_id``/``amount_cents`` in that case, only
    its lines'. Splits and transfers are mutually exclusive (enforced in
    ``routers/transactions.py``), so a split row's ``transfer_peer_scope`` is
    always ``None``.
    """
    splits_by_txn_id = splits_by_txn_id or {}
    own_scope: dict[int, str] = {
        t.id: account_scope.get(t.account_id, PERSONAL) for t in transactions
    }
    own_on_budget: dict[int, bool] = {
        t.id: account_on_budget.get(t.account_id, True) for t in transactions
    }

    def peer_scope(txn: Transaction) -> str | None:
        if txn.transfer_peer_id is None:
            return None
        account_id = peer_account_id.get(txn.transfer_peer_id)
        if account_id is None:
            # Should the peer be missing anyway, falling back to this row's own
            # scope marks the leg same-scope and excludes it from Ready to
            # Assign — the conservative reading of a transfer whose other half
            # isn't visible.
            return own_scope[txn.id]
        return account_scope.get(account_id, PERSONAL)

    rows: list[TxnRow] = []
    for t in transactions:
        splits = splits_by_txn_id.get(t.id)
        if splits:
            rows.extend(
                TxnRow(
                    category_id=s.category_id,
                    date=t.date,
                    amount_cents=s.amount_cents,
                    scope=own_scope[t.id],
                    transfer_peer_scope=None,
                    on_budget=own_on_budget[t.id],
                )
                for s in splits
            )
        else:
            rows.append(
                TxnRow(
                    category_id=t.category_id,
                    date=t.date,
                    amount_cents=t.amount_cents,
                    scope=own_scope[t.id],
                    transfer_peer_scope=peer_scope(t),
                    on_budget=own_on_budget[t.id],
                )
            )
    return rows
