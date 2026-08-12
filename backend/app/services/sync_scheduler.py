"""In-process automatic sync scheduler.

Started from the FastAPI lifespan when ``SYNC_MODE=auto``. Runs as a single
asyncio task that wakes every few minutes, checks the database, and fires a
global sync when one is due. All state (last run, daily quota) lives in the
``sync_runs`` table, so restarts never double-run or lose the daily count.

Assumes a single backend process — the deploy model of this app. Running
multiple replicas against one database could double-sync (harmless for data
thanks to dedup, but wasteful against the API quota).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.models import BankConnection, SyncRun
from app.services.bank_sync import run_global_sync
from app.services.banking_client import BankingClient
from app.services.sync_quota import latest_run, runs_today

logger = logging.getLogger(__name__)

WAKE_INTERVAL_SECONDS = 300


def auto_sync_interval(settings: Settings) -> timedelta:
    """Spacing between automatic runs: the day divided evenly by the quota."""
    return timedelta(hours=24) / max(settings.sync_max_per_day, 1)


def should_run_auto_sync(
    now: datetime,
    last_run_at: datetime | None,
    runs_today_count: int,
    has_connections: bool,
    settings: Settings,
) -> bool:
    """Pure decision function — the scheduler loop and tests share it."""
    if settings.sync_mode != "auto":
        return False
    if not has_connections:
        return False
    if runs_today_count >= settings.sync_max_per_day:
        return False
    if last_run_at is None:
        return True
    if last_run_at.tzinfo is None:
        last_run_at = last_run_at.replace(tzinfo=timezone.utc)
    return now - last_run_at >= auto_sync_interval(settings)


async def _tick(
    session_factory: async_sessionmaker[AsyncSession],
    make_client,
    settings: Settings,
) -> None:
    async with session_factory() as db:
        now = datetime.now(timezone.utc)
        last = await latest_run(db)
        used = await runs_today(db, now)
        has_connections = (
            await db.scalar(select(func.count()).select_from(BankConnection)) or 0
        ) > 0
        if not should_run_auto_sync(
            now, last.started_at if last else None, used, has_connections, settings
        ):
            return
        client: BankingClient = make_client()
        run, _ = await run_global_sync(db, client, SyncRun.TRIGGER_AUTO, settings)
        await db.commit()
        logger.info(
            "Auto sync run finished: status=%s added=%d modified=%d",
            run.status,
            run.added,
            run.modified,
        )


async def scheduler_loop(
    session_factory: async_sessionmaker[AsyncSession],
    make_client,
    settings: Settings | None = None,
) -> None:
    """Run forever; individual tick failures are logged, never fatal."""
    settings = settings or get_settings()
    logger.info(
        "Auto-sync scheduler started: %d run(s)/day, one every %s",
        settings.sync_max_per_day,
        auto_sync_interval(settings),
    )
    while True:
        try:
            await _tick(session_factory, make_client, settings)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Auto sync tick failed; will retry on next wake")
        await asyncio.sleep(WAKE_INTERVAL_SECONDS)
