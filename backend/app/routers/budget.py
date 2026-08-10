from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models import Account, Category, CategoryGroup, MonthlyAssignment, Transaction
from app.models.scope import PERSONAL, SHARED
from app.schemas.budget import (
    AssignRequest,
    BudgetCategoryRow,
    BudgetGroupRow,
    BudgetMonthResponse,
)
from app.services.budget_calc import (
    AssignmentRow,
    compute_category_balances,
    compute_ready_to_assign,
    format_month,
    month_start,
    parse_month,
)
from app.services.txn_rows import build_txn_rows, load_peer_account_ids


def _needed_this_month(category: Category, balance_cents: int, month_first: date) -> int | None:
    """How much the user should fund this category in ``month_first`` to stay on
    track. ``None`` when no meaningful suggestion exists (target_date already
    in the past)."""
    if category.goal_kind == "monthly":
        return max(0, category.goal_amount_cents - balance_cents)
    if category.goal_kind == "yearly":
        per_month = category.goal_amount_cents // 12
        return max(0, per_month - balance_cents)
    if category.goal_kind == "target_date":
        target = category.goal_target_month
        if target is None or target < month_first:
            return None
        months_left = (
            (target.year - month_first.year) * 12
            + (target.month - month_first.month)
            + 1
        )
        remaining = max(0, category.goal_amount_cents - balance_cents)
        return remaining // months_left if months_left > 0 else remaining
    return None

router = APIRouter(prefix="/api/budget", tags=["budget"])


def _parse_month_or_400(value: str):
    try:
        return month_start(parse_month(value))
    except (ValueError, IndexError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Month must be in YYYY-MM format",
        ) from exc


@router.get("/{month}", response_model=BudgetMonthResponse)
async def get_budget_month(
    month: str, db: DbSession, current_user: CurrentUser
) -> BudgetMonthResponse:
    target_month = _parse_month_or_400(month)

    groups = (
        (
            await db.execute(
                select(CategoryGroup)
                .where(CategoryGroup.user_id == current_user.id)
                .order_by(CategoryGroup.sort_order, CategoryGroup.id)
            )
        )
        .scalars()
        .all()
    )
    categories = (
        (
            await db.execute(
                select(Category)
                .where(Category.user_id == current_user.id)
                .order_by(Category.sort_order, Category.id)
            )
        )
        .scalars()
        .all()
    )
    accounts = (
        (
            await db.execute(
                select(Account).where(Account.user_id == current_user.id)
            )
        )
        .scalars()
        .all()
    )
    txn_rows_db = (
        (
            await db.execute(
                select(Transaction).where(Transaction.user_id == current_user.id)
            )
        )
        .scalars()
        .all()
    )
    assignment_rows_db = (
        (
            await db.execute(
                select(MonthlyAssignment).where(
                    MonthlyAssignment.user_id == current_user.id
                )
            )
        )
        .scalars()
        .all()
    )

    account_scope: dict[int, str] = {a.id: a.scope for a in accounts}
    group_scope: dict[int, str] = {g.id: g.scope for g in groups}
    category_scope: dict[int, str] = {c.id: group_scope[c.group_id] for c in categories}

    peer_account_id = await load_peer_account_ids(db, txn_rows_db)
    txns = build_txn_rows(txn_rows_db, account_scope, peer_account_id)
    assignments = [
        AssignmentRow(
            category_id=a.category_id,
            month=a.month,
            amount_cents=a.amount_cents,
            scope=category_scope.get(a.category_id, PERSONAL),
        )
        for a in assignment_rows_db
    ]

    personal_ready = compute_ready_to_assign(txns, assignments, target_month, PERSONAL)
    shared_ready = compute_ready_to_assign(txns, assignments, target_month, SHARED)
    cat_ids = [c.id for c in categories]
    balances = compute_category_balances(cat_ids, txns, assignments, target_month)

    cats_by_group: dict[int, list[BudgetCategoryRow]] = {}
    for c in categories:
        b = balances[c.id]
        cats_by_group.setdefault(c.group_id, []).append(
            BudgetCategoryRow(
                id=c.id,
                name=c.name,
                assigned_cents=b.assigned_cents,
                activity_cents=b.activity_cents,
                balance_cents=b.balance_cents,
                goal_kind=c.goal_kind,
                goal_amount_cents=c.goal_amount_cents,
                goal_target_month=c.goal_target_month,
                needed_this_month_cents=_needed_this_month(c, b.balance_cents, target_month),
            )
        )

    return BudgetMonthResponse(
        month=format_month(target_month),
        personal_ready_to_assign_cents=personal_ready,
        shared_ready_to_assign_cents=shared_ready,
        groups=[
            BudgetGroupRow(
                id=g.id,
                name=g.name,
                scope=g.scope,
                categories=cats_by_group.get(g.id, []),
            )
            for g in groups
        ],
    )


@router.post("/{month}/assign", status_code=status.HTTP_204_NO_CONTENT)
async def upsert_assignment(
    month: str,
    payload: AssignRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    target_month = _parse_month_or_400(month)

    category = await db.get(Category, payload.category_id)
    if category is None or category.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    existing = await db.scalar(
        select(MonthlyAssignment).where(
            MonthlyAssignment.user_id == current_user.id,
            MonthlyAssignment.category_id == payload.category_id,
            MonthlyAssignment.month == target_month,
        )
    )
    if existing is None:
        db.add(
            MonthlyAssignment(
                user_id=current_user.id,
                category_id=payload.category_id,
                month=target_month,
                amount_cents=payload.amount_cents,
            )
        )
    else:
        existing.amount_cents = payload.amount_cents
    await db.commit()
