from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# SHA-256 hex digest.
TOKEN_HASH_LENGTH = 64
FAMILY_ID_LENGTH = 32


class RefreshToken(Base):
    """One issued refresh token; rotating it revokes it and issues a successor.

    Only the SHA-256 of the token is stored, so a database leak does not yield
    usable sessions. Every token descended from one login shares a
    ``family_id``: presenting an already-revoked token means it leaked (or was
    replayed), so the whole family is revoked rather than just that row.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(
        String(TOKEN_HASH_LENGTH), unique=True, index=True, nullable=False
    )
    family_id: Mapped[str] = mapped_column(String(FAMILY_ID_LENGTH), index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
