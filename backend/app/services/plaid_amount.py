"""Plaid <-> ZeroBudget amount conversion.

Two things this module owns — do not reimplement them elsewhere:

1. Sign flip. Plaid: ``amount > 0`` means money leaving the account
   (debit / outflow). ZeroBudget: ``amount_cents > 0`` means inflow.
   So every amount is negated.
2. Currency gate. ZeroBudget is EUR-only. We reject non-EUR transactions
   at the boundary rather than quietly converting at a made-up rate.
"""

from __future__ import annotations

from decimal import Decimal

ZEROBUDGET_CURRENCY = "EUR"


class NonEurCurrencyError(ValueError):
    """Raised when a Plaid account or transaction is not EUR-denominated."""

    def __init__(self, iso: str | None, unofficial: str | None) -> None:
        self.iso_currency_code = iso
        self.unofficial_currency_code = unofficial
        super().__init__(
            f"Non-EUR currency rejected (iso={iso!r}, unofficial={unofficial!r})"
        )


def ensure_eur(iso_currency_code: str | None, unofficial_currency_code: str | None) -> None:
    """Raise ``NonEurCurrencyError`` if the given currency info isn't EUR."""
    if unofficial_currency_code:
        # e.g. crypto or reward-points — always reject.
        raise NonEurCurrencyError(iso_currency_code, unofficial_currency_code)
    if iso_currency_code != ZEROBUDGET_CURRENCY:
        raise NonEurCurrencyError(iso_currency_code, unofficial_currency_code)


def plaid_amount_to_cents(
    amount: float | Decimal | str,
    iso_currency_code: str | None,
    unofficial_currency_code: str | None,
) -> int:
    """Convert a Plaid transaction amount to ZeroBudget signed integer cents.

    Raises ``NonEurCurrencyError`` for non-EUR inputs.
    """
    ensure_eur(iso_currency_code, unofficial_currency_code)
    # ``str()`` on a float preserves its repr, which avoids artefacts like
    # ``Decimal(0.1)`` producing ``0.1000000000000000055511151231257827021181583404541015625``.
    plaid_cents = int((Decimal(str(amount)) * 100).quantize(Decimal("1")))
    return -plaid_cents
