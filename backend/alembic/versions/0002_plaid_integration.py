"""plaid integration

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-17

Adds the ``plaid_items`` table plus Plaid linkage columns on ``accounts``
and ``transactions``.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plaid_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plaid_item_id", sa.String(length=64), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("institution_name", sa.String(length=255), nullable=True),
        sa.Column("transactions_cursor", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_plaid_items_user_id", "plaid_items", ["user_id"])
    op.create_index(
        "ix_plaid_items_plaid_item_id", "plaid_items", ["plaid_item_id"], unique=True
    )

    with op.batch_alter_table("accounts") as batch_op:
        batch_op.add_column(sa.Column("plaid_item_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("plaid_account_id", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(sa.Column("plaid_mask", sa.String(length=16), nullable=True))
        batch_op.add_column(
            sa.Column("plaid_official_name", sa.String(length=255), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_accounts_plaid_item_id",
            "plaid_items",
            ["plaid_item_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_accounts_plaid_item_id", ["plaid_item_id"])
        batch_op.create_index(
            "ix_accounts_plaid_account_id", ["plaid_account_id"], unique=True
        )

    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(
            sa.Column("plaid_transaction_id", sa.String(length=64), nullable=True)
        )
        batch_op.create_index(
            "ix_transactions_plaid_transaction_id",
            ["plaid_transaction_id"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_index("ix_transactions_plaid_transaction_id")
        batch_op.drop_column("plaid_transaction_id")

    with op.batch_alter_table("accounts") as batch_op:
        batch_op.drop_index("ix_accounts_plaid_account_id")
        batch_op.drop_index("ix_accounts_plaid_item_id")
        batch_op.drop_constraint("fk_accounts_plaid_item_id", type_="foreignkey")
        batch_op.drop_column("plaid_official_name")
        batch_op.drop_column("plaid_mask")
        batch_op.drop_column("plaid_account_id")
        batch_op.drop_column("plaid_item_id")

    op.drop_index("ix_plaid_items_plaid_item_id", table_name="plaid_items")
    op.drop_index("ix_plaid_items_user_id", table_name="plaid_items")
    op.drop_table("plaid_items")
