"""Category suggestion: exact-payee recency ranking, fuzzy-payee fallback."""

from datetime import date

from app.services.category_suggest import PayeeHistoryRow, suggest_categories

GROCERIES = 1
DINING = 2
GAS = 3

JAN_1 = date(2026, 1, 1)


def _row(
    row_id: int,
    category_id: int,
    *,
    on: date = JAN_1,
    payee: str = "Store From Home",
) -> PayeeHistoryRow:
    return PayeeHistoryRow(id=row_id, payee=payee, category_id=category_id, date=on)


def test_no_history_suggests_nothing():
    assert suggest_categories("Store From Home", []) == []


def test_exact_match_single_category():
    rows = [_row(1, GROCERIES)]
    assert suggest_categories("Store From Home", rows) == [GROCERIES]


def test_exact_match_is_case_insensitive():
    rows = [_row(1, GROCERIES, payee="store from home")]
    assert suggest_categories("STORE FROM HOME", rows) == [GROCERIES]


def test_exact_match_ranks_categories_by_recency_of_use():
    rows = [
        _row(1, GROCERIES, on=date(2026, 1, 1)),
        _row(2, DINING, on=date(2026, 2, 1)),
        _row(3, GAS, on=date(2026, 3, 1)),
    ]
    assert suggest_categories("Store From Home", rows) == [GAS, DINING, GROCERIES]


def test_exact_match_dedupes_a_category_to_its_most_recent_use():
    rows = [
        _row(1, GROCERIES, on=date(2026, 1, 1)),
        _row(2, DINING, on=date(2026, 2, 1)),
        _row(3, GROCERIES, on=date(2026, 3, 1)),
    ]
    assert suggest_categories("Store From Home", rows) == [GROCERIES, DINING]


def test_unrelated_history_is_not_offered_as_exact_match():
    rows = [_row(1, GROCERIES, payee="Electric Company")]
    assert suggest_categories("Store From Home", rows) == []


def test_fuzzy_match_on_bank_added_prefix_noise():
    rows = [_row(1, GROCERIES, payee="Visa: Store From Home")]
    assert suggest_categories("Store From Home", rows) == [GROCERIES]


def test_fuzzy_match_is_symmetric():
    rows = [_row(1, GROCERIES, payee="Store From Home")]
    assert suggest_categories("Visa: Store From Home", rows) == [GROCERIES]


def test_fuzzy_match_below_threshold_suggests_nothing():
    rows = [_row(1, GROCERIES, payee="Electric Company")]
    assert suggest_categories("Store From Home", rows) == []


def test_fuzzy_match_picks_the_closer_of_two_similar_payees():
    rows = [
        _row(1, GROCERIES, payee="Visa: Store From Home"),
        _row(2, GAS, payee="Store From Home Express"),
    ]
    assert suggest_categories("Store From Home", rows) == [GROCERIES]


def test_fuzzy_match_ranks_the_matched_payees_categories_by_recency():
    rows = [
        _row(1, GROCERIES, payee="Visa: Store From Home", on=date(2026, 1, 1)),
        _row(2, DINING, payee="Visa: Store From Home", on=date(2026, 2, 1)),
    ]
    assert suggest_categories("Store From Home", rows) == [DINING, GROCERIES]
