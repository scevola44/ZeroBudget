from typing import Literal

from pydantic import BaseModel

from app.models.scope import Scope

OverspendFlag = Literal[
    "spent_above_usual",
    "assigned_above_usual",
    "new_spending",
    "available_negative",
]


class InsightsPeriod(BaseModel):
    start_month: str  # "YYYY-MM", inclusive
    end_month: str  # "YYYY-MM", inclusive
    month_count: int
    # The window the "usual" figures were measured over, so the UI can name it
    # rather than leaving the user to guess what it compared against.
    baseline_start_month: str
    baseline_end_month: str


class CategorySpendingRow(BaseModel):
    category_id: int
    name: str
    group_id: int
    group_name: str
    spent_cents: int  # gross outflow, >= 0
    refund_cents: int
    activity_cents: int  # refund - spent; matches BudgetCategoryRow.activity_cents


class GroupSpendingRow(BaseModel):
    group_id: int
    name: str
    spent_cents: int
    # The group's position in its scope's own ordering. Charts colour by this
    # rather than by rank, so changing the period never repaints the groups that
    # were already on screen.
    sort_index: int


class ScopeBreakdown(BaseModel):
    scope: Scope
    total_spent_cents: int
    groups: list[GroupSpendingRow]  # descending by spent_cents
    categories: list[CategorySpendingRow]  # descending by spent_cents


class ScopeSplit(BaseModel):
    """The only cross-scope aggregate on this page.

    It exists so the user can see how spending divides between their two pools,
    which is a labelled split rather than the silent merge ROADMAP invariant 1
    forbids. Every other figure stays inside one scope.
    """

    personal_spent_cents: int
    shared_spent_cents: int
    total_spent_cents: int


class SpendingBreakdown(BaseModel):
    scope_split: ScopeSplit
    personal: ScopeBreakdown
    shared: ScopeBreakdown


class MonthFlowRow(BaseModel):
    month: str  # "YYYY-MM"
    income_cents: int
    spent_cents: int
    refund_cents: int
    net_cents: int


class ScopeFlow(BaseModel):
    scope: Scope
    income_cents: int
    spent_cents: int
    refund_cents: int
    net_cents: int
    months: list[MonthFlowRow]  # one per month in the period, chronological


class IncomeVsSpending(BaseModel):
    personal: ScopeFlow
    shared: ScopeFlow


class CategoryTrendRow(BaseModel):
    category_id: int
    name: str
    group_name: str
    assigned_cents: int
    expected_assigned_cents: int | None
    assigned_delta_cents: int | None
    assigned_delta_pct: float | None
    spent_cents: int
    expected_spent_cents: int | None
    spent_delta_cents: int | None
    spent_delta_pct: float | None
    baseline_month_count: int
    has_baseline: bool
    worst_balance_cents: int
    worst_balance_month: str | None  # "YYYY-MM"; None when it never went negative
    flags: list[OverspendFlag]


class ScopeOverspending(BaseModel):
    scope: Scope
    categories: list[CategoryTrendRow]  # flagged only, most severe first
    on_track_count: int


class Overspending(BaseModel):
    # The rule these rows were selected by. Returned so the page can state it
    # exactly instead of hardcoding numbers that would drift from the service.
    threshold_pct: float
    min_notable_cents: int
    min_baseline_months: int
    personal: ScopeOverspending
    shared: ScopeOverspending


class InsightsResponse(BaseModel):
    period: InsightsPeriod
    breakdown: SpendingBreakdown
    income_vs_spending: IncomeVsSpending
    overspending: Overspending
