"""Enable Banking <-> ZeroBudget amount conversion.

Two things this module owns — do not reimplement them elsewhere:

1. Sign convention. Enable Banking amounts are unsigned strings with a
   separate ``credit_debit_indicator`` (CRDT = money in, DBIT = money out).
   ZeroBudget: ``amount_cents > 0`` means inflow.
2. Currency gate. ZeroBudget is EUR-only. We reject non-EUR transactions
   at the boundary rather than quietly converting at a made-up rate.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

ZEROBUDGET_CURRENCY = "EUR"

CREDIT = "CRDT"
DEBIT = "DBIT"


class NonEurCurrencyError(ValueError):
    """Raised when a bank account or transaction is not EUR-denominated."""

    def __init__(self, currency: str | None) -> None:
        self.currency = currency
        super().__init__(f"Non-EUR currency rejected (currency={currency!r})")


def ensure_eur(currency: str | None) -> None:
    """Raise ``NonEurCurrencyError`` if the given currency isn't EUR."""
    if currency != ZEROBUDGET_CURRENCY:
        raise NonEurCurrencyError(currency)


def bank_amount_to_cents(
    amount: str,
    currency: str | None,
    credit_debit_indicator: str,
) -> int:
    """Convert an Enable Banking transaction amount to signed integer cents.

    Raises ``NonEurCurrencyError`` for non-EUR inputs and ``ValueError`` for
    malformed amounts or unknown indicators.
    """
    ensure_eur(currency)
    try:
        cents = int((Decimal(amount) * 100).quantize(Decimal("1")))
    except InvalidOperation as exc:
        raise ValueError(f"Malformed transaction amount {amount!r}") from exc
    if credit_debit_indicator == CREDIT:
        return cents
    if credit_debit_indicator == DEBIT:
        return -cents
    raise ValueError(f"Unknown credit_debit_indicator {credit_debit_indicator!r}")


def bank_balance_amount_to_cents(amount: str, currency: str | None) -> int:
    """Convert an Enable Banking balance amount to signed integer cents.

    Unlike transaction amounts, balance amounts (Berlin Group NextGenPSD2
    ``balance_amount``) are already signed and carry no separate
    ``credit_debit_indicator``.

    Raises ``NonEurCurrencyError`` for non-EUR inputs and ``ValueError`` for
    malformed amounts.
    """
    ensure_eur(currency)
    try:
        return int((Decimal(amount) * 100).quantize(Decimal("1")))
    except InvalidOperation as exc:
        raise ValueError(f"Malformed balance amount {amount!r}") from exc
