"""Unit tests for ``app.services.bank_sync``.

We stand up a real in-memory SQLite session (same as the API tests) but swap
the banking client for a fake that hands back canned responses. This
exercises the full DB code path — inserts, dedup lookups, timestamp
persistence — without touching the network.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Account, BankConnection, SyncRun, Transaction, User
from app.services.bank_sync import run_global_sync, sync_connection
from app.services.banking_client import BankingError
from app.services.encryption import encrypt
from app.services.sync_quota import latest_run, quota_remaining, runs_today
from tests.conftest import _enable_sqlite_fks


@dataclass
class FakeBankingClient:
    transactions_by_uid: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    error: BankingError | None = None
    calls: list[tuple[str, date]] = field(default_factory=list)

    async def get_transactions(self, account_uid: str, date_from: date) -> list[dict[str, Any]]:
        self.calls.append((account_uid, date_from))
        if self.error is not None:
            raise self.error
        return self.transactions_by_uid.get(account_uid, [])


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine.sync_engine, "connect", _enable_sqlite_fks)
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _seed(db: AsyncSession) -> tuple[User, BankConnection, Account]:
    user = User(email="alice@example.com", hashed_password="x")
    db.add(user)
    await db.flush()

    connection = BankConnection(
        user_id=user.id,
        session_id_encrypted=encrypt("eb-session-xyz"),
        aspsp_name="Mock ASPSP",
        aspsp_country="FI",
        valid_until=datetime.now(timezone.utc) + timedelta(days=90),
    )
    db.add(connection)
    await db.flush()

    account = Account(
        user_id=user.id,
        name="Checking",
        type="checking",
        bank_connection_id=connection.id,
        bank_account_uid="uid_1",
    )
    db.add(account)
    await db.flush()
    return user, connection, account


def _txn(
    amount: str,
    indicator: str,
    *,
    entry_reference: str | None = "ref-1",
    booking_date: str = "2026-07-01",
    status: str = "BOOK",
    currency: str = "EUR",
    creditor: str | None = "Coffee Shop",
    debtor: str | None = None,
    remittance: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "entry_reference": entry_reference,
        "transaction_amount": {"amount": amount, "currency": currency},
        "credit_debit_indicator": indicator,
        "status": status,
        "booking_date": booking_date,
        "creditor": {"name": creditor} if creditor else None,
        "debtor": {"name": debtor} if debtor else None,
        "remittance_information": remittance or [],
    }


@pytest.mark.asyncio
async def test_booked_eur_debit_is_imported(db_session):
    _, connection, account = await _seed(db_session)
    client = FakeBankingClient(transactions_by_uid={"uid_1": [_txn("42.50", "DBIT")]})

    summary = await sync_connection(db_session, connection, client)
    await db_session.commit()

    assert summary.added == 1
    rows = (await db_session.execute(Transaction.__table__.select())).fetchall()
    assert len(rows) == 1
    assert rows[0].amount_cents == -4250
    assert rows[0].external_transaction_id == f"{account.id}:ref-1"
    assert rows[0].payee == "Coffee Shop"
    assert connection.last_synced_at is not None
    assert connection.last_error_code is None


@pytest.mark.asyncio
async def test_refetch_is_idempotent(db_session):
    _, connection, _ = await _seed(db_session)
    client = FakeBankingClient(
        transactions_by_uid={
            "uid_1": [
                _txn("42.50", "DBIT", entry_reference="ref-1"),
                _txn("100.00", "CRDT", entry_reference="ref-2", debtor="Employer"),
            ]
        }
    )

    first = await sync_connection(db_session, connection, client)
    second = await sync_connection(db_session, connection, client)

    assert first.added == 2
    assert second.added == 0
    assert second.modified == 0
    rows = (await db_session.execute(Transaction.__table__.select())).fetchall()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_missing_entry_reference_uses_hash_fallback(db_session):
    _, connection, account = await _seed(db_session)
    client = FakeBankingClient(
        transactions_by_uid={"uid_1": [_txn("9.99", "DBIT", entry_reference=None)]}
    )

    first = await sync_connection(db_session, connection, client)
    second = await sync_connection(db_session, connection, client)

    assert first.added == 1
    assert second.added == 0
    row = (await db_session.execute(Transaction.__table__.select())).fetchone()
    assert row.external_transaction_id.startswith(f"{account.id}:h:")


@pytest.mark.asyncio
async def test_update_preserves_user_owned_fields(db_session):
    user, connection, account = await _seed(db_session)
    db_session.add(
        Transaction(
            user_id=user.id,
            account_id=account.id,
            date=date(2026, 7, 1),
            payee="Coffee Shop",
            memo="my notes",
            amount_cents=-500,
            external_transaction_id=f"{account.id}:ref-1",
        )
    )
    await db_session.flush()

    client = FakeBankingClient(
        transactions_by_uid={
            "uid_1": [_txn("7.50", "DBIT", booking_date="2026-07-02", creditor="Renamed")]
        }
    )
    summary = await sync_connection(db_session, connection, client)

    assert summary.modified == 1
    row = (await db_session.execute(Transaction.__table__.select())).fetchone()
    # Bank-owned fields updated...
    assert row.amount_cents == -750
    assert row.date == date(2026, 7, 2)
    # ...user-owned fields preserved.
    assert row.memo == "my notes"
    assert row.payee == "Coffee Shop"


@pytest.mark.asyncio
async def test_pending_transactions_are_skipped(db_session):
    _, connection, _ = await _seed(db_session)
    client = FakeBankingClient(
        transactions_by_uid={
            "uid_1": [
                _txn("10.00", "DBIT", entry_reference="p1", status="PDNG"),
                _txn("20.00", "DBIT", entry_reference="b1"),
            ]
        }
    )
    summary = await sync_connection(db_session, connection, client)

    assert summary.added == 1
    assert summary.skipped_pending == 1


@pytest.mark.asyncio
async def test_non_eur_transactions_are_skipped(db_session):
    _, connection, _ = await _seed(db_session)
    client = FakeBankingClient(
        transactions_by_uid={
            "uid_1": [
                _txn("5.00", "DBIT", entry_reference="usd", currency="USD"),
                _txn("5.00", "DBIT", entry_reference="eur"),
            ]
        }
    )
    summary = await sync_connection(db_session, connection, client)

    assert summary.added == 1
    assert summary.skipped_non_eur == 1


@pytest.mark.asyncio
async def test_expired_consent_records_error_and_raises(db_session):
    _, connection, _ = await _seed(db_session)
    connection.valid_until = datetime.now(timezone.utc) - timedelta(days=1)
    await db_session.flush()

    client = FakeBankingClient()
    with pytest.raises(BankingError):
        await sync_connection(db_session, connection, client)

    assert connection.last_error_code == "SESSION_EXPIRED"
    assert client.calls == []  # no API quota wasted on a dead session


@pytest.mark.asyncio
async def test_client_error_records_error_code(db_session):
    _, connection, _ = await _seed(db_session)
    client = FakeBankingClient(error=BankingError("RATE_LIMITED", "slow down"))

    with pytest.raises(BankingError):
        await sync_connection(db_session, connection, client)

    assert connection.last_error_code == "RATE_LIMITED"
    assert connection.last_synced_at is None


@pytest.mark.asyncio
async def test_first_sync_uses_wider_window(db_session):
    _, connection, _ = await _seed(db_session)
    client = FakeBankingClient()

    await sync_connection(db_session, connection, client)
    first_window_start = client.calls[0][1]
    await sync_connection(db_session, connection, client)
    second_window_start = client.calls[1][1]

    # First sync reaches further back than subsequent ones (90 vs 14 days).
    assert first_window_start < second_window_start


@pytest.mark.asyncio
async def test_global_run_is_partial_when_one_connection_fails(db_session):
    user, connection, _ = await _seed(db_session)
    broken = BankConnection(
        user_id=user.id,
        session_id_encrypted=encrypt("eb-session-dead"),
        aspsp_name="Broken Bank",
        aspsp_country="DE",
        valid_until=datetime.now(timezone.utc) - timedelta(days=1),  # expired
    )
    db_session.add(broken)
    await db_session.flush()

    client = FakeBankingClient(
        transactions_by_uid={"uid_1": [_txn("42.50", "DBIT")]}
    )
    run, summaries = await run_global_sync(db_session, client, SyncRun.TRIGGER_MANUAL)
    await db_session.commit()

    assert run.status == SyncRun.STATUS_PARTIAL
    assert run.added == 1
    assert summaries[connection.id].added == 1
    assert summaries[broken.id].error_code == "SESSION_EXPIRED"


@pytest.mark.asyncio
async def test_global_run_counts_against_quota(db_session):
    from app.config import get_settings

    await _seed(db_session)
    client = FakeBankingClient()

    assert await runs_today(db_session) == 0
    await run_global_sync(db_session, client, SyncRun.TRIGGER_AUTO)
    await run_global_sync(db_session, client, SyncRun.TRIGGER_MANUAL)

    assert await runs_today(db_session) == 2
    settings = get_settings()
    remaining = await quota_remaining(db_session, settings)
    assert remaining == max(settings.sync_max_per_day - 2, 0)
    last = await latest_run(db_session)
    assert last is not None
    assert last.trigger == SyncRun.TRIGGER_MANUAL


@pytest.mark.asyncio
async def test_yesterdays_runs_do_not_count_today(db_session):
    await _seed(db_session)
    db_session.add(
        SyncRun(
            started_at=datetime.now(timezone.utc) - timedelta(days=1),
            trigger=SyncRun.TRIGGER_AUTO,
            status=SyncRun.STATUS_OK,
        )
    )
    await db_session.flush()

    assert await runs_today(db_session) == 0
