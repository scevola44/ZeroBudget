"""deleted external transactions

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-13

Tombstones a bank-imported transaction's ``external_transaction_id`` once the
user deletes it, so ``bank_sync.sync_connection`` can tell "the user removed
this" apart from "never imported" and skip re-inserting it on the next sync.
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
        "deleted_external_transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_transaction_id", sa.String(length=128), nullable=False),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_deleted_external_transactions_user_id",
        "deleted_external_transactions",
        ["user_id"],
    )
    op.create_index(
        "ix_deleted_external_transactions_external_transaction_id",
        "deleted_external_transactions",
        ["external_transaction_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_deleted_external_transactions_external_transaction_id",
        table_name="deleted_external_transactions",
    )
    op.drop_index(
        "ix_deleted_external_transactions_user_id",
        table_name="deleted_external_transactions",
    )
    op.drop_table("deleted_external_transactions")
