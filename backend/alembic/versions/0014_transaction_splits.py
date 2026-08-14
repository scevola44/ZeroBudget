"""transaction splits

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-14

Adds ``transaction_splits``: sub-lines of a transaction, each with its own
category and amount. A transaction with splits keeps ``category_id IS NULL``
at the parent level (enforced in the router); the split lines' amounts must
sum to the parent's ``amount_cents`` (also router-enforced, not a DB
constraint — SQLite/Postgres CHECK constraints can't reach across tables).
Brand-new table, no data migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transaction_splits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "transaction_id",
            sa.Integer(),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("memo", sa.String(length=500), nullable=False, server_default=""),
    )
    op.create_index(
        "ix_transaction_splits_transaction_id", "transaction_splits", ["transaction_id"]
    )
    op.create_index(
        "ix_transaction_splits_category_id", "transaction_splits", ["category_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_transaction_splits_category_id", table_name="transaction_splits")
    op.drop_index("ix_transaction_splits_transaction_id", table_name="transaction_splits")
    op.drop_table("transaction_splits")
