"""Unit tests for the Plaid <-> ZeroBudget amount helper.

The two invariants we care about:

- **Sign flip.** Plaid amounts are positive for outflows; ZeroBudget amounts
  are positive for inflows. Conversion must negate.
- **Currency gate.** Non-EUR inputs raise, never silently convert.
"""

from decimal import Decimal

import pytest

from app.services.plaid_amount import NonEurCurrencyError, plaid_amount_to_cents


def test_positive_plaid_becomes_negative_zerobudget():
    # Plaid: $12.34 purchase (debit, positive) -> ZeroBudget: outflow (negative cents)
    assert plaid_amount_to_cents(12.34, "EUR", None) == -1234


def test_negative_plaid_becomes_positive_zerobudget():
    # Plaid: -50.00 refund (credit, negative) -> ZeroBudget: inflow (positive cents)
    assert plaid_amount_to_cents(-50.00, "EUR", None) == 5000


def test_decimal_precision_on_known_float_trap():
    # 0.1 + 0.2 = 0.30000000000000004 in float-land. Decimal via str-repr
    # should land on exactly 30 cents (then -30 after sign flip).
    assert plaid_amount_to_cents(0.1 + 0.2, "EUR", None) == -30


def test_accepts_decimal_input():
    assert plaid_amount_to_cents(Decimal("7.89"), "EUR", None) == -789


def test_accepts_string_input():
    assert plaid_amount_to_cents("99.99", "EUR", None) == -9999


def test_zero_amount_is_zero():
    assert plaid_amount_to_cents(0, "EUR", None) == 0


def test_usd_is_rejected():
    with pytest.raises(NonEurCurrencyError):
        plaid_amount_to_cents(12.34, "USD", None)


def test_gbp_is_rejected():
    with pytest.raises(NonEurCurrencyError):
        plaid_amount_to_cents(12.34, "GBP", None)


def test_unofficial_currency_always_rejected():
    # Even with iso=EUR, the presence of an unofficial_currency_code (crypto,
    # reward points, etc.) means we can't trust the amount.
    with pytest.raises(NonEurCurrencyError):
        plaid_amount_to_cents(12.34, "EUR", "BTC")


def test_missing_iso_code_is_rejected():
    with pytest.raises(NonEurCurrencyError):
        plaid_amount_to_cents(12.34, None, None)
