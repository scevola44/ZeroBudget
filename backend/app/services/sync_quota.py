"""Global daily sync quota, backed by the ``sync_runs`` table.

"Today" is the UTC calendar day — simple to reason about and to explain in
the UI, and restart-proof because the ledger lives in the database.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import SyncRun


def _utc_midnight(now: datetime) -> datetime:
    return now.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)


async def runs_today(db: AsyncSession, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    count = await db.scalar(
        select(func.count())
        .select_from(SyncRun)
        .where(SyncRun.started_at >= _utc_midnight(now))
    )
    return int(count or 0)


async def quota_remaining(
    db: AsyncSession, settings: Settings, now: datetime | None = None
) -> int:
    used = await runs_today(db, now)
    return max(settings.sync_max_per_day - used, 0)


async def latest_run(db: AsyncSession) -> SyncRun | None:
    return (
        await db.execute(select(SyncRun).order_by(SyncRun.started_at.desc()).limit(1))
    ).scalar_one_or_none()
