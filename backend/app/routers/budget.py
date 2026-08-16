from dataclasses import dataclass
from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import CurrentUser, DbSession, owned_scope
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
    FundGoalsEntryResponse,
    FundGoalsPreviewResponse,
    FundGoalsRequest,
    MoveMoneyRequest,
    ScopeReadyToAssign,
)
from app.services.budget_calc import (
    AssignmentRow,
    CategoryBalance,
    FundGoalsEntry,
    TxnRow,
    compute_category_balances,
    compute_fund_goals_plan,
    compute_ready_to_assign,
    format_month,
    month_start,
    parse_month,
)
from app.services.txn_rows import (
    build_txn_rows,
    load_peer_account_ids,
    load_splits_by_transaction_id,
)


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


@dataclass
class _BudgetMonthData:
    groups: list[CategoryGroup]
    categories: list[Category]
    scopes: list[Scope]
    category_scope_id: dict[int, int]
    txns: list[TxnRow]
    assignments: list[AssignmentRow]
    balances: dict[int, CategoryBalance]


async def _load_budget_month_data(
    db: DbSession, current_user: CurrentUser, target_month: date
) -> _BudgetMonthData:
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

    return _BudgetMonthData(
        groups=groups,
        categories=categories,
        scopes=scopes,
        category_scope_id=category_scope_id,
        txns=txns,
        assignments=assignments,
        balances=balances,
    )


@router.get("/{month}", response_model=BudgetMonthResponse)
async def get_budget_month(
    month: str, db: DbSession, current_user: CurrentUser
) -> BudgetMonthResponse:
    target_month = _parse_month_or_400(month)
    data = await _load_budget_month_data(db, current_user, target_month)

    cats_by_group: dict[int, list[BudgetCategoryRow]] = {}
    for c in data.categories:
        b = data.balances[c.id]
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
                    data.txns, data.assignments, target_month, scope.id
                ),
            )
            for scope in data.scopes
        ],
        groups=[
            BudgetGroupRow(
                id=g.id,
                name=g.name,
                scope_id=g.scope_id,
                categories=cats_by_group.get(g.id, []),
            )
            for g in data.groups
        ],
    )


async def _upsert_assignment_amount(
    db: AsyncSession,
    user_id: int,
    category_id: int,
    target_month: date,
    new_amount_cents: int,
) -> None:
    """Set ``category_id``'s assignment for ``target_month`` to
    ``new_amount_cents``, creating the row if none exists yet. Caller commits."""
    existing = await db.scalar(
        select(MonthlyAssignment).where(
            MonthlyAssignment.user_id == user_id,
            MonthlyAssignment.category_id == category_id,
            MonthlyAssignment.month == target_month,
        )
    )
    if existing is None:
        db.add(
            MonthlyAssignment(
                user_id=user_id,
                category_id=category_id,
                month=target_month,
                amount_cents=new_amount_cents,
            )
        )
    else:
        existing.amount_cents = new_amount_cents


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

    await _upsert_assignment_amount(
        db, current_user.id, payload.category_id, target_month, payload.amount_cents
    )
    await db.commit()


async def _compute_fund_goals_plan_for_scope(
    db: DbSession, current_user: CurrentUser, target_month: date, scope_id: int
) -> tuple[_BudgetMonthData, list[FundGoalsEntry], dict[int, str], int]:
    """Shared by the preview and commit endpoints so both always see the same
    plan for the same DB state — the commit endpoint calls this itself right
    before writing rather than trusting a client-supplied preview, since a
    stale preview must never be allowed to move money."""
    data = await _load_budget_month_data(db, current_user, target_month)
    scope_categories = [c for c in data.categories if data.category_scope_id[c.id] == scope_id]
    needed_by_category = [
        (c.id, _needed_this_month(c, data.balances[c.id], target_month) or 0)
        for c in scope_categories
    ]
    ready_to_assign_cents = compute_ready_to_assign(
        data.txns, data.assignments, target_month, scope_id
    )
    plan = compute_fund_goals_plan(needed_by_category, ready_to_assign_cents)
    names_by_id = {c.id: c.name for c in scope_categories}
    return data, plan, names_by_id, ready_to_assign_cents


@router.post("/{month}/fund-goals/preview", response_model=FundGoalsPreviewResponse)
async def preview_fund_goals(
    month: str,
    payload: FundGoalsRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> FundGoalsPreviewResponse:
    target_month = _parse_month_or_400(month)
    await owned_scope(db, current_user.id, payload.scope_id)

    _data, plan, names_by_id, ready_to_assign_cents = await _compute_fund_goals_plan_for_scope(
        db, current_user, target_month, payload.scope_id
    )
    entries = [
        FundGoalsEntryResponse(
            category_id=entry.category_id,
            category_name=names_by_id[entry.category_id],
            needed_cents=entry.needed_cents,
            amount_cents=entry.amount_cents,
        )
        for entry in plan
    ]
    return FundGoalsPreviewResponse(
        scope_id=payload.scope_id,
        ready_to_assign_cents=ready_to_assign_cents,
        entries=entries,
        total_amount_cents=sum(e.amount_cents for e in entries),
    )


@router.post("/{month}/fund-goals", status_code=status.HTTP_204_NO_CONTENT)
async def commit_fund_goals(
    month: str,
    payload: FundGoalsRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    target_month = _parse_month_or_400(month)
    await owned_scope(db, current_user.id, payload.scope_id)

    data, plan, _names_by_id, _ready_to_assign_cents = await _compute_fund_goals_plan_for_scope(
        db, current_user, target_month, payload.scope_id
    )

    for entry in plan:
        if entry.amount_cents <= 0:
            continue
        new_total = data.balances[entry.category_id].assigned_cents + entry.amount_cents
        await _upsert_assignment_amount(
            db, current_user.id, entry.category_id, target_month, new_total
        )
    await db.commit()


@router.post("/{month}/move", status_code=status.HTTP_204_NO_CONTENT)
async def move_money(
    month: str,
    payload: MoveMoneyRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    """Move assigned money from one category to another within the same
    scope and month — the general mechanic behind "Cover overspending" and
    any future "Move money" affordance. A single endpoint doing both upserts
    before its one commit keeps this atomic: a rejected request can never
    leave a partial write."""
    target_month = _parse_month_or_400(month)
    data = await _load_budget_month_data(db, current_user, target_month)

    owned_category_ids = {c.id for c in data.categories}
    if (
        payload.from_category_id not in owned_category_ids
        or payload.to_category_id not in owned_category_ids
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    if payload.from_category_id == payload.to_category_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source and destination must be different categories",
        )
    if payload.amount_cents <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Amount must be greater than zero"
        )
    if (
        data.category_scope_id[payload.from_category_id]
        != data.category_scope_id[payload.to_category_id]
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Categories must be in the same scope",
        )

    from_balance = data.balances[payload.from_category_id]
    to_balance = data.balances[payload.to_category_id]
    if payload.amount_cents > from_balance.balance_cents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Source category does not have enough available funds",
        )

    await _upsert_assignment_amount(
        db,
        current_user.id,
        payload.from_category_id,
        target_month,
        from_balance.assigned_cents - payload.amount_cents,
    )
    await _upsert_assignment_amount(
        db,
        current_user.id,
        payload.to_category_id,
        target_month,
        to_balance.assigned_cents + payload.amount_cents,
    )
    await db.commit()
