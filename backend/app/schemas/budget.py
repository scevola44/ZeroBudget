from pydantic import BaseModel


class BudgetCategoryRow(BaseModel):
    id: int
    name: str
    assigned_cents: int
    activity_cents: int
    balance_cents: int


class BudgetGroupRow(BaseModel):
    id: int
    name: str
    categories: list[BudgetCategoryRow]


class BudgetMonthResponse(BaseModel):
    month: str  # "YYYY-MM"
    ready_to_assign_cents: int
    groups: list[BudgetGroupRow]


class AssignRequest(BaseModel):
    category_id: int
    amount_cents: int
