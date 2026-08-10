"""transfer_peer_id on transactions

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-10

Makes transfers first-class: both legs of a transfer carry a
``transfer_peer_id`` pointing at the other leg. UNIQUE enforces that a leg
belongs to at most one pair. Existing rows stay NULL — historical transfers
entered as two loose uncategorized transactions remain unlinked, which is
harmless: they already produce the correct Ready-to-Assign totals.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Batch mode for SQLite; the self-referential FK is named so downgrade can
    # drop it by name.
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(sa.Column("transfer_peer_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_transactions_transfer_peer_id",
            "transactions",
            ["transfer_peer_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_transactions_transfer_peer_id",
            ["transfer_peer_id"],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_index("ix_transactions_transfer_peer_id")
        batch_op.drop_constraint("fk_transactions_transfer_peer_id", type_="foreignkey")
        batch_op.drop_column("transfer_peer_id")
