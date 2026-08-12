"""Which category to propose for a payee, from how it's been categorized before.

Two tiers. A payee seen verbatim before is the easy case: offer whichever
category it was filed under most recently, then the one before that, and so
on — a payee that changed category over time should surface the current habit
first without hiding the fallback. A payee that has never appeared exactly as
typed is the hard case a bank sync creates constantly (`"Visa: Store From
Home"` vs. `"Store From Home"`): pick whichever *historical* payee the typed
text most resembles and borrow its ranking instead, but only above a
confidence floor — a wrong guess here is worse than no guess.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from rapidfuzz import fuzz

# rapidfuzz's WRatio score (0-100) below which a historical payee is treated
# as unrelated rather than the same entity with sync noise. Chosen so
# short additions like a "Visa: " prefix still match while genuinely
# different payees of similar length don't.
FUZZY_MATCH_THRESHOLD = 80


@dataclass(frozen=True)
class PayeeHistoryRow:
    id: int
    payee: str
    category_id: int
    date: date


def _normalize(payee: str) -> str:
    return payee.strip().casefold()


def _rank_by_recency(rows: Sequence[PayeeHistoryRow]) -> list[int]:
    """Category ids from ``rows``, most-recently-used first, each id once."""
    ordered = sorted(rows, key=lambda row: (row.date, row.id), reverse=True)
    seen: set[int] = set()
    ranked: list[int] = []
    for row in ordered:
        if row.category_id in seen:
            continue
        seen.add(row.category_id)
        ranked.append(row.category_id)
    return ranked


def suggest_categories(target_payee: str, rows: Sequence[PayeeHistoryRow]) -> list[int]:
    """Category ids to propose for ``target_payee``, best guess first."""
    target = _normalize(target_payee)

    exact = [row for row in rows if _normalize(row.payee) == target]
    if exact:
        return _rank_by_recency(exact)

    by_payee: dict[str, list[PayeeHistoryRow]] = {}
    for row in rows:
        by_payee.setdefault(_normalize(row.payee), []).append(row)

    best_payee: str | None = None
    best_score = -1.0
    best_recency: tuple[date, int] = (date.min, -1)
    for payee, payee_rows in by_payee.items():
        score = fuzz.WRatio(target, payee)
        if score < FUZZY_MATCH_THRESHOLD:
            continue
        recency = max((row.date, row.id) for row in payee_rows)
        if score > best_score or (score == best_score and recency > best_recency):
            best_payee, best_score, best_recency = payee, score, recency

    if best_payee is None:
        return []
    return _rank_by_recency(by_payee[best_payee])
