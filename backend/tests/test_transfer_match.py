"""Which imported rows may be paired as the two legs of one transfer.

The rules are deliberately strict: linking drops both legs out of Ready to
Assign on the assumption they cancel out, so a false pair silently invents or
destroys money.
"""

from datetime import date, timedelta

from app.services.synthetic_payees import BALANCE_ADJUSTMENT_PAYEE, OPENING_BALANCE_PAYEE
from app.services.transfer_match import (
    TRANSFER_MATCH_WINDOW_DAYS,
    AccountRef,
    MatchRow,
    find_candidates,
    is_linkable,
    is_match,
    payee_names_account,
    suggest_pairs,
    suggest_payee_matched_transfers,
)

CHECKING = 1
SAVINGS = 2
JOINT = 3

APRIL_2 = date(2026, 4, 2)


def _row(
    row_id: int,
    account_id: int,
    amount_cents: int,
    *,
    on: date = APRIL_2,
    category_id: int | None = None,
    payee: str = "Transfer",
    transfer_peer_id: int | None = None,
) -> MatchRow:
    return MatchRow(
        id=row_id,
        account_id=account_id,
        category_id=category_id,
        date=on,
        amount_cents=amount_cents,
        payee=payee,
        transfer_peer_id=transfer_peer_id,
    )


def test_opposite_amounts_in_different_accounts_on_the_same_day_match():
    assert is_match(_row(1, CHECKING, -60_000), _row(2, SAVINGS, 60_000))


def test_amounts_that_differ_by_a_fee_do_not_match():
    # Excluding both legs from Ready to Assign is only equivalent to netting
    # them while they cancel exactly; a 50c fee would vanish from the budget.
    assert not is_match(_row(1, CHECKING, -60_000), _row(2, SAVINGS, 59_950))


def test_two_rows_in_the_same_account_do_not_match():
    assert not is_match(_row(1, CHECKING, -60_000), _row(2, CHECKING, 60_000))


def test_same_sign_amounts_do_not_match():
    assert not is_match(_row(1, CHECKING, 60_000), _row(2, SAVINGS, 60_000))


def test_legs_dated_at_the_edge_of_the_window_still_match():
    settled = APRIL_2 + timedelta(days=TRANSFER_MATCH_WINDOW_DAYS)
    assert is_match(_row(1, CHECKING, -60_000), _row(2, SAVINGS, 60_000, on=settled))


def test_legs_dated_beyond_the_window_do_not_match():
    settled = APRIL_2 + timedelta(days=TRANSFER_MATCH_WINDOW_DAYS + 1)
    assert not is_match(_row(1, CHECKING, -60_000), _row(2, SAVINGS, 60_000, on=settled))


def test_a_row_already_in_a_transfer_is_not_linkable():
    assert not is_linkable(_row(1, CHECKING, -60_000, transfer_peer_id=2))


def test_a_zero_amount_row_is_not_linkable():
    # Two of them would satisfy "equal and opposite" while meaning nothing.
    assert not is_linkable(_row(1, CHECKING, 0))


def test_reconciling_rows_are_not_linkable():
    # Two accounts linked on the same day produce two opening balances that
    # would otherwise pair perfectly.
    assert not is_linkable(_row(1, CHECKING, -60_000, payee=OPENING_BALANCE_PAYEE))
    assert not is_linkable(_row(2, SAVINGS, 60_000, payee=BALANCE_ADJUSTMENT_PAYEE))


def test_candidates_are_ordered_by_how_close_their_dates_are():
    target = _row(1, CHECKING, -60_000)
    far = _row(2, SAVINGS, 60_000, on=date(2026, 4, 5))
    near = _row(3, JOINT, 60_000, on=date(2026, 4, 3))

    assert [row.id for row in find_candidates(target, [far, near])] == [near.id, far.id]


def test_candidates_exclude_rows_already_linked():
    target = _row(1, CHECKING, -60_000)
    taken = _row(2, SAVINGS, 60_000, transfer_peer_id=99)

    assert find_candidates(target, [taken]) == []


def test_a_categorized_row_can_still_be_offered_as_a_candidate():
    # Explicit linking may overrule a category; only the suggestion list stays
    # out of the way of a deliberate categorization.
    target = _row(1, CHECKING, -60_000)
    categorized = _row(2, SAVINGS, 60_000, category_id=7)

    assert [row.id for row in find_candidates(target, [categorized])] == [2]


def test_suggestions_pair_an_outflow_with_its_matching_inflow():
    rows = [_row(1, CHECKING, -60_000), _row(2, SAVINGS, 60_000)]

    pairs = suggest_pairs(rows)

    assert len(pairs) == 1
    assert (pairs[0].outflow_id, pairs[0].inflow_id) == (1, 2)


def test_suggestions_leave_categorized_rows_alone():
    # A category is a deliberate statement that the row is spending; a
    # suggestion should never invite undoing that with one click.
    rows = [_row(1, CHECKING, -60_000, category_id=7), _row(2, SAVINGS, 60_000)]

    assert suggest_pairs(rows) == []


def test_suggestions_ignore_unrelated_rows():
    rows = [
        _row(1, CHECKING, -60_000),
        _row(2, SAVINGS, 60_000),
        _row(3, CHECKING, -1_250, payee="Coffee"),
        _row(4, SAVINGS, 3_000, payee="Interest"),
    ]

    pairs = suggest_pairs(rows)

    assert [(p.outflow_id, p.inflow_id) for p in pairs] == [(1, 2)]


def test_a_row_matching_two_others_is_suggested_once_against_the_closer_one():
    # Otherwise the same transaction shows up in two suggestions and confirming
    # the first makes the second fail.
    outflow = _row(1, CHECKING, -60_000)
    close = _row(2, SAVINGS, 60_000, on=date(2026, 4, 3))
    distant = _row(3, JOINT, 60_000, on=date(2026, 4, 5))

    pairs = suggest_pairs([outflow, close, distant])

    assert [(p.outflow_id, p.inflow_id) for p in pairs] == [(1, 2)]


def test_every_suggested_row_appears_in_at_most_one_pair():
    rows = [
        _row(1, CHECKING, -60_000),
        _row(2, SAVINGS, 60_000),
        _row(3, CHECKING, -60_000),
        _row(4, JOINT, 60_000),
    ]

    pairs = suggest_pairs(rows)
    used = [row_id for pair in pairs for row_id in (pair.outflow_id, pair.inflow_id)]

    assert len(pairs) == 2
    assert sorted(used) == [1, 2, 3, 4]


def test_a_payee_naming_the_account_exactly_matches():
    assert payee_names_account("Savings", "Savings")


def test_a_payee_with_a_to_prefix_matches():
    assert payee_names_account("To Savings", "Savings")


def test_a_payee_with_a_from_prefix_matches():
    assert payee_names_account("From Savings", "Savings")


def test_a_payee_with_a_transfer_to_prefix_matches():
    assert payee_names_account("Transfer to Savings", "Savings")


def test_payee_matching_ignores_case_and_surrounding_whitespace():
    assert payee_names_account("  TO   savings  ", "Savings")


def test_a_payee_that_merely_contains_the_account_name_does_not_match():
    # No fuzzy/substring matching: a real merchant sharing a word with an
    # account name must never be silently turned into a transfer.
    assert not payee_names_account("Savings Superstore", "Savings")


def test_a_payee_naming_an_unrelated_account_does_not_match():
    assert not payee_names_account("To Rent", "Savings")


def test_an_empty_payee_does_not_match():
    assert not payee_names_account("", "Savings")


def test_payee_matched_transfers_are_suggested_for_unsynced_accounts():
    rows = [_row(1, CHECKING, -60_000, category_id=None, payee="To Savings")]
    accounts = [AccountRef(id=SAVINGS, name="Savings", is_unsynced=True)]

    suggestions = suggest_payee_matched_transfers(rows, accounts)

    assert len(suggestions) == 1
    assert suggestions[0].transaction_id == 1
    assert suggestions[0].to_account_id == SAVINGS


def test_payee_matched_transfers_skip_synced_accounts():
    # The next bank sync writes the real other leg there on its own; creating
    # one here too would leave a duplicate, orphaned row behind.
    rows = [_row(1, CHECKING, -60_000, payee="To Savings")]
    accounts = [AccountRef(id=SAVINGS, name="Savings", is_unsynced=False)]

    assert suggest_payee_matched_transfers(rows, accounts) == []


def test_payee_matched_transfers_skip_categorized_rows():
    rows = [_row(1, CHECKING, -60_000, category_id=7, payee="To Savings")]
    accounts = [AccountRef(id=SAVINGS, name="Savings", is_unsynced=True)]

    assert suggest_payee_matched_transfers(rows, accounts) == []


def test_payee_matched_transfers_skip_rows_already_claimed_by_amount_matching():
    rows = [_row(1, CHECKING, -60_000, payee="To Savings")]
    accounts = [AccountRef(id=SAVINGS, name="Savings", is_unsynced=True)]

    assert suggest_payee_matched_transfers(rows, accounts, claimed_ids={1}) == []


def test_payee_matched_transfers_skip_unrelated_payees():
    rows = [_row(1, CHECKING, -1_250, payee="Coffee")]
    accounts = [AccountRef(id=SAVINGS, name="Savings", is_unsynced=True)]

    assert suggest_payee_matched_transfers(rows, accounts) == []
