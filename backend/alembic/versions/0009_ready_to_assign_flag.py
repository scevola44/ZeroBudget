"""ready to assign flag on transactions

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-12

Lets a transaction be marked as deliberately uncategorized — its purpose is
only to move Ready to Assign (a balance reconcile, a paycheck), not to await
a category. Purely a display/filter signal: it is never read by the Ready to
Assign or category-balance calculations, which key on category_id alone.
No backfill — existing rows default to false and are flagged by hand.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_ready_to_assign",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.alter_column("is_ready_to_assign", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("is_ready_to_assign")
