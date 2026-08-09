"""Unit tests for Enable Banking amount normalization."""

import pytest

from app.services.bank_amount import (
    NonEurCurrencyError,
    bank_amount_to_cents,
    bank_balance_amount_to_cents,
    ensure_eur,
)


def test_debit_is_negative():
    assert bank_amount_to_cents("42.50", "EUR", "DBIT") == -4250


def test_credit_is_positive():
    assert bank_amount_to_cents("1250.00", "EUR", "CRDT") == 125000


def test_string_decimals_are_exact():
    # 0.1-style values must not pick up float artefacts.
    assert bank_amount_to_cents("0.10", "EUR", "CRDT") == 10
    assert bank_amount_to_cents("19.99", "EUR", "DBIT") == -1999


def test_non_eur_rejected():
    with pytest.raises(NonEurCurrencyError):
        bank_amount_to_cents("10.00", "USD", "DBIT")
    with pytest.raises(NonEurCurrencyError):
        ensure_eur("SEK")
    with pytest.raises(NonEurCurrencyError):
        ensure_eur(None)


def test_eur_accepted():
    ensure_eur("EUR")


def test_eur_accepted_case_and_whitespace_insensitive():
    ensure_eur("eur")
    ensure_eur("Eur")
    ensure_eur(" EUR ")


def test_unknown_indicator_rejected():
    with pytest.raises(ValueError):
        bank_amount_to_cents("10.00", "EUR", "WHAT")


def test_malformed_amount_rejected():
    with pytest.raises(ValueError):
        bank_amount_to_cents("ten euros", "EUR", "DBIT")


def test_balance_amount_is_already_signed():
    assert bank_balance_amount_to_cents("1250.00", "EUR") == 125000
    assert bank_balance_amount_to_cents("-42.50", "EUR") == -4250


def test_balance_amount_rejects_non_eur():
    with pytest.raises(NonEurCurrencyError):
        bank_balance_amount_to_cents("10.00", "USD")


def test_balance_amount_rejects_malformed():
    with pytest.raises(ValueError):
        bank_balance_amount_to_cents("ten euros", "EUR")
