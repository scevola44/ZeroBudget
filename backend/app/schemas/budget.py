from datetime import date

from pydantic import BaseModel

from app.schemas.category import GoalKind


class BudgetCategoryRow(BaseModel):
    id: int
    name: str
    assigned_cents: int
    activity_cents: int
    balance_cents: int
    goal_kind: GoalKind
    goal_amount_cents: int
    goal_target_month: date | None
    # Suggested funding to satisfy the goal in the displayed month. ``None``
    # for target_date goals whose target has already passed.
    needed_this_month_cents: int | None


class BudgetGroupRow(BaseModel):
    id: int
    name: str
    scope_id: int
    categories: list[BudgetCategoryRow]


class ScopeReadyToAssign(BaseModel):
    scope_id: int
    ready_to_assign_cents: int


class BudgetMonthResponse(BaseModel):
    month: str  # "YYYY-MM"
    # One entry per scope, in the user's own scope order. A list rather than a
    # map because JSON object keys are strings and scope ids are not.
    ready_to_assign: list[ScopeReadyToAssign]
    groups: list[BudgetGroupRow]


class AssignRequest(BaseModel):
    category_id: int
    amount_cents: int


class FundGoalsRequest(BaseModel):
    scope_id: int


class MoveMoneyRequest(BaseModel):
    from_category_id: int
    to_category_id: int
    amount_cents: int


class FundGoalsEntryResponse(BaseModel):
    category_id: int
    category_name: str
    # Full suggested amount vs. what will actually be assigned — differ when
    # the scope's Ready to Assign ran out partway through the plan.
    needed_cents: int
    amount_cents: int


class FundGoalsPreviewResponse(BaseModel):
    scope_id: int
    ready_to_assign_cents: int
    entries: list[FundGoalsEntryResponse]
    total_amount_cents: int
