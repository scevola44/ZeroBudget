from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Plaid linkage. All NULL for manual accounts; all populated for linked
    # accounts (with one row in plaid_items per item_id).
    plaid_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("plaid_items.id", ondelete="CASCADE"), index=True, nullable=True
    )
    plaid_account_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True
    )
    plaid_mask: Mapped[str | None] = mapped_column(String(16), nullable=True)
    plaid_official_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
