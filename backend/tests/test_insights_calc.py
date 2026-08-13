"""Pure-function tests for the insights math.

These pin the definitions the Insights page rests on: spending is gross with
refunds reported alongside, income is uncategorized inflow and nothing else,
"usual" is a median over whole months before the period, and the balance walk
agrees with ``budget_calc`` month for month.

The reconciliation tests at the bottom are load-bearing. ``insights_calc``
re-implements the rollover walk for speed; those tests are what stop it drifting
away from ``compute_category_balances``.
"""

from datetime import date

from app.services.budget_calc import AssignmentRow, TxnRow, compute_category_balances
from app.services.insights_calc import (
    ASSIGNED_ABOVE_USUAL,
    AVAILABLE_NEGATIVE,
    NEW_SPENDING,
    SPENT_ABOVE_USUAL,
    MonthRange,
    baseline_range,
    compute_category_trends,
    compute_spending_breakdown,
    flow_by_month,
    median_cents,
)

SCOPES = ("personal", "shared")
GROCERIES = 1
RENT = 2


def _month(year: int, month: int) -> date:
    return date(year, month, 1)


def _txn(
    *,
    category_id: int | None,
    date: date,
    amount_cents: int,
    scope: str = "personal",
    on_budget: bool = True,
    transfer_peer_scope: str | None = None,
    transfer_peer_on_budget: bool = True,
) -> TxnRow:
    return TxnRow(
        category_id=category_id,
        date=date,
        amount_cents=amount_cents,
        scope=scope,
        on_budget=on_budget,
        transfer_peer_scope=transfer_peer_scope,
        transfer_peer_on_budget=transfer_peer_on_budget,
    )


def _assign(
    *, category_id: int, month: date, amount_cents: int, scope: str = "personal"
) -> AssignmentRow:
    return AssignmentRow(
        category_id=category_id, month=month, amount_cents=amount_cents, scope=scope
    )


def _range(start: date, end: date) -> MonthRange:
    return MonthRange(start=start, end=end)


# ---------------------------------------------------------------------------
# Month ranges and baselines
# ---------------------------------------------------------------------------


def test_month_range_enumerates_every_month_inclusive():
    period = _range(_month(2026, 6), _month(2026, 8))
    assert period.month_count == 3
    assert period.months() == [_month(2026, 6), _month(2026, 7), _month(2026, 8)]


def test_single_month_range_holds_one_month():
    period = _range(_month(2026, 8), _month(2026, 8))
    assert period.month_count == 1
    assert period.months() == [_month(2026, 8)]


def test_month_range_spans_a_year_boundary():
    period = _range(_month(2025, 11), _month(2026, 2))
    assert period.month_count == 4
    assert period.months()[0] == _month(2025, 11)
    assert period.months()[-1] == _month(2026, 2)


def test_range_contains_every_day_of_its_last_month():
    period = _range(_month(2026, 6), _month(2026, 8))
    assert period.contains(date(2026, 8, 31))
    assert not period.contains(date(2026, 9, 1))
    assert not period.contains(date(2026, 5, 31))


def test_baseline_is_the_six_months_before_the_period():
    baseline = baseline_range(_range(_month(2026, 6), _month(2026, 8)))
    assert baseline.start == _month(2025, 12)
    assert baseline.end == _month(2026, 5)


def test_baseline_never_overlaps_the_period():
    period = _range(_month(2026, 1), _month(2026, 3))
    baseline = baseline_range(period)
    assert baseline.end < period.start
    assert baseline.start == _month(2025, 7)


# ---------------------------------------------------------------------------
# Median
# ---------------------------------------------------------------------------


def test_median_of_an_odd_count_is_the_middle_value():
    assert median_cents([100, 700, 200]) == 200


def test_median_of_an_even_count_averages_the_middle_pair():
    assert median_cents([100, 200, 300, 500]) == 250


def test_median_of_nothing_is_zero():
    assert median_cents([]) == 0


# ---------------------------------------------------------------------------
# Spending breakdown
# ---------------------------------------------------------------------------


def test_spending_is_reported_gross_with_refunds_alongside():
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(category_id=GROCERIES, date=date(2026, 4, 5), amount_cents=-40_000),
        _txn(category_id=GROCERIES, date=date(2026, 4, 9), amount_cents=3_000),
    ]

    spending = compute_spending_breakdown(
        transactions, period, {GROCERIES: "personal"}, SCOPES
    )

    groceries = spending["personal"].by_category[GROCERIES]
    assert groceries.spent_cents == 40_000
    assert groceries.refund_cents == 3_000
    assert groceries.activity_cents == -37_000


def test_a_refund_only_month_has_zero_spending_never_negative():
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(category_id=GROCERIES, date=date(2026, 4, 9), amount_cents=3_000)
    ]

    spending = compute_spending_breakdown(
        transactions, period, {GROCERIES: "personal"}, SCOPES
    )

    assert spending["personal"].by_category[GROCERIES].spent_cents == 0
    assert spending["personal"].total_spent_cents == 0


def test_uncategorized_outflow_never_counts_as_spending():
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(category_id=GROCERIES, date=date(2026, 4, 5), amount_cents=-40_000),
        _txn(category_id=None, date=date(2026, 4, 6), amount_cents=-5_000),
    ]

    spending = compute_spending_breakdown(
        transactions, period, {GROCERIES: "personal"}, SCOPES
    )

    assert set(spending["personal"].by_category) == {GROCERIES}
    assert spending["personal"].total_spent_cents == 40_000


def test_uncategorized_inflow_is_income_and_never_spending():
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(category_id=None, date=date(2026, 4, 1), amount_cents=250_000)
    ]

    spending = compute_spending_breakdown(transactions, period, {}, SCOPES)

    assert spending["personal"].total_spent_cents == 0


def test_scopes_are_reported_separately_and_never_merged():
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(category_id=GROCERIES, date=date(2026, 4, 5), amount_cents=-40_000),
        _txn(category_id=RENT, date=date(2026, 4, 5), amount_cents=-90_000, scope="shared"),
    ]

    spending = compute_spending_breakdown(
        transactions, period, {GROCERIES: "personal", RENT: "shared"}, SCOPES
    )

    assert spending["personal"].total_spent_cents == 40_000
    assert spending["shared"].total_spent_cents == 90_000
    assert RENT not in spending["personal"].by_category


def test_categorized_spending_follows_its_category_group_not_its_account():
    """The scope guard keeps these in step; deriving from the group is what makes
    Insights agree with the Budget page."""
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(
            category_id=RENT,
            date=date(2026, 4, 5),
            amount_cents=-90_000,
            scope="personal",
        )
    ]

    spending = compute_spending_breakdown(transactions, period, {RENT: "shared"}, SCOPES)

    assert spending["shared"].total_spent_cents == 90_000
    assert spending["personal"].total_spent_cents == 0


def test_uncategorized_off_budget_outflow_is_excluded_from_spending_breakdown():
    # An uncategorized withdrawal from a savings account never entered the
    # budget, so it must not appear as uncategorized spending either.
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(category_id=None, date=date(2026, 4, 6), amount_cents=-5_000, on_budget=False),
    ]

    spending = compute_spending_breakdown(transactions, period, {}, SCOPES)

    assert spending["personal"].total_spent_cents == 0


def test_uncategorized_off_budget_inflow_is_not_income():
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(category_id=None, date=date(2026, 4, 1), amount_cents=250_000, on_budget=False)
    ]

    spending = compute_spending_breakdown(transactions, period, {}, SCOPES)

    assert spending["personal"].total_spent_cents == 0


def test_categorized_activity_in_off_budget_account_still_counts_as_spending():
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(
            category_id=GROCERIES,
            date=date(2026, 4, 5),
            amount_cents=-40_000,
            on_budget=False,
        ),
    ]

    spending = compute_spending_breakdown(
        transactions, period, {GROCERIES: "personal"}, SCOPES
    )

    assert spending["personal"].by_category[GROCERIES].spent_cents == 40_000


def test_transactions_outside_the_period_are_excluded():
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(category_id=GROCERIES, date=date(2026, 3, 31), amount_cents=-10_000),
        _txn(category_id=GROCERIES, date=date(2026, 4, 15), amount_cents=-20_000),
        _txn(category_id=GROCERIES, date=date(2026, 5, 1), amount_cents=-30_000),
    ]

    spending = compute_spending_breakdown(
        transactions, period, {GROCERIES: "personal"}, SCOPES
    )

    assert spending["personal"].by_category[GROCERIES].spent_cents == 20_000


def test_an_empty_period_reports_zero_for_both_scopes():
    period = _range(_month(2026, 4), _month(2026, 4))

    spending = compute_spending_breakdown([], period, {}, SCOPES)

    assert spending["personal"].total_spent_cents == 0
    assert spending["shared"].total_spent_cents == 0


# ---------------------------------------------------------------------------
# Income vs spending
# ---------------------------------------------------------------------------


def test_every_month_gets_a_row_even_with_no_activity():
    period = _range(_month(2026, 4), _month(2026, 6))

    flows = flow_by_month([], period, "personal", {})

    assert [flow.month for flow in flows] == [
        _month(2026, 4),
        _month(2026, 5),
        _month(2026, 6),
    ]


def test_net_flow_equals_the_sum_of_every_amount_in_the_scope():
    """The identity holds when every euro is either income or categorized
    spending. Unassigned outgoing money breaks it by design — see
    test_uncategorized_outflow_is_excluded_from_net_flow."""
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(category_id=None, date=date(2026, 4, 1), amount_cents=250_000),
        _txn(category_id=GROCERIES, date=date(2026, 4, 5), amount_cents=-40_000),
        _txn(category_id=GROCERIES, date=date(2026, 4, 9), amount_cents=3_000),
    ]

    flow = flow_by_month(transactions, period, "personal", {GROCERIES: "personal"})[0]

    assert flow.income_cents == 250_000
    assert flow.spent_cents == 40_000
    assert flow.refund_cents == 3_000
    assert flow.net_cents == sum(txn.amount_cents for txn in transactions)


def test_uncategorized_outflow_is_excluded_from_net_flow():
    """Unassigned outgoing money never counts as spending, so it never
    reduces net cash flow either — real money can leave the account without
    net_cents reflecting it. That's the accepted cost of never treating
    uncategorized outflow as an expense."""
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(category_id=GROCERIES, date=date(2026, 4, 5), amount_cents=-40_000),
        _txn(category_id=None, date=date(2026, 4, 6), amount_cents=-5_000),
    ]

    flow = flow_by_month(transactions, period, "personal", {GROCERIES: "personal"})[0]

    assert flow.spent_cents == 40_000
    assert flow.income_cents == 0


def test_flows_are_isolated_per_scope():
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(category_id=None, date=date(2026, 4, 1), amount_cents=250_000),
        _txn(
            category_id=None, date=date(2026, 4, 1), amount_cents=90_000, scope="shared"
        ),
    ]

    assert flow_by_month(transactions, period, "personal", {})[0].income_cents == 250_000
    assert flow_by_month(transactions, period, "shared", {})[0].income_cents == 90_000


def test_flows_derive_scope_the_same_way_the_breakdown_does():
    """Both sections must agree about which pool a categorized euro belongs to."""
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(
            category_id=RENT,
            date=date(2026, 4, 5),
            amount_cents=-90_000,
            scope="personal",
        )
    ]

    assert flow_by_month(transactions, period, "shared", {RENT: "shared"})[
        0
    ].spent_cents == 90_000
    assert flow_by_month(transactions, period, "personal", {RENT: "shared"})[
        0
    ].spent_cents == 0


def test_monthly_spending_sums_to_the_breakdown_total():
    period = _range(_month(2026, 4), _month(2026, 6))
    transactions = [
        _txn(category_id=GROCERIES, date=date(2026, 4, 5), amount_cents=-40_000),
        _txn(category_id=GROCERIES, date=date(2026, 5, 5), amount_cents=-20_000),
        _txn(category_id=None, date=date(2026, 6, 5), amount_cents=-5_000),
    ]

    flows = flow_by_month(transactions, period, "personal", {GROCERIES: "personal"})
    spending = compute_spending_breakdown(
        transactions, period, {GROCERIES: "personal"}, SCOPES
    )

    assert sum(flow.spent_cents for flow in flows) == spending["personal"].total_spent_cents


def test_uncategorized_off_budget_inflow_contributes_no_income():
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(category_id=None, date=date(2026, 4, 1), amount_cents=250_000, on_budget=False),
    ]

    flow = flow_by_month(transactions, period, "personal", {})[0]

    assert flow.income_cents == 0
    assert flow.spent_cents == 0
    assert flow.refund_cents == 0


def test_same_scope_transfer_between_two_on_budget_accounts_is_not_income():
    # checking -> credit card: money changing accounts inside the pool, not
    # entering it, so the inflow leg must not read as income.
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(
            category_id=None,
            date=date(2026, 4, 2),
            amount_cents=60_000,
            transfer_peer_scope="personal",
        ),
    ]

    flow = flow_by_month(transactions, period, "personal", {})[0]

    assert flow.income_cents == 0


def test_same_scope_transfer_from_savings_into_checking_is_income():
    # savings -> checking: this leg is money entering the on-budget pool for
    # the first time, matching budget_calc.feeds_ready_to_assign.
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(
            category_id=None,
            date=date(2026, 4, 2),
            amount_cents=60_000,
            transfer_peer_scope="personal",
            transfer_peer_on_budget=False,
        ),
    ]

    flow = flow_by_month(transactions, period, "personal", {})[0]

    assert flow.income_cents == 60_000


def test_uncategorized_off_budget_outflow_is_excluded_not_counted_as_spent():
    # The pitfall this guards against: without excluding the row outright, a
    # negative uncategorized off-budget amount would fall through into the
    # ordinary "spent" branch once _is_income rejects it.
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(category_id=None, date=date(2026, 4, 6), amount_cents=-5_000, on_budget=False),
    ]

    flow = flow_by_month(transactions, period, "personal", {})[0]

    assert flow.spent_cents == 0
    assert flow.income_cents == 0
    assert flow.refund_cents == 0


def test_categorized_activity_in_off_budget_account_still_flows_normally():
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(
            category_id=GROCERIES,
            date=date(2026, 4, 5),
            amount_cents=-40_000,
            on_budget=False,
        ),
    ]

    flow = flow_by_month(transactions, period, "personal", {GROCERIES: "personal"})[0]

    assert flow.spent_cents == 40_000


# ---------------------------------------------------------------------------
# Trends: baselines and flags
# ---------------------------------------------------------------------------


def _steady_spending(amount_cents: int, months: list[date]) -> list[TxnRow]:
    return [
        _txn(category_id=GROCERIES, date=month, amount_cents=-amount_cents)
        for month in months
    ]


def _funding(amount_cents: int, months: list[date]) -> list[AssignmentRow]:
    """Assignments that exactly cover the matching spending, so a test about
    baselines isn't also tripping the negative-balance flag."""
    return [
        _assign(category_id=GROCERIES, month=month, amount_cents=amount_cents)
        for month in months
    ]


BASELINE_MONTHS = [_month(2025, 10 + offset) for offset in range(3)] + [
    _month(2026, 1 + offset) for offset in range(3)
]
PERIOD = _range(_month(2026, 4), _month(2026, 4))


def test_baseline_is_the_median_not_the_mean():
    """Five ordinary months plus one annual bill must not move the norm."""
    transactions = _steady_spending(10_000, BASELINE_MONTHS[:5]) + [
        _txn(category_id=GROCERIES, date=BASELINE_MONTHS[5], amount_cents=-70_000)
    ]

    trend = compute_category_trends([GROCERIES], transactions, [], PERIOD)[GROCERIES]

    assert trend.expected_spent_cents == 10_000


def test_quiet_months_inside_the_observed_span_count_as_zero():
    transactions = _steady_spending(10_000, BASELINE_MONTHS[:2])

    trend = compute_category_trends([GROCERIES], transactions, [], PERIOD)[GROCERIES]

    # Two spending months, four silent ones after the category first appeared:
    # the median of [10000, 10000, 0, 0, 0, 0] is 0.
    assert trend.baseline_month_count == 6
    assert trend.expected_spent_cents == 0


def test_months_before_a_category_existed_are_not_counted():
    transactions = _steady_spending(10_000, BASELINE_MONTHS[4:])

    trend = compute_category_trends([GROCERIES], transactions, [], PERIOD)[GROCERIES]

    assert trend.baseline_month_count == 2


def test_a_category_with_too_little_history_has_no_baseline():
    transactions = _steady_spending(10_000, BASELINE_MONTHS[5:]) + _steady_spending(
        50_000, [date(2026, 4, 5)]
    )
    assignments = _funding(10_000, BASELINE_MONTHS[5:]) + _funding(
        50_000, [_month(2026, 4)]
    )

    trend = compute_category_trends([GROCERIES], transactions, assignments, PERIOD)[
        GROCERIES
    ]

    assert not trend.has_baseline
    assert trend.expected_spent_cents is None
    assert trend.spent_delta_pct is None
    assert trend.flags == ()


def test_spending_more_than_ten_percent_above_usual_is_flagged():
    transactions = _steady_spending(10_000, BASELINE_MONTHS) + [
        _txn(category_id=GROCERIES, date=date(2026, 4, 5), amount_cents=-12_000)
    ]

    trend = compute_category_trends([GROCERIES], transactions, [], PERIOD)[GROCERIES]

    assert trend.expected_spent_cents == 10_000
    assert trend.spent_delta_cents == 2_000
    assert trend.spent_delta_pct == 20.0
    assert SPENT_ABOVE_USUAL in trend.flags


def test_exactly_ten_percent_above_usual_does_not_flag():
    transactions = _steady_spending(10_000, BASELINE_MONTHS) + [
        _txn(category_id=GROCERIES, date=date(2026, 4, 5), amount_cents=-11_000)
    ]
    assignments = _funding(10_000, BASELINE_MONTHS) + _funding(
        11_000, [_month(2026, 4)]
    )

    trend = compute_category_trends([GROCERIES], transactions, assignments, PERIOD)[
        GROCERIES
    ]

    assert trend.spent_delta_pct == 10.0
    assert trend.flags == ()


def test_a_small_category_needs_a_notable_amount_not_just_a_percentage():
    """10% of a €20 habit is two euros — not worth interrupting anyone over."""
    transactions = _steady_spending(2_000, BASELINE_MONTHS) + [
        _txn(category_id=GROCERIES, date=date(2026, 4, 5), amount_cents=-2_600)
    ]
    assignments = _funding(2_000, BASELINE_MONTHS) + _funding(2_600, [_month(2026, 4)])

    trend = compute_category_trends([GROCERIES], transactions, assignments, PERIOD)[
        GROCERIES
    ]

    assert trend.spent_delta_pct == 30.0
    assert trend.flags == ()


def test_a_small_category_over_by_a_notable_amount_is_flagged():
    transactions = _steady_spending(2_000, BASELINE_MONTHS) + [
        _txn(category_id=GROCERIES, date=date(2026, 4, 5), amount_cents=-3_100)
    ]
    assignments = _funding(2_000, BASELINE_MONTHS) + _funding(3_100, [_month(2026, 4)])

    trend = compute_category_trends([GROCERIES], transactions, assignments, PERIOD)[
        GROCERIES
    ]

    assert SPENT_ABOVE_USUAL in trend.flags


def test_the_notable_floor_scales_with_the_length_of_the_period():
    """€10 a month, so a three-month range needs €30 before it counts."""
    period = _range(_month(2026, 4), _month(2026, 6))
    period_months = [_month(2026, 4), _month(2026, 5), _month(2026, 6)]
    transactions = _steady_spending(2_000, BASELINE_MONTHS) + _steady_spending(
        2_900, period_months
    )
    assignments = _funding(2_000, BASELINE_MONTHS) + _funding(2_900, period_months)

    trend = compute_category_trends([GROCERIES], transactions, assignments, period)[
        GROCERIES
    ]

    # €87 against a €60 norm is +45%, but only €27 over three months.
    assert trend.spent_delta_cents == 2_700
    assert trend.flags == ()


def test_a_large_category_still_flags_on_the_percentage_alone():
    transactions = _steady_spending(50_000, BASELINE_MONTHS) + [
        _txn(category_id=GROCERIES, date=date(2026, 4, 5), amount_cents=-56_000)
    ]
    assignments = _funding(50_000, BASELINE_MONTHS) + _funding(
        56_000, [_month(2026, 4)]
    )

    trend = compute_category_trends([GROCERIES], transactions, assignments, PERIOD)[
        GROCERIES
    ]

    assert trend.spent_delta_pct == 12.0
    assert SPENT_ABOVE_USUAL in trend.flags


def test_a_trivial_dip_into_the_red_is_not_flagged():
    period = _range(_month(2026, 4), _month(2026, 4))
    assignments = [
        _assign(category_id=GROCERIES, month=_month(2026, 4), amount_cents=24_700)
    ]
    transactions = [
        _txn(category_id=GROCERIES, date=date(2026, 4, 5), amount_cents=-25_000)
    ]

    trend = compute_category_trends([GROCERIES], transactions, assignments, period)[
        GROCERIES
    ]

    assert trend.worst_balance_cents == -300
    assert trend.worst_balance_month is None
    assert trend.flags == ()


def test_a_dormant_category_needs_notable_spending_to_count_as_new():
    assignments = [
        _assign(category_id=GROCERIES, month=month, amount_cents=10_000)
        for month in BASELINE_MONTHS
    ] + _funding(10_000, [_month(2026, 4)])
    transactions = [
        _txn(category_id=GROCERIES, date=date(2026, 4, 5), amount_cents=-200)
    ]

    trend = compute_category_trends([GROCERIES], transactions, assignments, PERIOD)[
        GROCERIES
    ]

    assert trend.expected_spent_cents == 0
    assert NEW_SPENDING not in trend.flags


def test_spending_below_usual_is_not_flagged():
    transactions = _steady_spending(10_000, BASELINE_MONTHS) + [
        _txn(category_id=GROCERIES, date=date(2026, 4, 5), amount_cents=-5_000)
    ]
    assignments = _funding(10_000, BASELINE_MONTHS) + _funding(5_000, [_month(2026, 4)])

    trend = compute_category_trends([GROCERIES], transactions, assignments, PERIOD)[
        GROCERIES
    ]

    assert trend.flags == ()


def test_assignment_and_spending_flag_independently():
    assignments = [
        _assign(category_id=GROCERIES, month=month, amount_cents=10_000)
        for month in BASELINE_MONTHS
    ] + [_assign(category_id=GROCERIES, month=_month(2026, 4), amount_cents=15_000)]
    transactions = _steady_spending(10_000, BASELINE_MONTHS) + [
        _txn(category_id=GROCERIES, date=date(2026, 4, 5), amount_cents=-10_000)
    ]

    trend = compute_category_trends([GROCERIES], transactions, assignments, PERIOD)[
        GROCERIES
    ]

    assert ASSIGNED_ABOVE_USUAL in trend.flags
    assert SPENT_ABOVE_USUAL not in trend.flags


def test_spending_in_a_long_dormant_category_is_flagged_as_new():
    assignments = [
        _assign(category_id=GROCERIES, month=month, amount_cents=10_000)
        for month in BASELINE_MONTHS
    ]
    transactions = [
        _txn(category_id=GROCERIES, date=date(2026, 4, 5), amount_cents=-3_000)
    ]

    trend = compute_category_trends([GROCERIES], transactions, assignments, PERIOD)[
        GROCERIES
    ]

    assert trend.expected_spent_cents == 0
    assert trend.spent_delta_pct is None
    assert NEW_SPENDING in trend.flags


def test_a_multi_month_period_is_compared_against_the_scaled_baseline():
    """Three months at the usual rate is not a 200% overshoot."""
    period = _range(_month(2026, 4), _month(2026, 6))
    period_months = [_month(2026, 4), _month(2026, 5), _month(2026, 6)]
    transactions = _steady_spending(10_000, BASELINE_MONTHS) + _steady_spending(
        10_000, period_months
    )
    assignments = _funding(10_000, BASELINE_MONTHS) + _funding(10_000, period_months)

    trend = compute_category_trends([GROCERIES], transactions, assignments, period)[
        GROCERIES
    ]

    assert trend.expected_spent_cents == 30_000
    assert trend.spent_cents == 30_000
    assert trend.spent_delta_pct == 0.0
    assert trend.flags == ()


def test_a_balance_that_dips_negative_mid_period_is_flagged_with_its_month():
    period = _range(_month(2026, 4), _month(2026, 6))
    assignments = [
        _assign(category_id=GROCERIES, month=_month(2026, 4), amount_cents=10_000),
        _assign(category_id=GROCERIES, month=_month(2026, 6), amount_cents=30_000),
    ]
    transactions = [
        _txn(category_id=GROCERIES, date=date(2026, 5, 5), amount_cents=-25_000)
    ]

    trend = compute_category_trends([GROCERIES], transactions, assignments, period)[
        GROCERIES
    ]

    assert trend.worst_balance_cents == -15_000
    assert trend.worst_balance_month == _month(2026, 5)
    assert AVAILABLE_NEGATIVE in trend.flags


def test_a_negative_balance_is_flagged_even_without_a_baseline():
    period = _range(_month(2026, 4), _month(2026, 4))
    transactions = [
        _txn(category_id=GROCERIES, date=date(2026, 4, 5), amount_cents=-25_000)
    ]

    trend = compute_category_trends([GROCERIES], transactions, [], period)[GROCERIES]

    assert not trend.has_baseline
    assert trend.flags == (AVAILABLE_NEGATIVE,)


def test_a_balance_that_stays_positive_reports_no_worst_month():
    period = _range(_month(2026, 4), _month(2026, 4))
    assignments = [
        _assign(category_id=GROCERIES, month=_month(2026, 4), amount_cents=30_000)
    ]
    transactions = [
        _txn(category_id=GROCERIES, date=date(2026, 4, 5), amount_cents=-25_000)
    ]

    trend = compute_category_trends([GROCERIES], transactions, assignments, period)[
        GROCERIES
    ]

    assert trend.worst_balance_cents == 5_000
    assert trend.worst_balance_month is None
    assert AVAILABLE_NEGATIVE not in trend.flags


def test_the_balance_walk_carries_rollover_from_before_the_period():
    period = _range(_month(2026, 4), _month(2026, 4))
    assignments = [
        _assign(category_id=GROCERIES, month=_month(2026, 3), amount_cents=30_000)
    ]
    transactions = [
        _txn(category_id=GROCERIES, date=date(2026, 4, 5), amount_cents=-25_000)
    ]

    trend = compute_category_trends([GROCERIES], transactions, assignments, period)[
        GROCERIES
    ]

    assert trend.worst_balance_cents == 5_000


# ---------------------------------------------------------------------------
# Reconciliation with budget_calc — do not delete
# ---------------------------------------------------------------------------


def _reconciliation_fixture() -> tuple[list[TxnRow], list[AssignmentRow]]:
    months = [_month(2026, 1 + offset) for offset in range(6)]
    assignments = [
        _assign(category_id=GROCERIES, month=month, amount_cents=40_000)
        for month in months
    ] + [
        _assign(category_id=RENT, month=month, amount_cents=90_000) for month in months
    ]
    transactions = [
        _txn(category_id=GROCERIES, date=date(month.year, month.month, 12), amount_cents=-35_000)
        for month in months
    ] + [
        _txn(category_id=RENT, date=date(month.year, month.month, 3), amount_cents=-92_000)
        for month in months
    ] + [
        _txn(category_id=GROCERIES, date=date(2026, 3, 20), amount_cents=4_000),
    ]
    return transactions, assignments


def test_month_end_balances_match_compute_category_balances():
    transactions, assignments = _reconciliation_fixture()

    for offset in range(6):
        month = _month(2026, 1 + offset)
        period = _range(month, month)
        trends = compute_category_trends(
            [GROCERIES, RENT], transactions, assignments, period
        )
        balances = compute_category_balances(
            [GROCERIES, RENT], transactions, assignments, month
        )
        for category_id in (GROCERIES, RENT):
            assert trends[category_id].worst_balance_cents == balances[
                category_id
            ].balance_cents


def test_period_activity_matches_the_sum_of_monthly_budget_activity():
    transactions, assignments = _reconciliation_fixture()
    period = _range(_month(2026, 1), _month(2026, 6))

    spending = compute_spending_breakdown(
        transactions, period, {GROCERIES: "personal", RENT: "personal"}, SCOPES
    )

    for category_id in (GROCERIES, RENT):
        monthly_activity = sum(
            compute_category_balances(
                [category_id], transactions, assignments, _month(2026, 1 + offset)
            )[category_id].activity_cents
            for offset in range(6)
        )
        assert spending["personal"].by_category[category_id].activity_cents == monthly_activity


def test_period_assigned_matches_the_sum_of_monthly_budget_assigned():
    transactions, assignments = _reconciliation_fixture()
    period = _range(_month(2026, 1), _month(2026, 6))

    trends = compute_category_trends(
        [GROCERIES, RENT], transactions, assignments, period
    )

    for category_id in (GROCERIES, RENT):
        monthly_assigned = sum(
            compute_category_balances(
                [category_id], transactions, assignments, _month(2026, 1 + offset)
            )[category_id].assigned_cents
            for offset in range(6)
        )
        assert trends[category_id].assigned_cents == monthly_assigned
