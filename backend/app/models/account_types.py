# Account "type" values that are off-budget: money in them does not count
# towards Ready to Assign until it is transferred into an on-budget account.
# See app.models.account.Account.type.
OFF_BUDGET_ACCOUNT_TYPES: frozenset[str] = frozenset({"savings"})


def account_on_budget(account_type: str) -> bool:
    """Whether an account of this type feeds Ready to Assign."""
    return account_type not in OFF_BUDGET_ACCOUNT_TYPES
