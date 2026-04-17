"""Unit tests for ``app.services.plaid_sync.sync_item``.

We stand up a real in-memory SQLite session (same as the API tests) but swap
the Plaid client for a fake that hands back canned responses. This exercises
the full DB code path — inserts, dedup lookups, cursor persistence — without
touching the network.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Account, PlaidItem, Transaction, User
from app.services.encryption import encrypt
from app.services.plaid_client import PlaidError, SyncResult
from app.services.plaid_sync import sync_item
from tests.conftest import _enable_sqlite_fks


@dataclass
class FakePlaidClient:
    result: SyncResult | None = None
    error: PlaidError | None = None
    calls: list[tuple[str, str | None]] = None

    def __post_init__(self) -> None:
        if self.calls is None:
            self.calls = []

    async def sync_transactions(self, access_token: str, cursor: str | None) -> SyncResult:
        self.calls.append((access_token, cursor))
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


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


async def _seed(db: AsyncSession) -> tuple[User, PlaidItem, Account]:
    user = User(email="alice@example.com", hashed_password="x")
    db.add(user)
    await db.flush()

    item = PlaidItem(
        user_id=user.id,
        plaid_item_id="item_123",
        access_token_encrypted=encrypt("access-sandbox-xyz"),
    )
    db.add(item)
    await db.flush()

    account = Account(
        user_id=user.id,
        name="Checking",
        type="checking",
        plaid_item_id=item.id,
        plaid_account_id="plaid_acc_1",
    )
    db.add(account)
    await db.flush()
    return user, item, account


def _posted(
    transaction_id: str,
    account_id: str,
    amount: float,
    *,
    name: str = "Coffee",
    iso: str | None = "EUR",
    pending: bool = False,
) -> dict[str, Any]:
    return {
        "transaction_id": transaction_id,
        "account_id": account_id,
        "amount": amount,
        "name": name,
        "merchant_name": name,
        "date": "2026-04-01",
        "iso_currency_code": iso,
        "unofficial_currency_code": None,
        "pending": pending,
    }


@pytest.mark.asyncio
async def test_added_posted_eur_is_imported_with_sign_flipped(db_session):
    _, item, account = await _seed(db_session)
    client = FakePlaidClient(
        result=SyncResult(
            added=[_posted("txn_1", "plaid_acc_1", 42.50)],
            modified=[],
            removed=[],
            next_cursor="cursor_v1",
        )
    )
    summary = await sync_item(db_session, item, client)
    await db_session.commit()

    assert summary.added == 1
    rows = (await db_session.execute(Transaction.__table__.select())).fetchall()
    assert len(rows) == 1
    # 42.50 EUR spend in Plaid (positive) must land negative in ZeroBudget.
    assert rows[0].amount_cents == -4250
    assert rows[0].plaid_transaction_id == "txn_1"
    assert item.transactions_cursor == "cursor_v1"
    assert item.last_synced_at is not None


@pytest.mark.asyncio
async def test_pending_transactions_are_skipped(db_session):
    _, item, _ = await _seed(db_session)
    client = FakePlaidClient(
        result=SyncResult(
            added=[
                _posted("txn_pending", "plaid_acc_1", 10.00, pending=True),
                _posted("txn_posted", "plaid_acc_1", 20.00),
            ],
            modified=[],
            removed=[],
            next_cursor="c",
        )
    )
    summary = await sync_item(db_session, item, client)

    assert summary.added == 1
    assert summary.skipped_pending == 1


@pytest.mark.asyncio
async def test_non_eur_added_is_skipped(db_session):
    _, item, _ = await _seed(db_session)
    client = FakePlaidClient(
        result=SyncResult(
            added=[
                _posted("txn_usd", "plaid_acc_1", 5.00, iso="USD"),
                _posted("txn_eur", "plaid_acc_1", 5.00, iso="EUR"),
            ],
            modified=[],
            removed=[],
            next_cursor="c",
        )
    )
    summary = await sync_item(db_session, item, client)

    assert summary.added == 1
    assert summary.skipped_non_eur == 1


@pytest.mark.asyncio
async def test_added_dedups_on_plaid_transaction_id(db_session):
    user, item, account = await _seed(db_session)
    # Pre-seed a transaction with the same plaid id as what Plaid will return.
    db_session.add(
        Transaction(
            user_id=user.id,
            account_id=account.id,
            date=date(2026, 4, 1),
            payee="existing",
            amount_cents=-1234,
            plaid_transaction_id="txn_dup",
        )
    )
    await db_session.flush()

    client = FakePlaidClient(
        result=SyncResult(
            added=[_posted("txn_dup", "plaid_acc_1", 99.99)],
            modified=[],
            removed=[],
            next_cursor="c",
        )
    )
    summary = await sync_item(db_session, item, client)

    assert summary.added == 0
    rows = (await db_session.execute(Transaction.__table__.select())).fetchall()
    assert len(rows) == 1
    # Original row preserved untouched (amount not overwritten).
    assert rows[0].amount_cents == -1234


@pytest.mark.asyncio
async def test_modified_preserves_user_owned_fields(db_session):
    user, item, account = await _seed(db_session)
    # Simulate an existing row the user has already categorized and annotated.
    db_session.add(
        Transaction(
            user_id=user.id,
            account_id=account.id,
            date=date(2026, 4, 1),
            payee="Coffee",
            memo="my notes",
            amount_cents=-500,
            category_id=None,
            plaid_transaction_id="txn_mod",
        )
    )
    await db_session.flush()

    client = FakePlaidClient(
        result=SyncResult(
            added=[],
            modified=[
                {
                    "transaction_id": "txn_mod",
                    "account_id": "plaid_acc_1",
                    "amount": 7.50,  # bumped from 5.00
                    "name": "Coffee Shop (Renamed)",
                    "merchant_name": "Coffee Shop (Renamed)",
                    "date": "2026-04-02",  # shifted by one day
                    "iso_currency_code": "EUR",
                    "unofficial_currency_code": None,
                    "pending": False,
                }
            ],
            removed=[],
            next_cursor="c",
        )
    )
    summary = await sync_item(db_session, item, client)

    assert summary.modified == 1
    row = (
        await db_session.execute(Transaction.__table__.select())
    ).fetchone()
    # Plaid-owned fields updated...
    assert row.amount_cents == -750
    assert row.date == date(2026, 4, 2)
    # ...user-owned fields preserved.
    assert row.memo == "my notes"
    assert row.payee == "Coffee"


@pytest.mark.asyncio
async def test_removed_deletes_transaction(db_session):
    user, item, account = await _seed(db_session)
    db_session.add(
        Transaction(
            user_id=user.id,
            account_id=account.id,
            date=date(2026, 4, 1),
            payee="x",
            amount_cents=-100,
            plaid_transaction_id="txn_rm",
        )
    )
    await db_session.flush()

    client = FakePlaidClient(
        result=SyncResult(
            added=[],
            modified=[],
            removed=[{"transaction_id": "txn_rm", "account_id": "plaid_acc_1"}],
            next_cursor="c",
        )
    )
    summary = await sync_item(db_session, item, client)

    assert summary.removed == 1
    rows = (await db_session.execute(Transaction.__table__.select())).fetchall()
    assert rows == []


@pytest.mark.asyncio
async def test_cursor_only_persists_on_success(db_session):
    _, item, _ = await _seed(db_session)
    item.transactions_cursor = "before"
    await db_session.flush()

    client = FakePlaidClient(error=PlaidError("ITEM_LOGIN_REQUIRED", "re-auth needed"))

    with pytest.raises(PlaidError):
        await sync_item(db_session, item, client)

    # Cursor unchanged; error code surfaced on item.
    assert item.transactions_cursor == "before"
    assert item.last_error_code == "ITEM_LOGIN_REQUIRED"


@pytest.mark.asyncio
async def test_unknown_account_increments_skip(db_session):
    _, item, _ = await _seed(db_session)
    client = FakePlaidClient(
        result=SyncResult(
            added=[_posted("txn_1", "unknown_acc", 10.00)],
            modified=[],
            removed=[],
            next_cursor="c",
        )
    )
    summary = await sync_item(db_session, item, client)
    assert summary.skipped_unknown_account == 1
    assert summary.added == 0
