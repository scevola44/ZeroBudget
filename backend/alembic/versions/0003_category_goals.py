"""category goals

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-25

DESTRUCTIVE: deletes every existing row in ``categories``, ``category_groups``,
and ``monthly_assignments`` before adding the new NOT NULL goal columns. This
is intentional — the product decision is to clean the slate so users recreate
their categories with goals attached. Existing transactions are kept; their
``category_id`` is set to NULL (the same effect as the existing ON DELETE SET
NULL FK rule, made explicit so behavior matches on every backend).

The downgrade only drops the new columns; it does NOT restore the deleted
rows.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Wipe order matters: assignments depend on categories, and we want to
    # leave transactions intact (just unassigned). Spell every step out so
    # the behavior is identical on Postgres and SQLite.
    op.execute("DELETE FROM monthly_assignments")
    op.execute("UPDATE transactions SET category_id = NULL")
    op.execute("DELETE FROM categories")
    op.execute("DELETE FROM category_groups")

    with op.batch_alter_table("categories") as batch_op:
        batch_op.add_column(
            sa.Column("goal_kind", sa.String(length=16), nullable=False)
        )
        batch_op.add_column(
            sa.Column("goal_amount_cents", sa.BigInteger(), nullable=False)
        )
        batch_op.add_column(sa.Column("goal_target_month", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("categories") as batch_op:
        batch_op.drop_column("goal_target_month")
        batch_op.drop_column("goal_amount_cents")
        batch_op.drop_column("goal_kind")
