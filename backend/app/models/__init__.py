"""ORM models.

Importing this package registers every model on the shared ``Base.metadata``,
which is what Alembic's autogenerate and ``Base.metadata.create_all`` rely on.
"""

from app.models.account import Account
from app.models.assignment import MonthlyAssignment
from app.models.bank_connection import BankAuthRequest, BankConnection
from app.models.category import Category, CategoryGroup
from app.models.deleted_external_transaction import DeletedExternalTransaction
from app.models.payee import Payee
from app.models.payee_category_rule import PayeeCategoryRule
from app.models.scope import Scope
from app.models.sync_run import SyncRun
from app.models.transaction import Transaction
from app.models.transaction_split import TransactionSplit
from app.models.user import User

__all__ = [
    "Account",
    "BankAuthRequest",
    "BankConnection",
    "Category",
    "CategoryGroup",
    "DeletedExternalTransaction",
    "MonthlyAssignment",
    "Payee",
    "PayeeCategoryRule",
    "Scope",
    "SyncRun",
    "Transaction",
    "TransactionSplit",
    "User",
]
