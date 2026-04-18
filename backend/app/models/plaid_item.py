from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PlaidItem(Base):
    """A single linked bank connection (Plaid "Item").

    One user may have many items (Chase + Revolut + ...). Each item owns one
    or more ``Account`` rows via ``accounts.plaid_item_id``.
    """

    __tablename__ = "plaid_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    plaid_item_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Fernet-encrypted Plaid access_token. Never exposed to the client.
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    institution_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # /transactions/sync cursor. NULL means we've never synced; on first call
    # we pass ``cursor=""`` (Plaid's sentinel for "from the beginning").
    transactions_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Last Plaid error code (e.g. ITEM_LOGIN_REQUIRED). Surfaced to the UI so
    # the user knows to reconnect. NULL when the last sync was successful.
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
