"""Payees the app writes for itself, not for money changing hands.

Both rows below are bookkeeping artifacts: they exist to make a derived balance
agree with the bank, and no counterparty was ever involved. Anything that
reasons about what a transaction *means* — most notably transfer matching, where
two of these with opposite amounts would look like a textbook transfer — needs
to be able to recognize and skip them.
"""

# Written by ``routers.accounts`` when the user reconciles an account balance.
BALANCE_ADJUSTMENT_PAYEE = "Balance Adjustment"

# Written by ``services.bank_sync`` on an account's first sync, so the derived
# balance matches the bank despite the limited fetch window.
OPENING_BALANCE_PAYEE = "Opening Balance"

SYNTHETIC_PAYEES: frozenset[str] = frozenset(
    {BALANCE_ADJUSTMENT_PAYEE, OPENING_BALANCE_PAYEE}
)
