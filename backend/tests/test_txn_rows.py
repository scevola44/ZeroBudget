"""Pins ``build_txn_rows``'s split-expansion contract: a split transaction
becomes one ``TxnRow`` per line, summing to the parent's amount, and an
unsplit transaction is untouched. This is what keeps a split transaction's
budget/insights activity correct without ``budget_calc.py`` knowing splits
exist at all.
"""

from datetime import date

from app.models import Transaction, TransactionSplit
from app.services.budget_calc import feeds_ready_to_assign
from app.services.txn_rows import build_txn_rows

ACCOUNT_ID = 1
SCOPE_ID = 10


def _txn(*, id: int, category_id: int | None, amount_cents: int) -> Transaction:
    t = Transaction(
        account_id=ACCOUNT_ID,
        category_id=category_id,
        date=date(2026, 4, 1),
        amount_cents=amount_cents,
    )
    t.id = id  # normally assigned by the DB; set directly for a DB-free test
    return t


def _split(*, transaction_id: int, category_id: int | None, amount_cents: int) -> TransactionSplit:
    return TransactionSplit(
        transaction_id=transaction_id, category_id=category_id, amount_cents=amount_cents
    )


def test_non_split_transaction_still_produces_a_single_row():
    txn = _txn(id=1, category_id=5, amount_cents=-1000)

    rows = build_txn_rows([txn], {ACCOUNT_ID: SCOPE_ID}, {ACCOUNT_ID: True}, {})

    assert len(rows) == 1
    assert rows[0].category_id == 5
    assert rows[0].amount_cents == -1000
    assert rows[0].scope_id == SCOPE_ID


def test_build_txn_rows_expands_split_transaction_into_one_row_per_line():
    txn = _txn(id=1, category_id=None, amount_cents=-1000)
    splits = {
        1: [
            _split(transaction_id=1, category_id=7, amount_cents=-400),
            _split(transaction_id=1, category_id=8, amount_cents=-600),
        ]
    }

    rows = build_txn_rows(
        [txn], {ACCOUNT_ID: SCOPE_ID}, {ACCOUNT_ID: True}, {}, splits
    )

    assert len(rows) == 2
    assert {r.category_id for r in rows} == {7, 8}
    assert all(r.date == date(2026, 4, 1) for r in rows)
    assert all(r.scope_id == SCOPE_ID for r in rows)


def test_split_lines_sum_to_parent_amount():
    txn = _txn(id=1, category_id=None, amount_cents=-1000)
    splits = {
        1: [
            _split(transaction_id=1, category_id=7, amount_cents=-250),
            _split(transaction_id=1, category_id=8, amount_cents=-750),
        ]
    }

    rows = build_txn_rows([txn], {ACCOUNT_ID: SCOPE_ID}, {ACCOUNT_ID: True}, {}, splits)

    assert sum(r.amount_cents for r in rows) == txn.amount_cents


def test_split_line_with_null_category_feeds_ready_to_assign():
    txn = _txn(id=1, category_id=None, amount_cents=1000)
    splits = {
        1: [
            _split(transaction_id=1, category_id=None, amount_cents=600),
            _split(transaction_id=1, category_id=9, amount_cents=400),
        ]
    }

    rows = build_txn_rows([txn], {ACCOUNT_ID: SCOPE_ID}, {ACCOUNT_ID: True}, {}, splits)

    unassigned_row = next(r for r in rows if r.category_id is None)
    categorized_row = next(r for r in rows if r.category_id == 9)
    assert feeds_ready_to_assign(unassigned_row)
    assert not feeds_ready_to_assign(categorized_row)


def test_transactions_with_no_split_lines_are_unaffected_by_the_splits_map():
    unsplit = _txn(id=1, category_id=5, amount_cents=-1000)
    split = _txn(id=2, category_id=None, amount_cents=-500)
    splits = {2: [_split(transaction_id=2, category_id=6, amount_cents=-500)]}

    rows = build_txn_rows(
        [unsplit, split], {ACCOUNT_ID: SCOPE_ID}, {ACCOUNT_ID: True}, {}, splits
    )

    assert len(rows) == 2
    by_category = {r.category_id: r.amount_cents for r in rows}
    assert by_category[5] == -1000
    assert by_category[6] == -500
