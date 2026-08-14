from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TransferMatchCandidate(Base):
    """A persisted record that two transactions satisfy ``transfer_match.is_match``.

    Replaces recomputing ``transfer_match``'s pairwise comparison from scratch on
    every ``/transfer-candidates`` and ``/transfer-suggestions`` call.
    ``services/transfer_candidate_store.py`` is the only writer — it keeps this
    table in sync at each write chokepoint that can change whether a pair
    matches (create, edit, link, unlink); deletes cascade automatically via the
    FKs below.

    Deliberately just the matched pair, not a verdict: unlike the staging table
    ROADMAP.md's Phase 6 explicitly rejected, nothing here is read by
    ``budget_calc`` or ``insights_calc`` — a row means only "these two could be
    linked," never "this is a transfer," so it can't become a second source of
    truth for the budget math.
    """

    __tablename__ = "transfer_match_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # The pair's two transaction ids, always stored with the smaller id first —
    # the only thing that makes a (lo, hi) pair well-defined regardless of
    # which leg triggered the recompute, and what the unique constraint dedupes
    # on.
    transaction_lo_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    transaction_hi_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "transaction_lo_id", "transaction_hi_id", name="uq_transfer_match_candidate_pair"
        ),
    )
