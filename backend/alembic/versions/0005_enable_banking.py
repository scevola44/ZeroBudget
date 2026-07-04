"""enable banking integration

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-04

Replaces the Plaid integration with Enable Banking (PSD2). Plaid was
sandbox-only, so its tables/columns are dropped outright — no data migration.
Adds ``bank_connections``, ``bank_auth_requests``, ``sync_runs`` and the new
linkage columns on ``accounts`` / ``transactions``.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- drop Plaid schema -------------------------------------------------
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

    # --- create Enable Banking schema --------------------------------------
    op.create_table(
        "bank_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id_encrypted", sa.Text(), nullable=False),
        sa.Column("aspsp_name", sa.String(length=255), nullable=False),
        sa.Column("aspsp_country", sa.String(length=2), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_bank_connections_user_id", "bank_connections", ["user_id"])

    op.create_table(
        "bank_auth_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=64), nullable=False),
        sa.Column("aspsp_name", sa.String(length=255), nullable=False),
        sa.Column("aspsp_country", sa.String(length=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_bank_auth_requests_user_id", "bank_auth_requests", ["user_id"])
    op.create_index(
        "ix_bank_auth_requests_state", "bank_auth_requests", ["state"], unique=True
    )

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("added", sa.Integer(), nullable=False),
        sa.Column("modified", sa.Integer(), nullable=False),
    )
    op.create_index("ix_sync_runs_started_at", "sync_runs", ["started_at"])

    with op.batch_alter_table("accounts") as batch_op:
        batch_op.add_column(sa.Column("bank_connection_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("bank_account_uid", sa.String(length=128), nullable=True)
        )
        batch_op.add_column(
            sa.Column("bank_account_mask", sa.String(length=16), nullable=True)
        )
        batch_op.add_column(
            sa.Column("bank_product_name", sa.String(length=255), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_accounts_bank_connection_id",
            "bank_connections",
            ["bank_connection_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_accounts_bank_connection_id", ["bank_connection_id"])
        batch_op.create_index(
            "ix_accounts_bank_account_uid", ["bank_account_uid"], unique=True
        )

    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(
            sa.Column("external_transaction_id", sa.String(length=128), nullable=True)
        )
        batch_op.create_index(
            "ix_transactions_external_transaction_id",
            ["external_transaction_id"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_index("ix_transactions_external_transaction_id")
        batch_op.drop_column("external_transaction_id")

    with op.batch_alter_table("accounts") as batch_op:
        batch_op.drop_index("ix_accounts_bank_account_uid")
        batch_op.drop_index("ix_accounts_bank_connection_id")
        batch_op.drop_constraint("fk_accounts_bank_connection_id", type_="foreignkey")
        batch_op.drop_column("bank_product_name")
        batch_op.drop_column("bank_account_mask")
        batch_op.drop_column("bank_account_uid")
        batch_op.drop_column("bank_connection_id")

    op.drop_index("ix_sync_runs_started_at", table_name="sync_runs")
    op.drop_table("sync_runs")
    op.drop_index("ix_bank_auth_requests_state", table_name="bank_auth_requests")
    op.drop_index("ix_bank_auth_requests_user_id", table_name="bank_auth_requests")
    op.drop_table("bank_auth_requests")
    op.drop_index("ix_bank_connections_user_id", table_name="bank_connections")
    op.drop_table("bank_connections")

    # Restore the 0002 Plaid shape so downgrade chains stay intact.
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
