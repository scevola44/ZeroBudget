"""ORM models.

Importing this package registers every model on the shared ``Base.metadata``,
which is what Alembic's autogenerate and ``Base.metadata.create_all`` rely on.
"""

from app.models.account import Account
from app.models.assignment import MonthlyAssignment
from app.models.category import Category, CategoryGroup
from app.models.plaid_item import PlaidItem
from app.models.transaction import Transaction
from app.models.user import User

__all__ = [
    "Account",
    "Category",
    "CategoryGroup",
    "MonthlyAssignment",
    "PlaidItem",
    "Transaction",
    "User",
]
