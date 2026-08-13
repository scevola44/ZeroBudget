from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Free-form string for now: "checking" / "savings" / "cash".
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="checking")
    # The budget pool this account's money belongs to — see app.models.scope.
    scope_id: Mapped[int] = mapped_column(
        ForeignKey("scopes.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    # A retired account. Its transactions still count towards every past month;
    # it is only hidden from the account list. Closing is the alternative to
    # deleting, which would rewrite budget history.
    closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Bank linkage. All NULL for manual accounts; populated for accounts
    # imported from an Enable Banking session.
    bank_connection_id: Mapped[int | None] = mapped_column(
        ForeignKey("bank_connections.id", ondelete="CASCADE"), index=True, nullable=True
    )
    # Enable Banking account uid — stable per authorized account.
    bank_account_uid: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True
    )
    # Last 4 characters of the IBAN, for display.
    bank_account_mask: Mapped[str | None] = mapped_column(String(16), nullable=True)
    bank_product_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
