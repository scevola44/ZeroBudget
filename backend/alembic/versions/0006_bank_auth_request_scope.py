"""scope on bank_auth_requests

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-09

Adds a ``scope`` column ("personal" | "shared") to ``bank_auth_requests`` so
the scope chosen when starting a bank link survives the redirect and is
applied to the accounts created on callback. Existing rows are backfilled to
``"personal"``.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("bank_auth_requests") as batch_op:
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
    with op.batch_alter_table("bank_auth_requests") as batch_op:
        batch_op.drop_column("scope")
