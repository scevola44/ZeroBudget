"""build_txn_rows: split-line flattening, pure over plain ORM-shaped objects."""

from datetime import date

from app.models.scope import PERSONAL
from app.services.txn_rows import build_txn_rows


class _FakeTransaction:
    """Just enough attribute surface for build_txn_rows — no DB needed."""

    def __init__(
        self,
        id: int,
        account_id: int,
        category_id: int | None,
        date: date,
        amount_cents: int,
        transfer_peer_id: int | None = None,
    ):
        self.id = id
        self.account_id = account_id
        self.category_id = category_id
        self.date = date
        self.amount_cents = amount_cents
        self.transfer_peer_id = transfer_peer_id


class _FakeSplit:
    def __init__(self, transaction_id: int, category_id: int | None, amount_cents: int):
        self.transaction_id = transaction_id
        self.category_id = category_id
        self.amount_cents = amount_cents


def test_unsplit_transaction_produces_one_row():
    txn = _FakeTransaction(id=1, account_id=10, category_id=5, date=date(2026, 4, 1), amount_cents=-1000)
    rows = build_txn_rows([txn], {10: PERSONAL}, {10: True}, {})
    assert len(rows) == 1
    assert rows[0].category_id == 5
    assert rows[0].amount_cents == -1000


def test_split_transaction_produces_one_row_per_line():
    txn = _FakeTransaction(id=1, account_id=10, category_id=None, date=date(2026, 4, 1), amount_cents=-1000)
    splits = [
        _FakeSplit(transaction_id=1, category_id=5, amount_cents=-600),
        _FakeSplit(transaction_id=1, category_id=6, amount_cents=-400),
    ]
    rows = build_txn_rows(
        [txn], {10: PERSONAL}, {10: True}, {}, {1: splits}
    )
    assert len(rows) == 2
    by_cat = {r.category_id: r.amount_cents for r in rows}
    assert by_cat == {5: -600, 6: -400}
    assert all(r.date == date(2026, 4, 1) for r in rows)
    assert all(r.scope == PERSONAL for r in rows)


def test_split_line_never_carries_a_transfer_peer_scope():
    """Splits and transfers are mutually exclusive (enforced in the router),
    but the flattening logic itself must not accidentally inherit a peer
    scope even if a caller passed one for the parent transaction."""
    txn = _FakeTransaction(
        id=1, account_id=10, category_id=None, date=date(2026, 4, 1), amount_cents=-1000
    )
    splits = [
        _FakeSplit(transaction_id=1, category_id=5, amount_cents=-500),
        _FakeSplit(transaction_id=1, category_id=None, amount_cents=-500),
    ]
    rows = build_txn_rows([txn], {10: PERSONAL}, {10: True}, {}, {1: splits})
    assert all(r.transfer_peer_scope is None for r in rows)


def test_uncategorized_split_line_is_a_row_like_any_other():
    txn = _FakeTransaction(id=1, account_id=10, category_id=None, date=date(2026, 4, 1), amount_cents=1000)
    splits = [
        _FakeSplit(transaction_id=1, category_id=None, amount_cents=800),
        _FakeSplit(transaction_id=1, category_id=5, amount_cents=200),
    ]
    rows = build_txn_rows([txn], {10: PERSONAL}, {10: True}, {}, {1: splits})
    uncategorized = [r for r in rows if r.category_id is None]
    assert len(uncategorized) == 1
    assert uncategorized[0].amount_cents == 800


def test_transaction_with_no_splits_entry_is_unaffected():
    txn = _FakeTransaction(id=1, account_id=10, category_id=5, date=date(2026, 4, 1), amount_cents=-1000)
    rows_without_arg = build_txn_rows([txn], {10: PERSONAL}, {10: True}, {})
    rows_with_empty_map = build_txn_rows([txn], {10: PERSONAL}, {10: True}, {}, {})
    assert rows_without_arg == rows_with_empty_map
