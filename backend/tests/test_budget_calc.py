"""Pure-function tests for the zero-based math.

These tests pin down the behaviour that defines "zero-based" for this app:
Ready-to-Assign shrinks as you assign money; category balances roll forward
month to month; activity is scoped to the requested month; and personal vs.
shared scopes are independent budget pools.
"""

from datetime import date

from app.services.budget_calc import (
    AssignmentRow,
    TxnRow,
    compute_category_balances,
    compute_ready_to_assign,
    month_start,
    next_month_start,
    parse_month,
)

APRIL = date(2026, 4, 1)
MAY = date(2026, 5, 1)


def _txn(
    *,
    category_id: int | None,
    date: date,
    amount_cents: int,
    scope: str = "personal",
) -> TxnRow:
    return TxnRow(
        category_id=category_id, date=date, amount_cents=amount_cents, scope=scope
    )


def _assign(
    *,
    category_id: int,
    month: date,
    amount_cents: int,
    scope: str = "personal",
) -> AssignmentRow:
    return AssignmentRow(
        category_id=category_id, month=month, amount_cents=amount_cents, scope=scope
    )


def test_month_helpers():
    assert month_start(date(2026, 4, 17)) == APRIL
    assert next_month_start(APRIL) == MAY
    assert next_month_start(date(2026, 12, 1)) == date(2027, 1, 1)
    assert parse_month("2026-04") == APRIL


def test_ready_to_assign_starts_empty():
    assert compute_ready_to_assign([], [], APRIL, "personal") == 0


def test_ready_to_assign_counts_only_unassigned_inflow():
    txns = [
        _txn(category_id=None, date=date(2026, 4, 3), amount_cents=100_000),  # inflow
        _txn(category_id=42, date=date(2026, 4, 5), amount_cents=-20_000),  # categorized spend
    ]
    # Categorized spend does NOT affect ready_to_assign.
    assert compute_ready_to_assign(txns, [], APRIL, "personal") == 100_000


def test_ready_to_assign_shrinks_as_money_is_assigned():
    txns = [_txn(category_id=None, date=date(2026, 4, 3), amount_cents=100_000)]
    assigns = [_assign(category_id=1, month=APRIL, amount_cents=60_000)]
    assert compute_ready_to_assign(txns, assigns, APRIL, "personal") == 40_000


def test_ready_to_assign_scoped_to_requested_month():
    txns = [
        _txn(category_id=None, date=date(2026, 4, 3), amount_cents=100_000),
        _txn(category_id=None, date=date(2026, 5, 3), amount_cents=50_000),
    ]
    assigns = [
        _assign(category_id=1, month=APRIL, amount_cents=30_000),
        _assign(category_id=1, month=MAY, amount_cents=20_000),
    ]
    # April sees its inflows and deducts only through-April assignments.
    assert compute_ready_to_assign(txns, assigns, APRIL, "personal") == 70_000
    # May sees all inflows through May and deducts all through-May assignments.
    assert compute_ready_to_assign(txns, assigns, MAY, "personal") == 100_000


def test_past_month_unaffected_by_future_assignments():
    MARCH = date(2026, 3, 1)
    txns = [_txn(category_id=None, date=date(2026, 4, 3), amount_cents=100_000)]
    assigns = [
        _assign(category_id=1, month=APRIL, amount_cents=50_000),
        _assign(category_id=1, month=MAY, amount_cents=50_000),
    ]
    assert compute_ready_to_assign(txns, assigns, MARCH, "personal") == 0


def test_category_balance_for_single_month():
    cat = 1
    txns = [
        _txn(category_id=cat, date=date(2026, 4, 5), amount_cents=-15_000),
        _txn(category_id=cat, date=date(2026, 4, 20), amount_cents=-5_000),
    ]
    assigns = [_assign(category_id=cat, month=APRIL, amount_cents=60_000)]
    balances = compute_category_balances([cat], txns, assigns, APRIL)
    b = balances[cat]
    assert b.assigned_cents == 60_000
    assert b.activity_cents == -20_000
    assert b.balance_cents == 40_000


def test_category_balance_rolls_positive_prior_forward():
    cat = 1
    txns = [_txn(category_id=cat, date=date(2026, 4, 5), amount_cents=-10_000)]
    assigns = [
        _assign(category_id=cat, month=APRIL, amount_cents=60_000),
        _assign(category_id=cat, month=MAY, amount_cents=20_000),
    ]
    balances = compute_category_balances([cat], txns, assigns, MAY)
    b = balances[cat]
    # April left 50_000 in the category; May adds 20_000 → balance 70_000.
    assert b.assigned_cents == 20_000
    assert b.activity_cents == 0
    assert b.balance_cents == 70_000


def test_category_balance_rolls_negative_prior_forward():
    cat = 1
    txns = [_txn(category_id=cat, date=date(2026, 4, 5), amount_cents=-30_000)]
    assigns = [
        _assign(category_id=cat, month=APRIL, amount_cents=10_000),
        _assign(category_id=cat, month=MAY, amount_cents=10_000),
    ]
    balances = compute_category_balances([cat], txns, assigns, MAY)
    b = balances[cat]
    # April ended at -20_000; May adds 10_000 → balance -10_000.
    assert b.balance_cents == -10_000


def test_activity_is_scoped_to_requested_month():
    cat = 1
    txns = [
        _txn(category_id=cat, date=date(2026, 3, 28), amount_cents=-5_000),
        _txn(category_id=cat, date=date(2026, 4, 1), amount_cents=-7_000),
        _txn(category_id=cat, date=date(2026, 4, 30), amount_cents=-3_000),
        _txn(category_id=cat, date=date(2026, 5, 1), amount_cents=-9_000),
    ]
    balances = compute_category_balances([cat], txns, [], APRIL)
    assert balances[cat].activity_cents == -10_000


def test_multiple_categories_are_independent():
    txns = [
        _txn(category_id=1, date=date(2026, 4, 2), amount_cents=-10_000),
        _txn(category_id=2, date=date(2026, 4, 2), amount_cents=-20_000),
    ]
    assigns = [
        _assign(category_id=1, month=APRIL, amount_cents=30_000),
        _assign(category_id=2, month=APRIL, amount_cents=50_000),
    ]
    balances = compute_category_balances([1, 2], txns, assigns, APRIL)
    assert balances[1].balance_cents == 20_000
    assert balances[2].balance_cents == 30_000


# --- Scope isolation ----------------------------------------------------------


def test_personal_inflow_does_not_bleed_into_shared_rta():
    txns = [
        _txn(category_id=None, date=APRIL, amount_cents=100_000, scope="personal"),
    ]
    assert compute_ready_to_assign(txns, [], APRIL, "personal") == 100_000
    assert compute_ready_to_assign(txns, [], APRIL, "shared") == 0


def test_shared_inflow_does_not_bleed_into_personal_rta():
    txns = [
        _txn(category_id=None, date=APRIL, amount_cents=80_000, scope="shared"),
    ]
    assert compute_ready_to_assign(txns, [], APRIL, "personal") == 0
    assert compute_ready_to_assign(txns, [], APRIL, "shared") == 80_000


def test_per_scope_assignments_only_drain_their_own_pool():
    txns = [
        _txn(category_id=None, date=APRIL, amount_cents=100_000, scope="personal"),
        _txn(category_id=None, date=APRIL, amount_cents=80_000, scope="shared"),
    ]
    assigns = [
        _assign(category_id=1, month=APRIL, amount_cents=30_000, scope="personal"),
        _assign(category_id=2, month=APRIL, amount_cents=20_000, scope="shared"),
    ]
    assert compute_ready_to_assign(txns, assigns, APRIL, "personal") == 70_000
    assert compute_ready_to_assign(txns, assigns, APRIL, "shared") == 60_000


def test_future_overdraft_isolated_per_scope():
    # Shared has a future assignment with no future inflow → eats into shared
    # RTA. Personal must be unaffected.
    txns = [
        _txn(category_id=None, date=APRIL, amount_cents=100_000, scope="personal"),
        _txn(category_id=None, date=APRIL, amount_cents=50_000, scope="shared"),
    ]
    assigns = [
        _assign(category_id=2, month=MAY, amount_cents=70_000, scope="shared"),
    ]
    assert compute_ready_to_assign(txns, assigns, APRIL, "personal") == 100_000
    # Shared April: 50k inflow on hand, May overdraft of 70k pulls back 70k.
    assert compute_ready_to_assign(txns, assigns, APRIL, "shared") == -20_000


def test_transfer_pair_yields_expected_per_scope_rta():
    # A transfer is two unassigned-category transactions on opposite scopes.
    # Personal: 1000 salary, then -600 transfer out → 400.
    # Shared: 600 transfer in → 600.
    txns = [
        _txn(category_id=None, date=date(2026, 4, 1), amount_cents=100_000, scope="personal"),
        _txn(category_id=None, date=date(2026, 4, 2), amount_cents=-60_000, scope="personal"),
        _txn(category_id=None, date=date(2026, 4, 2), amount_cents=60_000, scope="shared"),
    ]
    assert compute_ready_to_assign(txns, [], APRIL, "personal") == 40_000
    assert compute_ready_to_assign(txns, [], APRIL, "shared") == 60_000
