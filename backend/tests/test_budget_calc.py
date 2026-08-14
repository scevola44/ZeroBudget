"""Pure-function tests for the zero-based math.

These tests pin down the behaviour that defines "zero-based" for this app:
Ready-to-Assign shrinks as you assign money; category balances roll forward
month to month; activity is scoped to the requested month; and separate scopes
are independent budget pools.
"""

from datetime import date

from app.services.budget_calc import (
    AssignmentRow,
    FundGoalsEntry,
    TxnRow,
    compute_category_balances,
    compute_fund_goals_plan,
    compute_ready_to_assign,
    month_start,
    next_month_start,
    parse_month,
)

# Scopes are rows in the database, so these unit tests only need two distinct
# ids. The names say which pool each stands for.
PERSONAL = 1
FAMILY = 2

APRIL = date(2026, 4, 1)
MAY = date(2026, 5, 1)


def _txn(
    *,
    category_id: int | None,
    date: date,
    amount_cents: int,
    scope_id: int = PERSONAL,
    transfer_peer_scope_id: int | None = None,
    on_budget: bool = True,
    transfer_peer_on_budget: bool = True,
) -> TxnRow:
    return TxnRow(
        category_id=category_id,
        date=date,
        amount_cents=amount_cents,
        scope_id=scope_id,
        transfer_peer_scope_id=transfer_peer_scope_id,
        on_budget=on_budget,
        transfer_peer_on_budget=transfer_peer_on_budget,
    )


def _assign(
    *,
    category_id: int,
    month: date,
    amount_cents: int,
    scope_id: int = PERSONAL,
) -> AssignmentRow:
    return AssignmentRow(
        category_id=category_id, month=month, amount_cents=amount_cents, scope_id=scope_id
    )


def test_month_helpers():
    assert month_start(date(2026, 4, 17)) == APRIL
    assert next_month_start(APRIL) == MAY
    assert next_month_start(date(2026, 12, 1)) == date(2027, 1, 1)
    assert parse_month("2026-04") == APRIL


def test_ready_to_assign_starts_empty():
    assert compute_ready_to_assign([], [], APRIL, PERSONAL) == 0


def test_ready_to_assign_counts_only_unassigned_inflow():
    txns = [
        _txn(category_id=None, date=date(2026, 4, 3), amount_cents=100_000),  # inflow
        _txn(category_id=42, date=date(2026, 4, 5), amount_cents=-20_000),  # categorized spend
    ]
    # Categorized spend does NOT affect ready_to_assign.
    assert compute_ready_to_assign(txns, [], APRIL, PERSONAL) == 100_000


def test_ready_to_assign_shrinks_as_money_is_assigned():
    txns = [_txn(category_id=None, date=date(2026, 4, 3), amount_cents=100_000)]
    assigns = [_assign(category_id=1, month=APRIL, amount_cents=60_000)]
    assert compute_ready_to_assign(txns, assigns, APRIL, PERSONAL) == 40_000


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
    assert compute_ready_to_assign(txns, assigns, APRIL, PERSONAL) == 70_000
    # May sees all inflows through May and deducts all through-May assignments.
    assert compute_ready_to_assign(txns, assigns, MAY, PERSONAL) == 100_000


def test_past_month_unaffected_by_future_assignments():
    MARCH = date(2026, 3, 1)
    txns = [_txn(category_id=None, date=date(2026, 4, 3), amount_cents=100_000)]
    assigns = [
        _assign(category_id=1, month=APRIL, amount_cents=50_000),
        _assign(category_id=1, month=MAY, amount_cents=50_000),
    ]
    assert compute_ready_to_assign(txns, assigns, MARCH, PERSONAL) == 0


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
        _txn(category_id=None, date=APRIL, amount_cents=100_000, scope_id=PERSONAL),
    ]
    assert compute_ready_to_assign(txns, [], APRIL, PERSONAL) == 100_000
    assert compute_ready_to_assign(txns, [], APRIL, FAMILY) == 0


def test_shared_inflow_does_not_bleed_into_personal_rta():
    txns = [
        _txn(category_id=None, date=APRIL, amount_cents=80_000, scope_id=FAMILY),
    ]
    assert compute_ready_to_assign(txns, [], APRIL, PERSONAL) == 0
    assert compute_ready_to_assign(txns, [], APRIL, FAMILY) == 80_000


def test_per_scope_assignments_only_drain_their_own_pool():
    txns = [
        _txn(category_id=None, date=APRIL, amount_cents=100_000, scope_id=PERSONAL),
        _txn(category_id=None, date=APRIL, amount_cents=80_000, scope_id=FAMILY),
    ]
    assigns = [
        _assign(category_id=1, month=APRIL, amount_cents=30_000, scope_id=PERSONAL),
        _assign(category_id=2, month=APRIL, amount_cents=20_000, scope_id=FAMILY),
    ]
    assert compute_ready_to_assign(txns, assigns, APRIL, PERSONAL) == 70_000
    assert compute_ready_to_assign(txns, assigns, APRIL, FAMILY) == 60_000


def test_future_overdraft_isolated_per_scope():
    # Shared has a future assignment with no future inflow → eats into shared
    # RTA. Personal must be unaffected.
    txns = [
        _txn(category_id=None, date=APRIL, amount_cents=100_000, scope_id=PERSONAL),
        _txn(category_id=None, date=APRIL, amount_cents=50_000, scope_id=FAMILY),
    ]
    assigns = [
        _assign(category_id=2, month=MAY, amount_cents=70_000, scope_id=FAMILY),
    ]
    assert compute_ready_to_assign(txns, assigns, APRIL, PERSONAL) == 100_000
    # Shared April: 50k inflow on hand, May overdraft of 70k pulls back 70k.
    assert compute_ready_to_assign(txns, assigns, APRIL, FAMILY) == -20_000


def test_cross_scope_transfer_moves_ready_to_assign_between_pools():
    # A cross-scope transfer really does move money out of one pool and into
    # the other, so both legs count.
    # Personal: 1000 salary, then -600 transfer out → 400.
    # Shared: 600 transfer in → 600.
    txns = [
        _txn(category_id=None, date=date(2026, 4, 1), amount_cents=100_000, scope_id=PERSONAL),
        _txn(
            category_id=None,
            date=date(2026, 4, 2),
            amount_cents=-60_000,
            scope_id=PERSONAL,
            transfer_peer_scope_id=FAMILY,
        ),
        _txn(
            category_id=None,
            date=date(2026, 4, 2),
            amount_cents=60_000,
            scope_id=FAMILY,
            transfer_peer_scope_id=PERSONAL,
        ),
    ]
    assert compute_ready_to_assign(txns, [], APRIL, PERSONAL) == 40_000
    assert compute_ready_to_assign(txns, [], APRIL, FAMILY) == 60_000


def test_same_scope_transfer_leaves_ready_to_assign_untouched():
    # Moving money between two personal accounts is the same pool's money
    # changing hands: neither leg touches Ready to Assign.
    txns = [
        _txn(category_id=None, date=date(2026, 4, 1), amount_cents=100_000, scope_id=PERSONAL),
        _txn(
            category_id=None,
            date=date(2026, 4, 2),
            amount_cents=-60_000,
            scope_id=PERSONAL,
            transfer_peer_scope_id=PERSONAL,
        ),
        _txn(
            category_id=None,
            date=date(2026, 4, 2),
            amount_cents=60_000,
            scope_id=PERSONAL,
            transfer_peer_scope_id=PERSONAL,
        ),
    ]
    assert compute_ready_to_assign(txns, [], APRIL, PERSONAL) == 100_000


def test_incoming_same_scope_transfer_leg_is_not_treated_as_income():
    # The failure this guards against: a positive uncategorized leg looking
    # like fresh income and inflating the pool it landed in.
    txns = [
        _txn(
            category_id=None,
            date=APRIL,
            amount_cents=60_000,
            scope_id=PERSONAL,
            transfer_peer_scope_id=PERSONAL,
        ),
    ]
    assert compute_ready_to_assign(txns, [], APRIL, PERSONAL) == 0


# --- Off-budget (savings) accounts --------------------------------------------


def test_off_budget_uncategorized_inflow_does_not_feed_ready_to_assign():
    # Money landing directly in a savings account (e.g. bank-synced interest)
    # never touches Ready to Assign.
    txns = [
        _txn(category_id=None, date=date(2026, 4, 3), amount_cents=100_000, on_budget=False),
    ]
    assert compute_ready_to_assign(txns, [], APRIL, PERSONAL) == 0


def test_off_budget_uncategorized_outflow_does_not_reduce_ready_to_assign():
    txns = [
        _txn(category_id=None, date=date(2026, 4, 1), amount_cents=100_000),
        _txn(category_id=None, date=date(2026, 4, 5), amount_cents=-40_000, on_budget=False),
    ]
    # The off-budget outflow is invisible, not subtracted.
    assert compute_ready_to_assign(txns, [], APRIL, PERSONAL) == 100_000


def test_same_scope_transfer_into_savings_reduces_ready_to_assign():
    # checking -> savings, same scope: the money leaves the on-budget pool,
    # so it must stop counting as available to assign even though the
    # transfer never crosses scopes.
    txns = [
        _txn(category_id=None, date=date(2026, 4, 1), amount_cents=100_000),
        _txn(
            category_id=None,
            date=date(2026, 4, 2),
            amount_cents=-60_000,
            transfer_peer_scope_id=PERSONAL,
            transfer_peer_on_budget=False,
        ),
        _txn(
            category_id=None,
            date=date(2026, 4, 2),
            amount_cents=60_000,
            transfer_peer_scope_id=PERSONAL,
            on_budget=False,
        ),
    ]
    assert compute_ready_to_assign(txns, [], APRIL, PERSONAL) == 40_000


def test_same_scope_transfer_from_savings_raises_ready_to_assign():
    # savings -> checking, same scope: money re-entering the on-budget pool
    # becomes available to assign again, per account_types.py's documented
    # design ("does not count... until it is transferred into an on-budget
    # account").
    txns = [
        _txn(category_id=None, date=date(2026, 4, 1), amount_cents=100_000, on_budget=False),
        _txn(
            category_id=None,
            date=date(2026, 4, 2),
            amount_cents=-60_000,
            transfer_peer_scope_id=PERSONAL,
            on_budget=False,
        ),
        _txn(
            category_id=None,
            date=date(2026, 4, 2),
            amount_cents=60_000,
            transfer_peer_scope_id=PERSONAL,
            transfer_peer_on_budget=False,
        ),
    ]
    assert compute_ready_to_assign(txns, [], APRIL, PERSONAL) == 60_000


def test_same_scope_transfer_between_two_on_budget_accounts_leaves_ready_to_assign_untouched():
    # checking -> credit card, both on-budget, same scope: money changing
    # accounts inside the pool, not entering or leaving it.
    txns = [
        _txn(category_id=None, date=date(2026, 4, 1), amount_cents=100_000),
        _txn(
            category_id=None,
            date=date(2026, 4, 2),
            amount_cents=-60_000,
            transfer_peer_scope_id=PERSONAL,
        ),
        _txn(
            category_id=None,
            date=date(2026, 4, 2),
            amount_cents=60_000,
            transfer_peer_scope_id=PERSONAL,
        ),
    ]
    assert compute_ready_to_assign(txns, [], APRIL, PERSONAL) == 100_000


def test_categorized_transaction_in_off_budget_account_still_reduces_category_balance():
    # Categorization is unaffected by on_budget — only uncategorized rows are
    # excluded from Ready to Assign.
    cat = 1
    txns = [
        _txn(category_id=cat, date=date(2026, 4, 5), amount_cents=-15_000, on_budget=False),
    ]
    assigns = [_assign(category_id=cat, month=APRIL, amount_cents=60_000)]
    balances = compute_category_balances([cat], txns, assigns, APRIL)
    b = balances[cat]
    assert b.activity_cents == -15_000
    assert b.balance_cents == 45_000


# --- Fund goals plan -----------------------------------------------------------


def test_fund_goals_plan_funds_everything_when_pool_covers_the_total():
    plan = compute_fund_goals_plan([(1, 10_000), (2, 20_000)], available_cents=50_000)
    assert [(e.category_id, e.needed_cents, e.amount_cents) for e in plan] == [
        (1, 10_000, 10_000),
        (2, 20_000, 20_000),
    ]


def test_fund_goals_plan_fills_sequentially_and_stops_when_pool_runs_out():
    # First category funded in full, second gets the remainder, third gets 0.
    plan = compute_fund_goals_plan(
        [(1, 10_000), (2, 20_000), (3, 15_000)], available_cents=25_000
    )
    assert [(e.category_id, e.needed_cents, e.amount_cents) for e in plan] == [
        (1, 10_000, 10_000),
        (2, 20_000, 15_000),
        (3, 15_000, 0),
    ]


def test_fund_goals_plan_excludes_categories_that_are_not_underfunded():
    plan = compute_fund_goals_plan([(1, 0), (2, -500), (3, 10_000)], available_cents=100_000)
    assert [e.category_id for e in plan] == [3]


def test_fund_goals_plan_treats_negative_pool_as_nothing_available():
    plan = compute_fund_goals_plan([(1, 10_000)], available_cents=-5_000)
    assert plan == [FundGoalsEntry(category_id=1, needed_cents=10_000, amount_cents=0)]


def test_fund_goals_plan_empty_input_yields_empty_plan():
    assert compute_fund_goals_plan([], available_cents=50_000) == []


def test_fund_goals_plan_never_exceeds_available_cents():
    plan = compute_fund_goals_plan(
        [(1, 10_000), (2, 20_000), (3, 15_000)], available_cents=25_000
    )
    assert sum(e.amount_cents for e in plan) == 25_000
