"""Turn ORM transaction rows into the plain ``TxnRow``s the calc modules take.

Both ``routers/budget.py`` and ``routers/insights.py`` need this, and they must
agree exactly: ``insights_calc`` re-implements ``budget_calc``'s rollover walk,
and the two are pinned against each other by
``test_insights_calc.py::test_month_end_balances_match_compute_category_balances``
and ``test_insights_api.py::test_insights_reconciles_with_the_budget_page_for_the_same_month``.
Building the rows in one place is what stops the transfer rule drifting between
them and quietly breaking those tests.
"""

from collections.abc import Sequence

from app.models import Transaction
from app.models.scope import PERSONAL
from app.services.budget_calc import TxnRow


def build_txn_rows(
    transactions: Sequence[Transaction], account_scope: dict[int, str]
) -> list[TxnRow]:
    """Join each transaction to its account's scope and its transfer peer's."""
    scope_by_txn_id: dict[int, str] = {
        t.id: account_scope.get(t.account_id, PERSONAL) for t in transactions
    }

    def peer_scope(txn: Transaction) -> str | None:
        if txn.transfer_peer_id is None:
            return None
        # Both legs always share a date, so a date-windowed query loads both.
        # Should the peer be missing anyway, falling back to this row's own
        # scope marks the leg same-scope and excludes it from Ready to Assign —
        # the conservative reading of a transfer whose other half isn't visible.
        own_scope = scope_by_txn_id[txn.id]
        return scope_by_txn_id.get(txn.transfer_peer_id, own_scope)

    return [
        TxnRow(
            category_id=t.category_id,
            date=t.date,
            amount_cents=t.amount_cents,
            scope=scope_by_txn_id[t.id],
            transfer_peer_scope=peer_scope(t),
        )
        for t in transactions
    ]
