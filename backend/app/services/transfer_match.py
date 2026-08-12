"""Finding the two halves of a transfer that arrived as two separate rows.

A bank sync fetches each account independently, so it has no idea that the
-500 leaving checking and the +500 landing in savings are one movement of money.
It writes two unlinked, uncategorized transactions, and until they are linked
they read as real income and real spending everywhere on Insights.

This module is the single place that decides which rows *could* be halves of the
same transfer, so the "link these two" picker and the post-sync suggestion list
can never disagree about what a match is. It is pure over its inputs — the ORM
join happens in the router, mirroring how ``budget_calc`` and ``txn_rows`` are
split.

Matching is deliberately strict. Linking is destructive to the budget: both legs
drop out of Ready to Assign on the assumption that they cancel out, so a false
pair silently invents or destroys money.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from app.services.synthetic_payees import SYNTHETIC_PAYEES

# Bank-generated payees for a transfer are typically "To <account>" or
# "From <account>" (sometimes "Transfer to/from <account>"). Stripped before
# comparing against an account name so only the name itself has to match.
_DIRECTIONAL_PREFIXES = re.compile(
    r"^(transfer\s+)?(to|from)\s+", re.IGNORECASE
)

# How far apart two legs may be dated and still be one transfer. Money leaving
# one bank on Friday can land at another the following Monday, so same-day is
# too strict; much wider and unrelated round-number transactions start pairing.
TRANSFER_MATCH_WINDOW_DAYS = 3

# How far back the suggestion list looks when the caller doesn't say. Older
# unlinked pairs are almost always deliberate, not a sync artifact waiting to be
# tidied up.
SUGGESTION_DEFAULT_DAYS = 90


@dataclass(frozen=True)
class MatchRow:
    id: int
    account_id: int
    category_id: int | None
    date: date
    amount_cents: int  # signed
    payee: str
    transfer_peer_id: int | None


@dataclass(frozen=True)
class SuggestedPair:
    outflow_id: int
    inflow_id: int


@dataclass(frozen=True)
class AccountRef:
    id: int
    name: str
    # True when nothing is ever synced into this account, i.e. no bank sync
    # will independently write the other leg here.
    is_unsynced: bool


@dataclass(frozen=True)
class PayeeMatchedTransfer:
    transaction_id: int
    to_account_id: int


def is_linkable(row: MatchRow) -> bool:
    """Whether ``row`` may be volunteered as one half of a transfer.

    Zero-amount rows are excluded because two of them satisfy "equal and
    opposite" while meaning nothing. Synthetic rows are excluded because they
    describe a balance, not a payment — and two accounts linked on the same day
    produce two opening balances that would otherwise pair perfectly.
    """
    return (
        row.transfer_peer_id is None
        and row.amount_cents != 0
        and row.payee not in SYNTHETIC_PAYEES
    )


def is_match(a: MatchRow, b: MatchRow) -> bool:
    """Whether two rows could be the two legs of one transfer.

    Amounts must be exactly opposite: the budget math excludes both legs rather
    than summing them, which is only equivalent to netting while they cancel
    out. A pair that differs by a transfer fee would quietly leave that fee
    unaccounted for in Ready to Assign.
    """
    return (
        a.id != b.id
        and a.account_id != b.account_id
        and a.amount_cents == -b.amount_cents
        and abs((a.date - b.date).days) <= TRANSFER_MATCH_WINDOW_DAYS
    )


def find_candidates(target: MatchRow, rows: Iterable[MatchRow]) -> list[MatchRow]:
    """Rows that could be ``target``'s other leg, closest date first."""
    if not is_linkable(target):
        return []
    matches = [row for row in rows if is_linkable(row) and is_match(target, row)]
    return sorted(matches, key=lambda row: (abs((row.date - target.date).days), row.id))


def suggest_pairs(rows: Sequence[MatchRow]) -> list[SuggestedPair]:
    """Disjoint suggested transfer pairs, most confident first.

    Only uncategorized rows are volunteered. A category is a deliberate
    statement that the row is spending, and a suggestion should never invite the
    user to undo their own intent with one click — explicit linking may still
    override it.

    Every returned pair is disjoint: a row that could pair with two others is
    offered once, against its closest match. That keeps the list honest (the
    same transaction never appears twice) and makes confirming the suggestions
    in any order always succeed.
    """
    candidates = [row for row in rows if is_linkable(row) and row.category_id is None]

    # An exact amount match is required, so rows of different magnitudes can
    # never pair — bucketing on magnitude keeps this near-linear instead of
    # comparing every row against every other.
    by_magnitude: dict[int, list[MatchRow]] = defaultdict(list)
    for row in candidates:
        by_magnitude[abs(row.amount_cents)].append(row)

    scored: list[tuple[int, MatchRow, MatchRow]] = []
    for bucket in by_magnitude.values():
        outflows = [row for row in bucket if row.amount_cents < 0]
        inflows = [row for row in bucket if row.amount_cents > 0]
        for outflow in outflows:
            for inflow in inflows:
                if is_match(outflow, inflow):
                    days_apart = abs((inflow.date - outflow.date).days)
                    scored.append((days_apart, outflow, inflow))

    scored.sort(
        key=lambda entry: (
            entry[0],
            -abs(entry[1].amount_cents),
            entry[1].id,
            entry[2].id,
        )
    )

    claimed: set[int] = set()
    suggestions: list[SuggestedPair] = []
    for _, outflow, inflow in scored:
        if outflow.id in claimed or inflow.id in claimed:
            continue
        claimed.update((outflow.id, inflow.id))
        suggestions.append(SuggestedPair(outflow_id=outflow.id, inflow_id=inflow.id))
    return suggestions


def _normalized_for_account_match(text: str) -> str:
    """Fold a payee or account name down to the form compared for equality.

    Deliberately narrow: this only strips a fixed set of directional prefixes
    and surrounding whitespace/punctuation, then casefolds. No fuzzy or
    substring matching — a wrong guess here silently turns real spending (or a
    real transfer to somewhere else) into a transfer, which invents or hides
    money the same way a bad amount/date pairing would.
    """
    stripped = _DIRECTIONAL_PREFIXES.sub("", text.strip())
    return stripped.strip(" \t:-").casefold()


def payee_names_account(payee: str, account_name: str) -> bool:
    """Whether ``payee`` reads as "(Transfer) To/From <account_name>"."""
    if not payee.strip() or not account_name.strip():
        return False
    return _normalized_for_account_match(payee) == account_name.strip().casefold()


def suggest_payee_matched_transfers(
    rows: Sequence[MatchRow],
    accounts: Sequence[AccountRef],
    claimed_ids: Iterable[int] = (),
) -> list[PayeeMatchedTransfer]:
    """Rows whose payee names an unsynced account of the user's, unlinked side.

    Restricted to unsynced target accounts: a synced account's other leg will
    arrive on its own from the next bank sync, so creating it here too would
    leave a duplicate, orphaned row behind. ``claimed_ids`` excludes rows
    ``suggest_pairs`` already offered, so the two suggestion lists never
    overlap.
    """
    already_claimed = set(claimed_ids)
    suggestions: list[PayeeMatchedTransfer] = []
    for row in rows:
        if not is_linkable(row) or row.category_id is not None or row.id in already_claimed:
            continue
        for account in accounts:
            if not account.is_unsynced or account.id == row.account_id:
                continue
            if payee_names_account(row.payee, account.name):
                suggestions.append(
                    PayeeMatchedTransfer(transaction_id=row.id, to_account_id=account.id)
                )
                break
    return suggestions
