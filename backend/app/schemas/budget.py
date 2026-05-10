from datetime import date

from pydantic import BaseModel

from app.models.scope import Scope
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
    scope: Scope
    categories: list[BudgetCategoryRow]


class BudgetMonthResponse(BaseModel):
    month: str  # "YYYY-MM"
    personal_ready_to_assign_cents: int
    shared_ready_to_assign_cents: int
    groups: list[BudgetGroupRow]


class AssignRequest(BaseModel):
    category_id: int
    amount_cents: int
