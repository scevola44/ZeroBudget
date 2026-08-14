from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models import (
    Account,
    Category,
    CategoryGroup,
    MonthlyAssignment,
    Scope,
    Transaction,
)
from app.models.account_types import account_on_budget
from app.schemas.budget import (
    AssignRequest,
    BudgetCategoryRow,
    BudgetGroupRow,
    BudgetMonthResponse,
    ScopeReadyToAssign,
)
from app.services.budget_calc import (
    AssignmentRow,
    CategoryBalance,
    compute_category_balances,
    compute_ready_to_assign,
    format_month,
    month_start,
    parse_month,
)
from app.services.txn_rows import build_txn_rows, load_peer_account_ids, load_splits_by_transaction_id


def _needed_this_month(
    category: Category, balance: CategoryBalance, month_first: date
) -> int | None:
    """How much the user should fund this category in ``month_first`` to stay on
    track. ``None`` when no meaningful suggestion exists (target_date already
    in the past)."""
    if category.goal_kind == "monthly":
        # A monthly goal means "assign this much every month" — it's not about
        # keeping the available balance topped up, so in-month spending alone
        # shouldn't resurrect the suggestion once the goal has been assigned.
        # It should reappear if spending has overspent the category, though.
        underfunded = max(0, category.goal_amount_cents - balance.assigned_cents)
        overspent = max(0, -balance.balance_cents)
        return max(underfunded, overspent)
    if category.goal_kind == "yearly":
        per_month = category.goal_amount_cents // 12
        return max(0, per_month - balance.balance_cents)
    if category.goal_kind == "target_date":
        target = category.goal_target_month
        if target is None or target < month_first:
            return None
        months_left = (
            (target.year - month_first.year) * 12
            + (target.month - month_first.month)
            + 1
        )
        remaining = max(0, category.goal_amount_cents - balance.balance_cents)
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

    scopes = (
        (
            await db.execute(
                select(Scope)
                .where(Scope.user_id == current_user.id)
                .order_by(Scope.sort_order, Scope.id)
            )
        )
        .scalars()
        .all()
    )

    account_scope_id: dict[int, int] = {a.id: a.scope_id for a in accounts}
    account_on_budget_map: dict[int, bool] = {a.id: account_on_budget(a.type) for a in accounts}
    group_scope_id: dict[int, int] = {g.id: g.scope_id for g in groups}
    category_scope_id: dict[int, int] = {c.id: group_scope_id[c.group_id] for c in categories}

    peer_account_id = await load_peer_account_ids(db, txn_rows_db)
    splits_by_transaction_id = await load_splits_by_transaction_id(db, txn_rows_db)
    txns = build_txn_rows(
        txn_rows_db,
        account_scope_id,
        account_on_budget_map,
        peer_account_id,
        splits_by_transaction_id,
    )
    assignments = [
        AssignmentRow(
            category_id=a.category_id,
            month=a.month,
            amount_cents=a.amount_cents,
            scope_id=category_scope_id[a.category_id],
        )
        for a in assignment_rows_db
    ]

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
                needed_this_month_cents=_needed_this_month(c, b, target_month),
            )
        )

    return BudgetMonthResponse(
        month=format_month(target_month),
        ready_to_assign=[
            ScopeReadyToAssign(
                scope_id=scope.id,
                ready_to_assign_cents=compute_ready_to_assign(
                    txns, assignments, target_month, scope.id
                ),
            )
            for scope in scopes
        ],
        groups=[
            BudgetGroupRow(
                id=g.id,
                name=g.name,
                scope_id=g.scope_id,
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
