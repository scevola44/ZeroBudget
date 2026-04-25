from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, String, func
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
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payee: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    memo: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # Signed integer cents. Positive = inflow, negative = outflow.
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Plaid's globally-unique transaction id. NULL for manually-entered rows;
    # globally unique for imported rows so /transactions/sync retries stay
    # idempotent.
    plaid_transaction_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
