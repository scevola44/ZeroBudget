"""payee category rules

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-14

Adds ``payee_category_rules``: user-defined "payee contains X -> category Y"
rules, applied only to bank-synced and imported transactions that arrive
with no category of their own (see ``services/payee_rules.py``). A brand-new
table, no data migration needed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payee_category_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("categories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("contains_text", sa.String(length=255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_payee_category_rules_user_id", "payee_category_rules", ["user_id"])
    op.create_index(
        "ix_payee_category_rules_category_id", "payee_category_rules", ["category_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_payee_category_rules_category_id", table_name="payee_category_rules")
    op.drop_index("ix_payee_category_rules_user_id", table_name="payee_category_rules")
    op.drop_table("payee_category_rules")
