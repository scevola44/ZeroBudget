from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SyncRun(Base):
    """One global transaction-sync run.

    Doubles as the daily-quota ledger (used-today = rows since UTC midnight)
    and the scheduler's "when did we last run" state, so both survive
    restarts on SQLite and Postgres alike.
    """

    __tablename__ = "sync_runs"

    TRIGGER_MANUAL = "manual"
    TRIGGER_AUTO = "auto"
    TRIGGER_LINK = "link"

    STATUS_OK = "ok"
    STATUS_PARTIAL = "partial"
    STATUS_ERROR = "error"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_OK)
    added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    modified: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
