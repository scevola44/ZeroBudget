"""closed flag on accounts

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-10

Retiring an account must not mean destroying its history: a closed account
keeps every transaction, and so keeps contributing to past budget months and
Insights. It is simply hidden from the account list by default. Existing rows
are backfilled to open.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.add_column(
            sa.Column(
                "closed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.alter_column("closed", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("accounts") as batch_op:
        batch_op.drop_column("closed")
