from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Nullable: when NULL and amount > 0 this row represents unassigned inflow
    # (the source of "Ready to Assign").
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # True marks an uncategorized row as *deliberately* uncategorized — its
    # whole purpose is to move Ready to Assign (a balance reconcile, a
    # paycheck) rather than needing the user's attention. Never set alongside
    # category_id (see routers.transactions). Invisible to budget math: it
    # never reaches TxnRow, so feeds_ready_to_assign treats a flagged row
    # exactly like any other uncategorized inflow — this only changes what the
    # "Unassigned" filter shows.
    is_ready_to_assign: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # Nullable: no payee typed/matched. Resolved to a Payee row on write via
    # services.payees.resolve_payee — see that module for why this isn't a
    # free-text column.
    payee_id: Mapped[int | None] = mapped_column(
        ForeignKey("payees.id", ondelete="SET NULL"), index=True, nullable=True
    )
    memo: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # Signed integer cents. Positive = inflow, negative = outflow.
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Provider dedup key, NULL for manually-entered rows. For Enable Banking
    # imports: "{account.id}:{entry_reference}" when the bank supplies an
    # entry reference, else "{account.id}:h:{sha256-prefix}" over the txn's
    # stable fields — windowed re-fetches stay idempotent either way.
    external_transaction_id: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True, index=True
    )
    # Set on both legs of a transfer, each pointing at the other. UNIQUE so a
    # leg can only ever belong to one pair. SET NULL rather than CASCADE: the
    # API deletes both legs itself, and a cascade on a mutually-referencing
    # pair has no well-defined order.
    transfer_peer_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
