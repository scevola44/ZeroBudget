"""cleared flag on transactions

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-28

Lets a transaction be marked as reviewed by the user (YNAB's "cleared"),
distinct from whether it has a category: a payee rule or bank sync can
already have filled in category_id, but that's a guess until the user
confirms it. Backfilled to true for every existing row via server_default —
don't retroactively flag a user's whole history as unreviewed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "cleared",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )
        batch_op.alter_column("cleared", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("cleared")
