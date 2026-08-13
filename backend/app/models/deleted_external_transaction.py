from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DeletedExternalTransaction(Base):
    """Tombstone for a bank-imported ``Transaction`` the user deleted.

    Deleting a ``Transaction`` frees its ``external_transaction_id`` for
    reuse, so the next bank sync can no longer tell "never imported" apart
    from "the user removed this on purpose" by looking at the transactions
    table alone. This row is what makes that distinction, keyed on the same
    id, so ``bank_sync.sync_connection`` can skip re-inserting it.
    """

    __tablename__ = "deleted_external_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    external_transaction_id: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
