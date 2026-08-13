from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class BankConnection(Base):
    """A single authorized bank connection (Enable Banking "session").

    One user may have many connections (one per bank). Each connection owns
    one or more ``Account`` rows via ``accounts.bank_connection_id``.
    """

    __tablename__ = "bank_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Fernet-encrypted Enable Banking session id. Never exposed to the client.
    session_id_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    aspsp_name: Mapped[str] = mapped_column(String(255), nullable=False)
    aspsp_country: Mapped[str] = mapped_column(String(2), nullable=False)
    # PSD2 consent expiry (session access.valid_until). After this the bank
    # rejects data calls and the user must re-authorize.
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Last sync error code (e.g. SESSION_EXPIRED). Surfaced to the UI so the
    # user knows to reconnect. NULL when the last sync was successful.
    last_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BankAuthRequest(Base):
    """A pending redirect-based bank authorization.

    Created when the user picks a bank; the row's ``state`` is round-tripped
    through the bank redirect and validated on callback (anti code-injection),
    then the row is deleted. Rows older than an hour are treated as expired.
    """

    __tablename__ = "bank_auth_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    state: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    aspsp_name: Mapped[str] = mapped_column(String(255), nullable=False)
    aspsp_country: Mapped[str] = mapped_column(String(2), nullable=False)
    # Scope chosen when the user started the link, carried across the redirect
    # so the accounts created on callback land in the right RTA pool.
    scope_id: Mapped[int] = mapped_column(
        ForeignKey("scopes.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
