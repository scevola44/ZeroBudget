from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.scope import PERSONAL, Scope

GoalKind = Literal["monthly", "yearly", "target_date"]


def _ensure_first_of_month(value: date) -> date:
    if value.day != 1:
        raise ValueError("goal_target_month must be the first of the month")
    return value


def _validate_goal_combo(
    kind: GoalKind, amount_cents: int, target_month: date | None
) -> None:
    """Cross-field rules for the (kind, amount, target_month) triple.

    Pure function so the router can re-run it after merging a partial PATCH
    with the persisted row.
    """
    if amount_cents <= 0:
        raise ValueError("goal_amount_cents must be positive")
    if kind == "target_date":
        if target_month is None:
            raise ValueError("goal_target_month is required when goal_kind is target_date")
        _ensure_first_of_month(target_month)
    else:
        if target_month is not None:
            raise ValueError(
                "goal_target_month must be omitted unless goal_kind is target_date"
            )


class CategoryGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    sort_order: int = 0
    scope: Scope = PERSONAL


class CategoryGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    sort_order: int | None = None
    scope: Scope | None = None


class CategoryCreate(BaseModel):
    group_id: int
    name: str = Field(min_length=1, max_length=120)
    sort_order: int = 0
    goal_kind: GoalKind
    goal_amount_cents: int = Field(gt=0)
    goal_target_month: date | None = None

    @model_validator(mode="after")
    def _check_goal(self) -> "CategoryCreate":
        _validate_goal_combo(self.goal_kind, self.goal_amount_cents, self.goal_target_month)
        return self


class CategoryUpdate(BaseModel):
    group_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    sort_order: int | None = None
    goal_kind: GoalKind | None = None
    goal_amount_cents: int | None = Field(default=None, gt=0)
    goal_target_month: date | None = None

    @model_validator(mode="after")
    def _check_target_month_shape(self) -> "CategoryUpdate":
        # We can't fully validate the kind/target_month combo here without the
        # current row — the router does that after merging. But we can already
        # reject a target_month that isn't a first-of-month date.
        if self.goal_target_month is not None:
            _ensure_first_of_month(self.goal_target_month)
        return self


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int
    name: str
    sort_order: int
    goal_kind: GoalKind
    goal_amount_cents: int
    goal_target_month: date | None


class CategoryGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sort_order: int
    scope: Scope
    categories: list[CategoryResponse] = []


class YnabImportRow(BaseModel):
    group: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=120)


class YnabImportRequest(BaseModel):
    rows: list[YnabImportRow] = Field(min_length=1)


class YnabImportResponse(BaseModel):
    groups_created: int
    categories_created: int
