"""Zero-based budgeting math.

This module is the single source of truth for:

- **Ready to Assign** — money the user has in their accounts that hasn't been
  handed to a category yet, computed *per scope* (each scope is an independent
  pool).
- **Category balance** — how much is still available to spend on a category,
  including rollover from prior months.

All amounts are signed integer cents in a single currency (EUR). The functions
here are pure over their inputs so they can be unit-tested without a database —
see ``tests/test_budget_calc.py``.

Each ``TxnRow`` carries the scope of its **account** and each
``AssignmentRow`` carries the scope of its **category's group**. The router
joins the relevant rows before passing them in. A transfer leg additionally
carries the scope of its peer's account, which decides whether it touches RTA —
see ``feeds_ready_to_assign``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


def month_start(d: date) -> date:
    """Return the first day of the month containing ``d``."""
    return d.replace(day=1)


def next_month_start(d: date) -> date:
    """Return the first day of the month *after* ``d``."""
    first = month_start(d)
    year, month = first.year, first.month
    if month == 12:
        return date(year + 1, 1, 1)
    return date(year, month + 1, 1)


def parse_month(value: str) -> date:
    """Parse ``"YYYY-MM"`` into the first-of-month ``date``."""
    year_str, month_str = value.split("-", 1)
    return date(int(year_str), int(month_str), 1)


def format_month(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


@dataclass(frozen=True)
class TxnRow:
    category_id: int | None
    date: date
    amount_cents: int  # signed
    scope_id: int  # the account's scope
    # Scope of the account holding this row's transfer peer; None when the row
    # isn't a transfer leg. See ``feeds_ready_to_assign``.
    transfer_peer_scope_id: int | None = None
    # Whether this row's account feeds Ready to Assign — False for savings
    # accounts. See ``feeds_ready_to_assign``.
    on_budget: bool = True
    # Whether the transfer peer's account is on-budget; meaningless when the
    # row isn't a transfer leg. Defaults to True so callers building a
    # same-scope, on-budget-only transfer don't need to set it.
    # See ``feeds_ready_to_assign``.
    transfer_peer_on_budget: bool = True


def feeds_ready_to_assign(txn: TxnRow) -> bool:
    """Whether ``txn`` is money arriving in (or leaving) its scope's RTA pool.

    Uncategorized rows are the sole source of Ready to Assign. Transfer legs
    are uncategorized too, but only legs that actually move money between
    pools count: a *cross-scope* transfer moves money between two pools, and a
    same-scope transfer that crosses the on-budget/
    off-budget boundary moves money into or out of the budget entirely (e.g.
    checking -> savings). A same-scope transfer between two accounts with the
    same on-budget status is just one pool's money changing accounts, so both
    its legs are excluded and the pool is untouched.

    The two legs are always equal and opposite, so excluding them is the same
    arithmetic as letting them cancel out — except when they fall in different
    months, which a pair linked from two bank imports routinely does
    (money leaves on the 31st and lands on the 2nd). There the exclusion is the
    *more* correct reading: money in transit between the user's own accounts
    never stopped being theirs, so neither month's pool should move. Writing it
    as an exclusion rather than relying on cancellation is what pins that, and
    what lets ``insights_calc`` apply the identical rule.

    Off-budget accounts (savings) never feed RTA directly through this row —
    only through the on-budget leg of a transfer that moves money in or out of
    them, per ``account_types.OFF_BUDGET_ACCOUNT_TYPES``'s documented design.
    """
    if txn.category_id is not None:
        return False
    if not txn.on_budget:
        return False
    return (
        txn.transfer_peer_scope_id != txn.scope_id
        or txn.transfer_peer_on_budget != txn.on_budget
    )


@dataclass(frozen=True)
class AssignmentRow:
    category_id: int
    month: date  # first of month
    amount_cents: int
    scope_id: int  # the scope of the category's group


@dataclass(frozen=True)
class CategoryBalance:
    category_id: int
    assigned_cents: int  # for the requested month only
    activity_cents: int  # for the requested month only (signed; outflow is negative)
    balance_cents: int  # prior rollover + assigned + activity


def compute_ready_to_assign(
    transactions: list[TxnRow],
    assignments: list[AssignmentRow],
    through_month: date,
    scope_id: int,
) -> int:
    """Money on hand in ``scope_id`` that has not yet been assigned to any category.

    Inflows are scoped to ``through_month`` and earlier. Assignments from
    future months reduce the pool when they exceed future inflows — the
    shortfall must be drawn from money already on hand. Rows from other
    scopes are ignored: each scope is its own self-contained pool.
    ``through_month`` must be a first-of-month date.
    """
    boundary = next_month_start(through_month)

    inflow_through_month = sum(
        t.amount_cents
        for t in transactions
        if t.scope_id == scope_id and feeds_ready_to_assign(t) and t.date < boundary
    )
    assigned_through_month = sum(
        a.amount_cents
        for a in assignments
        if a.scope_id == scope_id and a.month < boundary
    )

    future_inflow = sum(
        t.amount_cents
        for t in transactions
        if t.scope_id == scope_id and feeds_ready_to_assign(t) and t.date >= boundary
    )
    future_assigned = sum(
        a.amount_cents
        for a in assignments
        if a.scope_id == scope_id and a.month >= boundary
    )
    future_overdraft = max(0, future_assigned - future_inflow)

    return inflow_through_month - assigned_through_month - future_overdraft


def compute_category_balances(
    category_ids: list[int],
    transactions: list[TxnRow],
    assignments: list[AssignmentRow],
    month: date,
) -> dict[int, CategoryBalance]:
    """Compute per-category assigned / activity / balance for ``month``.

    ``balance`` rolls all prior months forward (positive *and* negative, like
    nYNAB's default). ``assigned`` and ``activity`` reflect ``month`` only.
    Scope-agnostic: scope filtering happens in the caller via category
    selection.
    """
    month = month_start(month)
    next_month = next_month_start(month)

    result: dict[int, CategoryBalance] = {}
    for cat_id in category_ids:
        assigned_this_month = sum(
            a.amount_cents for a in assignments if a.category_id == cat_id and a.month == month
        )
        activity_this_month = sum(
            t.amount_cents
            for t in transactions
            if t.category_id == cat_id and month <= t.date < next_month
        )
        prior_assigned = sum(
            a.amount_cents for a in assignments if a.category_id == cat_id and a.month < month
        )
        prior_activity = sum(
            t.amount_cents
            for t in transactions
            if t.category_id == cat_id and t.date < month
        )
        balance = prior_assigned + prior_activity + assigned_this_month + activity_this_month
        result[cat_id] = CategoryBalance(
            category_id=cat_id,
            assigned_cents=assigned_this_month,
            activity_cents=activity_this_month,
            balance_cents=balance,
        )
    return result
