"""Spending-insights math.

This module answers three questions about a window of months:

- **Where did the money go** — spending per category, group and scope.
- **Income vs spending** — what came in against what went out, month by month.
- **What wasn't planned for** — categories funded or spent well above their
  recent norm, plus any category whose Available balance dipped below zero.

Like ``budget_calc``, everything here is pure over its inputs so it can be
unit-tested without a database — see ``tests/test_insights_calc.py``. It reuses
``budget_calc``'s ``TxnRow`` / ``AssignmentRow``, which already carry the scope
their router joined in.

It deliberately does **not** call ``compute_category_balances``: that function is
O(categories x transactions) per month, and Insights walks up to eighteen months
(a twelve-month range plus its six-month baseline). Instead rows are bucketed by
(category, month) once and the month axis is walked per category. The balance
walk reproduces ``budget_calc``'s rollover semantics, and
``test_insights_calc.py`` pins the two against each other month by month — those
reconciliation tests are load-bearing, not extra coverage.

Unassigned (``category_id IS NULL``) outgoing money never counts as spending,
regardless of whether it is a transfer, which scope it crosses, or just a
purchase nobody has categorized yet — the user would rather it disappear from
"Spent" than have it mislabeled as an expense. Unassigned incoming money is
the opposite: it is income (``_is_income``), the sole source of Ready to
Assign, unless it is a same-scope transfer leg recycling the pool's own money
back to itself — that split still matters and mirrors
``budget_calc.feeds_ready_to_assign``; see ``_is_internal_transfer``.

TODO: this blanket exclusion leans on the assumption that most unassigned
outflow is really transfers. ``services/transfer_match.py`` has a matching
TODO for a persisted lookup/linking table to identify transfer pairs more
reliably than today's stateless heuristic — that would let this exclusion
become precise instead of blanket.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from app.services.budget_calc import AssignmentRow, TxnRow, month_start, next_month_start

# How many months before the selected window define a category's "usual" level.
# Long enough to smooth a quarterly bill, short enough to follow a real change in
# circumstances. Twelve would straddle rent rises and job changes.
BASELINE_WINDOW_MONTHS = 6
# The smallest count where a median is genuinely a middle value. Below this a
# category has no norm worth comparing against.
MIN_BASELINE_MONTHS = 3
# How far above the norm counts as "not planned for".
OVERSPEND_THRESHOLD_PCT = 10.0
# The smallest amount of money worth drawing attention to. A bare percentage
# rule is too twitchy at the small end — 10% of a €20 habit is two euros — and a
# bare euro floor is meaningless at the large end. Every flag therefore needs
# both: the percentage governs big categories, this floor governs small ones.
MIN_NOTABLE_CENTS = 1_000

SPENT_ABOVE_USUAL = "spent_above_usual"
ASSIGNED_ABOVE_USUAL = "assigned_above_usual"
NEW_SPENDING = "new_spending"
AVAILABLE_NEGATIVE = "available_negative"


@dataclass(frozen=True)
class MonthRange:
    """An inclusive span of whole months, both bounds first-of-month dates."""

    start: date
    end: date

    @property
    def month_count(self) -> int:
        return _month_index(self.end) - _month_index(self.start) + 1

    def months(self) -> list[date]:
        return [
            _month_from_index(index)
            for index in range(_month_index(self.start), _month_index(self.end) + 1)
        ]

    def contains(self, day: date) -> bool:
        return self.start <= day < next_month_start(self.end)


def baseline_range(period: MonthRange, window_months: int = BASELINE_WINDOW_MONTHS) -> MonthRange:
    """The whole months immediately preceding ``period``.

    Never overlaps ``period``: a window that included the months it judges would
    let a blowout raise its own bar and hide itself.
    """
    end_index = _month_index(period.start) - 1
    return MonthRange(
        start=_month_from_index(end_index - window_months + 1),
        end=_month_from_index(end_index),
    )


def _month_index(first_of_month: date) -> int:
    return first_of_month.year * 12 + (first_of_month.month - 1)


def _month_from_index(index: int) -> date:
    return date(index // 12, index % 12 + 1, 1)


def _is_income(txn: TxnRow) -> bool:
    """Uncategorized inflow is the sole source of Ready to Assign, and so the
    only thing that counts as income (ROADMAP invariant 6). A categorized inflow
    is a refund. Off-budget (savings) inflow is excluded the same way
    ``budget_calc.feeds_ready_to_assign`` excludes it — it never reached Ready
    to Assign in the first place."""
    return txn.category_id is None and txn.amount_cents > 0 and txn.on_budget


def _is_internal_transfer(txn: TxnRow) -> bool:
    """A transfer whose two legs sit in the same scope *and* the same
    on-budget status — money moving between the user's own accounts inside
    one pool, not into or out of it. Relevant only to the income side:
    without this check a same-scope transfer's inflow leg would misread as
    income. The outflow leg needs no such check — all unassigned outflow is
    already excluded from spending regardless of scope. Cross-scope legs, and
    same-scope legs that cross the on-budget/off-budget boundary (e.g. a
    transfer back from savings into checking), are real movements into a
    pool, so their inflow leg is left in, matching
    ``budget_calc.feeds_ready_to_assign``.
    """
    return txn.transfer_peer_scope == txn.scope and txn.transfer_peer_on_budget == txn.on_budget


def _scope_of(txn: TxnRow, category_scope: dict[int, str]) -> str | None:
    """Which pool a transaction belongs to.

    Categorized rows take the scope of their **category's group**, not their
    account: ``_enforce_scope_match`` keeps those in step, and deriving from the
    group makes Insights agree with the Budget page by construction.
    Uncategorized rows have only their account scope to go on.
    """
    if txn.category_id is None:
        return txn.scope
    return category_scope.get(txn.category_id)


@dataclass(frozen=True)
class CategorySpending:
    spent_cents: int  # gross outflow, >= 0
    refund_cents: int  # categorized inflow, >= 0

    @property
    def activity_cents(self) -> int:
        """Signed, matching ``budget_calc.CategoryBalance.activity_cents``."""
        return self.refund_cents - self.spent_cents


@dataclass(frozen=True)
class ScopeSpending:
    scope: str
    by_category: dict[int, CategorySpending]

    @property
    def total_spent_cents(self) -> int:
        return sum(spend.spent_cents for spend in self.by_category.values())


def compute_spending_breakdown(
    transactions: list[TxnRow],
    period: MonthRange,
    category_scope: dict[int, str],
    scopes: tuple[str, ...],
) -> dict[str, ScopeSpending]:
    """Spending per category over ``period``, one entry per scope in ``scopes``.

    Spending is reported **gross**, with refunds alongside rather than netted in.
    A floored net would not sum: a refund landing in a different month from its
    purchase makes the range total disagree with the sum of its months. Gross
    outflow adds up across months, categories, groups and scopes and is never
    negative, so stacked bars and shares always mean something; ``activity_cents``
    is there when a signed figure is needed.
    """
    spent: dict[tuple[str, int], int] = {}
    refunded: dict[tuple[str, int], int] = {}

    for txn in transactions:
        if not period.contains(txn.date):
            continue
        if txn.category_id is None:
            # Unassigned money never appears in the spending breakdown:
            # outflow never counts as an expense, and inflow is income
            # (handled in flow_by_month), not spend.
            continue
        scope = _scope_of(txn, category_scope)
        if scope not in scopes:
            continue
        key = (scope, txn.category_id)
        if txn.amount_cents < 0:
            spent[key] = spent.get(key, 0) - txn.amount_cents
        else:
            refunded[key] = refunded.get(key, 0) + txn.amount_cents

    breakdown: dict[str, ScopeSpending] = {}
    for scope in scopes:
        category_ids = {
            category_id for (row_scope, category_id) in (*spent, *refunded) if row_scope == scope
        }
        breakdown[scope] = ScopeSpending(
            scope=scope,
            by_category={
                category_id: CategorySpending(
                    spent_cents=spent.get((scope, category_id), 0),
                    refund_cents=refunded.get((scope, category_id), 0),
                )
                for category_id in category_ids
            },
        )
    return breakdown


@dataclass(frozen=True)
class MonthFlow:
    month: date
    income_cents: int  # uncategorized inflow, >= 0
    spent_cents: int  # gross outflow, >= 0
    refund_cents: int  # categorized inflow, >= 0

    @property
    def net_cents(self) -> int:
        """Income plus refunds minus spending. This is the scope's true cash
        flow only once every euro is either categorized or counted as income —
        unassigned outgoing money is never spending (see the module
        docstring), so real money leaving the account uncategorized will not
        show up here either."""
        return self.income_cents + self.refund_cents - self.spent_cents


def flow_by_month(
    transactions: list[TxnRow],
    period: MonthRange,
    scope: str,
    category_scope: dict[int, str],
) -> list[MonthFlow]:
    """Income against spending for every month in ``period``, for one scope.

    Scope is derived exactly as in ``compute_spending_breakdown`` — categorized
    rows follow their category's group, uncategorized rows their account — so
    the two sections can never disagree about which pool a euro belongs to.

    Months with no activity still get a row, or the chart's month axis develops
    gaps.
    """
    months = period.months()
    income: dict[date, int] = {month: 0 for month in months}
    spent: dict[date, int] = {month: 0 for month in months}
    refunded: dict[date, int] = {month: 0 for month in months}

    for txn in transactions:
        if _scope_of(txn, category_scope) != scope or _is_internal_transfer(txn):
            continue
        if txn.category_id is None and (txn.amount_cents < 0 or not txn.on_budget):
            # Unassigned outflow never counts as spending (see the identical
            # guard in compute_spending_breakdown), and unassigned off-budget
            # inflow never reached Ready to Assign, so neither is reclassified
            # here — both are excluded entirely.
            continue
        bucket = month_start(txn.date)
        if bucket not in income:
            continue
        if _is_income(txn):
            income[bucket] += txn.amount_cents
        elif txn.amount_cents < 0:
            spent[bucket] -= txn.amount_cents
        else:
            refunded[bucket] += txn.amount_cents

    return [
        MonthFlow(
            month=month,
            income_cents=income[month],
            spent_cents=spent[month],
            refund_cents=refunded[month],
        )
        for month in months
    ]


@dataclass(frozen=True)
class CategoryTrend:
    category_id: int
    assigned_cents: int
    expected_assigned_cents: int | None
    assigned_delta_cents: int | None
    assigned_delta_pct: float | None
    spent_cents: int
    expected_spent_cents: int | None
    spent_delta_cents: int | None
    spent_delta_pct: float | None
    baseline_month_count: int
    worst_balance_cents: int
    worst_balance_month: date | None  # None when the balance never went negative
    flags: tuple[str, ...]

    @property
    def has_baseline(self) -> bool:
        return self.baseline_month_count >= MIN_BASELINE_MONTHS


def compute_category_trends(
    category_ids: list[int],
    transactions: list[TxnRow],
    assignments: list[AssignmentRow],
    period: MonthRange,
    window_months: int = BASELINE_WINDOW_MONTHS,
) -> dict[int, CategoryTrend]:
    """Per-category assignment and spending against their recent norm.

    The norm is the **median** per-month value over the ``window_months`` before
    ``period``. Median, not mean: budget data is spiky, and a single annual
    insurance payment inside the window would multiply a mean by six and make
    every ordinary month read as far below usual. Where a category is funded
    identically every month — the common case, since goals are mandatory — the
    two coincide, so nothing is lost.

    Only months at or after a category's first activity count towards its
    baseline: a month you had the category and spent nothing is real data and
    must count as zero, but months before it existed are absent, not zero.

    Scope-agnostic, like ``compute_category_balances`` — the caller narrows
    ``category_ids`` to one pool.
    """
    baseline = baseline_range(period, window_months)
    period_months = period.months()
    baseline_months = baseline.months()

    assigned_by_month = _fold(
        (row.category_id, month_start(row.month), row.amount_cents) for row in assignments
    )
    activity_by_month = _fold(
        (txn.category_id, month_start(txn.date), txn.amount_cents)
        for txn in transactions
        if txn.category_id is not None
    )
    spent_by_month = _fold(
        (txn.category_id, month_start(txn.date), -txn.amount_cents)
        for txn in transactions
        if txn.category_id is not None and txn.amount_cents < 0
    )
    first_seen = _first_seen_month(assigned_by_month, activity_by_month)
    opening = _opening_balances(assigned_by_month, activity_by_month, period.start)

    trends: dict[int, CategoryTrend] = {}
    for category_id in category_ids:
        observed = _observed_baseline_months(baseline_months, first_seen.get(category_id))

        assigned_cents = _total(assigned_by_month, category_id, period_months)
        spent_cents = _total(spent_by_month, category_id, period_months)

        expected_assigned = _expected(
            assigned_by_month, category_id, observed, period.month_count
        )
        expected_spent = _expected(spent_by_month, category_id, observed, period.month_count)

        worst_balance, worst_month = _worst_balance(
            assigned_by_month,
            activity_by_month,
            category_id,
            period,
            opening.get(category_id, 0),
        )

        trends[category_id] = CategoryTrend(
            category_id=category_id,
            assigned_cents=assigned_cents,
            expected_assigned_cents=expected_assigned,
            assigned_delta_cents=_delta_cents(assigned_cents, expected_assigned),
            assigned_delta_pct=_delta_pct(assigned_cents, expected_assigned),
            spent_cents=spent_cents,
            expected_spent_cents=expected_spent,
            spent_delta_cents=_delta_cents(spent_cents, expected_spent),
            spent_delta_pct=_delta_pct(spent_cents, expected_spent),
            baseline_month_count=len(observed),
            worst_balance_cents=worst_balance,
            worst_balance_month=worst_month,
            flags=_flags(
                assigned_cents=assigned_cents,
                expected_assigned=expected_assigned,
                spent_cents=spent_cents,
                expected_spent=expected_spent,
                baseline_month_count=len(observed),
                worst_balance_cents=worst_balance,
                period_month_count=period.month_count,
            ),
        )
    return trends


def median_cents(values: list[int]) -> int:
    """The middle value, averaging the middle pair on an even count."""
    if not values:
        return 0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) // 2


def _fold(rows: Iterable[tuple[int, date, int]]) -> dict[tuple[int, date], int]:
    """Fold (category, month, amount) triples into one bucket per pair, so the
    per-category passes stay linear in the number of rows."""
    totals: dict[tuple[int, date], int] = {}
    for category_id, month, amount in rows:
        key = (category_id, month)
        totals[key] = totals.get(key, 0) + amount
    return totals


def _first_seen_month(
    assigned: dict[tuple[int, date], int], activity: dict[tuple[int, date], int]
) -> dict[int, date]:
    first: dict[int, date] = {}
    for category_id, month in (*assigned, *activity):
        known = first.get(category_id)
        if known is None or month < known:
            first[category_id] = month
    return first


def _observed_baseline_months(
    baseline_months: list[date], first_seen: date | None
) -> list[date]:
    if first_seen is None:
        return []
    return [month for month in baseline_months if month >= first_seen]


def _total(
    totals: dict[tuple[int, date], int], category_id: int, months: list[date]
) -> int:
    return sum(totals.get((category_id, month), 0) for month in months)


def _expected(
    totals: dict[tuple[int, date], int],
    category_id: int,
    observed_months: list[date],
    period_month_count: int,
) -> int | None:
    """The norm scaled to the length of the selected period.

    Scaling the baseline up rather than averaging the period down keeps the delta
    a real euro figure the user can act on — "€92 more than usual over these
    three months" beats an averaged abstraction.
    """
    if len(observed_months) < MIN_BASELINE_MONTHS:
        return None
    per_month = median_cents(
        [totals.get((category_id, month), 0) for month in observed_months]
    )
    return per_month * period_month_count


def _delta_cents(actual_cents: int, expected_cents: int | None) -> int | None:
    if expected_cents is None:
        return None
    return actual_cents - expected_cents


def _delta_pct(actual_cents: int, expected_cents: int | None) -> float | None:
    """How far above the norm a figure sits. ``None`` when there is no positive
    norm to divide by — the caller renders that as "new" rather than infinity."""
    if expected_cents is None or expected_cents <= 0:
        return None
    return (actual_cents - expected_cents) / expected_cents * 100.0


def _opening_balances(
    assigned: dict[tuple[int, date], int],
    activity: dict[tuple[int, date], int],
    period_start: date,
) -> dict[int, int]:
    """Each category's rolled-forward balance on the eve of ``period_start``."""
    opening: dict[int, int] = {}
    for buckets in (assigned, activity):
        for (category_id, month), amount in buckets.items():
            if month < period_start:
                opening[category_id] = opening.get(category_id, 0) + amount
    return opening


def _worst_balance(
    assigned: dict[tuple[int, date], int],
    activity: dict[tuple[int, date], int],
    category_id: int,
    period: MonthRange,
    opening_cents: int,
) -> tuple[int, date | None]:
    """Walk month-end balances across ``period``, reporting the lowest.

    "Went negative" means dipped: a category that blew up in March and was
    covered in April still deserves the mention. Rollover from before the period
    is included, matching ``compute_category_balances``.

    The month is only reported when the dip clears ``dipped_negative``, so the
    figure the UI shows and the flag it shows it for always agree.
    """
    balance = opening_cents
    worst = balance
    worst_month = period.start
    for month in period.months():
        balance += assigned.get((category_id, month), 0) + activity.get((category_id, month), 0)
        if balance < worst or month == period.start:
            worst = balance
            worst_month = month
    return worst, worst_month if dipped_negative(worst) else None


def _flags(
    *,
    assigned_cents: int,
    expected_assigned: int | None,
    spent_cents: int,
    expected_spent: int | None,
    baseline_month_count: int,
    worst_balance_cents: int,
    period_month_count: int,
) -> tuple[str, ...]:
    flags: list[str] = []
    if baseline_month_count >= MIN_BASELINE_MONTHS:
        if _above_norm(spent_cents, expected_spent, period_month_count):
            flags.append(SPENT_ABOVE_USUAL)
        elif expected_spent == 0 and spent_cents >= MIN_NOTABLE_CENTS:
            flags.append(NEW_SPENDING)
        if _above_norm(assigned_cents, expected_assigned, period_month_count):
            flags.append(ASSIGNED_ABOVE_USUAL)
    if dipped_negative(worst_balance_cents):
        flags.append(AVAILABLE_NEGATIVE)
    return tuple(flags)


def _above_norm(
    actual_cents: int, expected_cents: int | None, period_month_count: int
) -> bool:
    """Above the norm by both a proportion and an amount worth mentioning.

    The trigger is ``max(MIN_NOTABLE_CENTS per month, OVERSPEND_THRESHOLD_PCT)``.
    The floor scales with the period because the norm does: over six months it
    means "at least €10 a month above usual on average", which is the same
    judgement a one-month range makes.

    Strictly above, so exactly 10% over does not count.
    """
    if expected_cents is None or expected_cents <= 0:
        return False
    delta_cents = actual_cents - expected_cents
    proportional_trigger = expected_cents * OVERSPEND_THRESHOLD_PCT / 100
    absolute_trigger = MIN_NOTABLE_CENTS * period_month_count
    return delta_cents > max(proportional_trigger, absolute_trigger)


def dipped_negative(worst_balance_cents: int) -> bool:
    """Whether a balance went far enough into the red to be worth reporting.

    A few euros overdrawn for a fortnight and covered the next month is not
    overspending, and listing it buries the categories that are.
    """
    return worst_balance_cents <= -MIN_NOTABLE_CENTS
