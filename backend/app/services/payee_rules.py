"""Which category a payee-contains rule proposes for an incoming payee.

Pure and DB-free, same spirit as ``budget_calc.py``: the caller loads the
user's rules (already ordered by ``sort_order``) and this just picks the
first match, so the rule can be unit-tested without a session.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryRule:
    id: int
    category_id: int
    contains_text: str


def match_rule(payee_text: str, rules: Sequence[CategoryRule]) -> int | None:
    """The category id of the first rule (in ``rules``' given order) whose
    ``contains_text`` appears in ``payee_text``, case-insensitively.

    ``None`` when ``payee_text`` is blank or no rule matches.
    """
    normalized = payee_text.strip().casefold()
    if not normalized:
        return None
    for rule in rules:
        needle = rule.contains_text.strip().casefold()
        if needle and needle in normalized:
            return rule.category_id
    return None
