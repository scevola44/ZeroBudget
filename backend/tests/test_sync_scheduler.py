"""Tests for the auto-sync decision logic."""

from datetime import datetime, timedelta, timezone

from app.config import Settings
from app.services.sync_scheduler import auto_sync_interval, should_run_auto_sync

NOW = datetime(2026, 7, 4, 12, 0, tzinfo=timezone.utc)


def _settings(mode: str = "auto", max_per_day: int = 4) -> Settings:
    return Settings(sync_mode=mode, sync_max_per_day=max_per_day)


def test_interval_divides_day_by_quota():
    assert auto_sync_interval(_settings(max_per_day=4)) == timedelta(hours=6)
    assert auto_sync_interval(_settings(max_per_day=24)) == timedelta(hours=1)


def test_interval_survives_zero_quota():
    assert auto_sync_interval(_settings(max_per_day=0)) == timedelta(hours=24)


def test_runs_when_never_synced():
    assert should_run_auto_sync(NOW, None, 0, True, _settings())


def test_skips_in_manual_mode():
    assert not should_run_auto_sync(NOW, None, 0, True, _settings(mode="manual"))


def test_skips_without_connections():
    assert not should_run_auto_sync(NOW, None, 0, False, _settings())


def test_skips_when_quota_exhausted():
    stale = NOW - timedelta(hours=23)
    assert not should_run_auto_sync(NOW, stale, 4, True, _settings(max_per_day=4))


def test_skips_when_last_run_is_recent():
    recent = NOW - timedelta(hours=2)
    assert not should_run_auto_sync(NOW, recent, 1, True, _settings(max_per_day=4))


def test_runs_when_interval_elapsed():
    due = NOW - timedelta(hours=6)
    assert should_run_auto_sync(NOW, due, 1, True, _settings(max_per_day=4))


def test_naive_last_run_treated_as_utc():
    # SQLite hands back naive datetimes; they must compare as UTC.
    due_naive = (NOW - timedelta(hours=7)).replace(tzinfo=None)
    assert should_run_auto_sync(NOW, due_naive, 1, True, _settings(max_per_day=4))
