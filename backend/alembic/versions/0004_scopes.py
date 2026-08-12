"""scopes on accounts and category groups

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-30

Adds a ``scope`` column ("personal" | "shared") to ``accounts`` and
``category_groups`` so a single user can run two independent budget pools
side by side. Existing rows are backfilled to ``"personal"``.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default backfills existing rows; we drop it afterwards so future
    # inserts must specify the value explicitly (matches the existing
    # convention for required columns).
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.add_column(
            sa.Column(
                "scope",
                sa.String(length=16),
                nullable=False,
                server_default="personal",
            )
        )
        batch_op.alter_column("scope", server_default=None)

    with op.batch_alter_table("category_groups") as batch_op:
        batch_op.add_column(
            sa.Column(
                "scope",
                sa.String(length=16),
                nullable=False,
                server_default="personal",
            )
        )
        batch_op.alter_column("scope", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("category_groups") as batch_op:
        batch_op.drop_column("scope")
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.drop_column("scope")
