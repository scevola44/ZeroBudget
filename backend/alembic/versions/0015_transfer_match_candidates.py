"""transfer_match_candidates

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-14

Adds ``transfer_match_candidates``: a persisted record of transaction pairs
that satisfy ``transfer_match.is_match``, replacing the stateless
recompute-on-every-call heuristic (see ``services/transfer_candidate_store.py``
and ROADMAP.md's Phase 6 TODO). A brand-new table, no data migration in this
revision — existing unlinked transactions are backfilled separately by
``scripts/backfill_transfer_match_candidates.py`` after deploy.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transfer_match_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "transaction_lo_id",
            sa.Integer(),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "transaction_hi_id",
            sa.Integer(),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "transaction_lo_id", "transaction_hi_id", name="uq_transfer_match_candidate_pair"
        ),
    )
    op.create_index(
        "ix_transfer_match_candidates_user_id", "transfer_match_candidates", ["user_id"]
    )
    op.create_index(
        "ix_transfer_match_candidates_transaction_lo_id",
        "transfer_match_candidates",
        ["transaction_lo_id"],
    )
    op.create_index(
        "ix_transfer_match_candidates_transaction_hi_id",
        "transfer_match_candidates",
        ["transaction_hi_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transfer_match_candidates_transaction_hi_id",
        table_name="transfer_match_candidates",
    )
    op.drop_index(
        "ix_transfer_match_candidates_transaction_lo_id",
        table_name="transfer_match_candidates",
    )
    op.drop_index("ix_transfer_match_candidates_user_id", table_name="transfer_match_candidates")
    op.drop_table("transfer_match_candidates")
