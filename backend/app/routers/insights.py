from datetime import date

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models import Account, Category, CategoryGroup, MonthlyAssignment, Transaction
from app.models.account_types import account_on_budget
from app.models.scope import PERSONAL, SCOPES, SHARED
from app.schemas.insights import (
    CategorySpendingRow,
    CategoryTrendRow,
    GroupSpendingRow,
    IncomeVsSpending,
    InsightsPeriod,
    InsightsResponse,
    MonthFlowRow,
    Overspending,
    ScopeBreakdown,
    ScopeFlow,
    ScopeOverspending,
    ScopeSplit,
    SpendingBreakdown,
)
from app.services.budget_calc import (
    AssignmentRow,
    TxnRow,
    format_month,
    month_start,
    next_month_start,
    parse_month,
)
from app.services.insights_calc import (
    MIN_BASELINE_MONTHS,
    MIN_NOTABLE_CENTS,
    OVERSPEND_THRESHOLD_PCT,
    CategoryTrend,
    MonthRange,
    ScopeSpending,
    baseline_range,
    compute_category_trends,
    compute_spending_breakdown,
    flow_by_month,
)
from app.services.txn_rows import build_txn_rows, load_peer_account_ids

router = APIRouter(prefix="/api/insights", tags=["insights"])

# Guards against an unbounded hand-typed range; the UI never asks for more than
# twelve months.
MAX_RANGE_MONTHS = 60


def _parse_month_or_400(value: str) -> date:
    try:
        return month_start(parse_month(value))
    except (ValueError, IndexError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Month must be in YYYY-MM format",
        ) from exc


def _parse_period_or_400(start_month: str, end_month: str) -> MonthRange:
    start = _parse_month_or_400(start_month)
    end = _parse_month_or_400(end_month)
    if start > end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_month must not be after end_month",
        )
    period = MonthRange(start=start, end=end)
    if period.month_count > MAX_RANGE_MONTHS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Range must not exceed {MAX_RANGE_MONTHS} months",
        )
    return period


@router.get("", response_model=InsightsResponse)
async def get_insights(
    db: DbSession,
    current_user: CurrentUser,
    start_month: str = Query(..., description="YYYY-MM, inclusive"),
    end_month: str = Query(..., description="YYYY-MM, inclusive"),
) -> InsightsResponse:
    period = _parse_period_or_400(start_month, end_month)
    # Rows after the period cannot affect any figure on this page. The budget
    # router must not do this — ``compute_ready_to_assign`` needs future rows for
    # its overdraft term — but Insights computes no Ready to Assign.
    horizon = next_month_start(period.end)

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
        (await db.execute(select(Account).where(Account.user_id == current_user.id)))
        .scalars()
        .all()
    )
    txn_rows_db = (
        (
            await db.execute(
                select(Transaction).where(
                    Transaction.user_id == current_user.id,
                    Transaction.date < horizon,
                )
            )
        )
        .scalars()
        .all()
    )
    assignment_rows_db = (
        (
            await db.execute(
                select(MonthlyAssignment).where(
                    MonthlyAssignment.user_id == current_user.id,
                    MonthlyAssignment.month < horizon,
                )
            )
        )
        .scalars()
        .all()
    )

    account_scope: dict[int, str] = {a.id: a.scope for a in accounts}
    account_on_budget_map: dict[int, bool] = {a.id: account_on_budget(a.type) for a in accounts}
    group_scope: dict[int, str] = {g.id: g.scope for g in groups}
    category_scope: dict[int, str] = {
        c.id: group_scope.get(c.group_id, PERSONAL) for c in categories
    }
    category_group: dict[int, int] = {c.id: c.group_id for c in categories}
    category_name: dict[int, str] = {c.id: c.name for c in categories}
    group_name: dict[int, str] = {g.id: g.name for g in groups}

    # Peers are loaded separately: this query is date-windowed, and a transfer
    # linked from two bank imports can straddle the horizon.
    peer_account_id = await load_peer_account_ids(db, txn_rows_db)
    txns = build_txn_rows(txn_rows_db, account_scope, account_on_budget_map, peer_account_id)
    assignments = [
        AssignmentRow(
            category_id=a.category_id,
            month=a.month,
            amount_cents=a.amount_cents,
            scope=category_scope.get(a.category_id, PERSONAL),
        )
        for a in assignment_rows_db
    ]

    spending = compute_spending_breakdown(txns, period, category_scope, SCOPES)
    trends = compute_category_trends(
        [c.id for c in categories], txns, assignments, period
    )
    baseline = baseline_range(period)

    def breakdown_for(scope: str) -> ScopeBreakdown:
        scope_groups = [g.id for g in groups if g.scope == scope]
        return _scope_breakdown(
            spending[scope], scope_groups, category_group, category_name, group_name
        )

    def flow_for(scope: str) -> ScopeFlow:
        return _scope_flow(txns, period, scope, category_scope)

    def overspending_for(scope: str) -> ScopeOverspending:
        scoped = [c.id for c in categories if category_scope[c.id] == scope]
        return _scope_overspending(
            scope, scoped, trends, category_name, category_group, group_name
        )

    return InsightsResponse(
        period=InsightsPeriod(
            start_month=format_month(period.start),
            end_month=format_month(period.end),
            month_count=period.month_count,
            baseline_start_month=format_month(baseline.start),
            baseline_end_month=format_month(baseline.end),
        ),
        breakdown=SpendingBreakdown(
            scope_split=ScopeSplit(
                personal_spent_cents=spending[PERSONAL].total_spent_cents,
                shared_spent_cents=spending[SHARED].total_spent_cents,
                total_spent_cents=spending[PERSONAL].total_spent_cents
                + spending[SHARED].total_spent_cents,
            ),
            personal=breakdown_for(PERSONAL),
            shared=breakdown_for(SHARED),
        ),
        income_vs_spending=IncomeVsSpending(
            personal=flow_for(PERSONAL), shared=flow_for(SHARED)
        ),
        overspending=Overspending(
            threshold_pct=OVERSPEND_THRESHOLD_PCT,
            min_notable_cents=MIN_NOTABLE_CENTS,
            min_baseline_months=MIN_BASELINE_MONTHS,
            personal=overspending_for(PERSONAL),
            shared=overspending_for(SHARED),
        ),
    )


def _scope_breakdown(
    spending: ScopeSpending,
    scope_group_ids: list[int],
    category_group: dict[int, int],
    category_name: dict[int, str],
    group_name: dict[int, str],
) -> ScopeBreakdown:
    categories = sorted(
        (
            CategorySpendingRow(
                category_id=category_id,
                name=category_name.get(category_id, ""),
                group_id=category_group[category_id],
                group_name=group_name.get(category_group[category_id], ""),
                spent_cents=spend.spent_cents,
                refund_cents=spend.refund_cents,
                activity_cents=spend.activity_cents,
            )
            for category_id, spend in spending.by_category.items()
        ),
        key=lambda row: (-row.spent_cents, row.category_id),
    )

    group_totals: dict[int, int] = {group_id: 0 for group_id in scope_group_ids}
    for row in categories:
        group_totals[row.group_id] = group_totals.get(row.group_id, 0) + row.spent_cents

    return ScopeBreakdown(
        scope=spending.scope,
        total_spent_cents=spending.total_spent_cents,
        groups=sorted(
            (
                GroupSpendingRow(
                    group_id=group_id,
                    name=group_name.get(group_id, ""),
                    spent_cents=group_totals[group_id],
                    sort_index=sort_index,
                )
                for sort_index, group_id in enumerate(scope_group_ids)
            ),
            key=lambda row: (-row.spent_cents, row.group_id),
        ),
        categories=categories,
    )


def _scope_flow(
    txns: list[TxnRow],
    period: MonthRange,
    scope: str,
    category_scope: dict[int, str],
) -> ScopeFlow:
    months = flow_by_month(txns, period, scope, category_scope)
    return ScopeFlow(
        scope=scope,
        income_cents=sum(month.income_cents for month in months),
        spent_cents=sum(month.spent_cents for month in months),
        refund_cents=sum(month.refund_cents for month in months),
        net_cents=sum(month.net_cents for month in months),
        months=[
            MonthFlowRow(
                month=format_month(month.month),
                income_cents=month.income_cents,
                spent_cents=month.spent_cents,
                refund_cents=month.refund_cents,
                net_cents=month.net_cents,
            )
            for month in months
        ],
    )


def _scope_overspending(
    scope: str,
    category_ids: list[int],
    trends: dict[int, CategoryTrend],
    category_name: dict[int, str],
    category_group: dict[int, int],
    group_name: dict[int, str],
) -> ScopeOverspending:
    flagged = [trends[category_id] for category_id in category_ids if trends[category_id].flags]
    return ScopeOverspending(
        scope=scope,
        categories=[
            CategoryTrendRow(
                category_id=trend.category_id,
                name=category_name.get(trend.category_id, ""),
                group_name=group_name.get(category_group[trend.category_id], ""),
                assigned_cents=trend.assigned_cents,
                expected_assigned_cents=trend.expected_assigned_cents,
                assigned_delta_cents=trend.assigned_delta_cents,
                assigned_delta_pct=trend.assigned_delta_pct,
                spent_cents=trend.spent_cents,
                expected_spent_cents=trend.expected_spent_cents,
                spent_delta_cents=trend.spent_delta_cents,
                spent_delta_pct=trend.spent_delta_pct,
                baseline_month_count=trend.baseline_month_count,
                has_baseline=trend.has_baseline,
                worst_balance_cents=trend.worst_balance_cents,
                worst_balance_month=(
                    format_month(trend.worst_balance_month)
                    if trend.worst_balance_month is not None
                    else None
                ),
                flags=list(trend.flags),
            )
            for trend in sorted(flagged, key=_severity)
        ],
        on_track_count=len(category_ids) - len(flagged),
    )


def _severity(trend: CategoryTrend) -> tuple[int, int, float, float, int]:
    """A balance that went negative outranks any percentage; deepest first. Then
    the biggest spending overshoot, then assignment — assigning more than usual
    is a choice the user made, so it never outranks money actually running out."""
    went_negative = trend.worst_balance_month is not None
    return (
        0 if went_negative else 1,
        trend.worst_balance_cents if went_negative else 0,
        -(trend.spent_delta_pct or 0.0),
        -(trend.assigned_delta_pct or 0.0),
        trend.category_id,
    )
