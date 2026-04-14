"""Zero-based budgeting math.

This module is the single source of truth for:

- **Ready to Assign** — money the user has in their accounts that hasn't been
  handed to a category yet.
- **Category balance** — how much is still available to spend on a category,
  including rollover from prior months.

All amounts are signed integer cents in a single currency (EUR). The functions
here are pure over their inputs so they can be unit-tested without a database —
see ``tests/test_budget_calc.py``.
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


@dataclass(frozen=True)
class AssignmentRow:
    category_id: int
    month: date  # first of month
    amount_cents: int


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
) -> int:
    """Money on hand that has not yet been assigned to any category.

    Only transactions/assignments up through the *end* of ``through_month`` are
    considered. ``through_month`` must be a first-of-month date.
    """
    boundary = next_month_start(through_month)

    unassigned_inflow = sum(
        t.amount_cents
        for t in transactions
        if t.category_id is None and t.date < boundary
    )
    total_assigned = sum(
        a.amount_cents for a in assignments if a.month < boundary
    )
    return unassigned_inflow - total_assigned


def compute_category_balances(
    category_ids: list[int],
    transactions: list[TxnRow],
    assignments: list[AssignmentRow],
    month: date,
) -> dict[int, CategoryBalance]:
    """Compute per-category assigned / activity / balance for ``month``.

    ``balance`` rolls all prior months forward (positive *and* negative, like
    nYNAB's default). ``assigned`` and ``activity`` reflect ``month`` only.
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
