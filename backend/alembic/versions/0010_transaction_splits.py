"""transaction_splits table

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-11

A transaction with split lines has ``category_id = NULL`` at the parent
level; budget activity for a split transaction is attributed per line (see
``services/txn_rows.py``, which flattens each split into its own row for
``budget_calc.py``). No backfill: splits are a new feature, nothing existing
maps onto them.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transaction_splits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
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
    op.create_index("ix_transaction_splits_user_id", "transaction_splits", ["user_id"])
    op.create_index(
        "ix_transaction_splits_transaction_id", "transaction_splits", ["transaction_id"]
    )
    op.create_index("ix_transaction_splits_category_id", "transaction_splits", ["category_id"])


def downgrade() -> None:
    op.drop_index("ix_transaction_splits_category_id", table_name="transaction_splits")
    op.drop_index("ix_transaction_splits_transaction_id", table_name="transaction_splits")
    op.drop_index("ix_transaction_splits_user_id", table_name="transaction_splits")
    op.drop_table("transaction_splits")
