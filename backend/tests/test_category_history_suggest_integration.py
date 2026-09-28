"""Payee-history category suggestions, wired into the two places a
transaction is ever created unattended: a first-time bank sync insert, and a
YNAB import row that arrives with no category of its own.

``suggest_categories`` itself (exact/fuzzy matching, recency ranking) is
covered by ``test_category_suggest.py``; these tests only check that it's
actually consulted here, after rules, and that it respects the same
never-overwrite and scope rules a rule match does.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import (
    Account,
    BankConnection,
    Category,
    CategoryGroup,
    Payee,
    PayeeCategoryRule,
    Scope,
    Transaction,
    User,
)
from app.services.bank_sync import sync_connection
from app.services.encryption import encrypt
from tests.conftest import (
    _enable_sqlite_fks,
    create_account,
    create_category,
    create_group,
    register_user,
)


@dataclass
class FakeBankingClient:
    transactions_by_uid: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    async def get_transactions(self, account_uid: str, date_from: date) -> list[dict[str, Any]]:
        return self.transactions_by_uid.get(account_uid, [])

    async def get_balances(self, account_uid: str) -> list[dict[str, Any]]:
        return []


def _txn(amount: str, indicator: str, creditor: str | None = None) -> dict[str, Any]:
    return {
        "entry_reference": "ref-1",
        "transaction_amount": {"amount": amount, "currency": "EUR"},
        "credit_debit_indicator": indicator,
        "status": "BOOK",
        "booking_date": "2026-07-01",
        "creditor": {"name": creditor} if creditor else None,
        "debtor": None,
        "remittance_information": [],
    }


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


async def _seed(db: AsyncSession) -> tuple[User, BankConnection, Account, Category]:
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

    scope = Scope(user_id=user.id, name="Personal", sort_order=0)
    db.add(scope)
    await db.flush()

    account = Account(
        user_id=user.id,
        name="Checking",
        type="checking",
        scope_id=scope.id,
        bank_connection_id=connection.id,
        bank_account_uid="uid_1",
    )
    db.add(account)
    group = CategoryGroup(user_id=user.id, name="Subscriptions", scope_id=scope.id)
    db.add(group)
    await db.flush()
    category = Category(
        user_id=user.id,
        group_id=group.id,
        name="Streaming",
        goal_kind="monthly",
        goal_amount_cents=1000,
    )
    db.add(category)
    await db.flush()
    return user, connection, account, category


async def _add_history(
    db: AsyncSession,
    user: User,
    account: Account,
    category: Category,
    *,
    payee_name: str,
    on: date,
) -> None:
    payee = Payee(user_id=user.id, name=payee_name)
    db.add(payee)
    await db.flush()
    db.add(
        Transaction(
            user_id=user.id,
            account_id=account.id,
            category_id=category.id,
            cleared=True,
            date=on,
            payee_id=payee.id,
            amount_cents=-999,
        )
    )
    await db.flush()


@pytest.mark.asyncio
async def test_bank_sync_suggests_category_from_exact_payee_history(db_session: AsyncSession):
    user, connection, account, category = await _seed(db_session)
    await _add_history(
        db_session, user, account, category, payee_name="Netflix.com", on=date(2026, 6, 1)
    )

    client = FakeBankingClient(
        transactions_by_uid={"uid_1": [_txn("9.99", "DBIT", creditor="Netflix.com")]}
    )
    await sync_connection(db_session, connection, client)
    await db_session.commit()

    rows = (await db_session.execute(select(Transaction).order_by(Transaction.id))).scalars().all()
    [new_row] = [r for r in rows if r.date == date(2026, 7, 1)]
    assert new_row.category_id == category.id
    assert new_row.cleared is False


@pytest.mark.asyncio
async def test_bank_sync_suggests_category_from_fuzzy_payee_history(db_session: AsyncSession):
    user, connection, account, category = await _seed(db_session)
    await _add_history(
        db_session, user, account, category, payee_name="Netflix.com", on=date(2026, 6, 1)
    )

    client = FakeBankingClient(
        transactions_by_uid={"uid_1": [_txn("9.99", "DBIT", creditor="Visa: Netflix.com")]}
    )
    await sync_connection(db_session, connection, client)
    await db_session.commit()

    rows = (await db_session.execute(select(Transaction).order_by(Transaction.id))).scalars().all()
    [new_row] = [r for r in rows if r.date == date(2026, 7, 1)]
    assert new_row.category_id == category.id


@pytest.mark.asyncio
async def test_bank_sync_rule_takes_priority_over_history_suggestion(db_session: AsyncSession):
    user, connection, account, category = await _seed(db_session)
    await _add_history(
        db_session, user, account, category, payee_name="Netflix.com", on=date(2026, 6, 1)
    )
    group = CategoryGroup(user_id=user.id, name="Entertainment", scope_id=account.scope_id)
    db_session.add(group)
    await db_session.flush()
    rule_category = Category(
        user_id=user.id,
        group_id=group.id,
        name="Fun Money",
        goal_kind="monthly",
        goal_amount_cents=1000,
    )
    db_session.add(rule_category)
    await db_session.flush()
    db_session.add(
        PayeeCategoryRule(user_id=user.id, category_id=rule_category.id, contains_text="netflix")
    )
    await db_session.flush()

    client = FakeBankingClient(
        transactions_by_uid={"uid_1": [_txn("9.99", "DBIT", creditor="Netflix.com")]}
    )
    await sync_connection(db_session, connection, client)
    await db_session.commit()

    rows = (await db_session.execute(select(Transaction).order_by(Transaction.id))).scalars().all()
    [new_row] = [r for r in rows if r.date == date(2026, 7, 1)]
    assert new_row.category_id == rule_category.id


@pytest.mark.asyncio
async def test_bank_sync_never_overwrites_a_category_with_a_history_suggestion(
    db_session: AsyncSession,
):
    user, connection, account, category = await _seed(db_session)
    await _add_history(
        db_session, user, account, category, payee_name="Netflix.com", on=date(2026, 6, 1)
    )

    client = FakeBankingClient(
        transactions_by_uid={"uid_1": [_txn("9.99", "DBIT", creditor="Netflix.com")]}
    )
    await sync_connection(db_session, connection, client)
    await db_session.commit()

    [row] = [
        r
        for r in (await db_session.execute(select(Transaction))).scalars().all()
        if r.date == date(2026, 7, 1)
    ]
    row.category_id = None  # simulate the user deliberately clearing it
    await db_session.commit()

    # Amount changes so the second sync treats the row as "modified", not a
    # fresh insert — the suggestion must not re-fire on an update.
    client2 = FakeBankingClient(
        transactions_by_uid={"uid_1": [_txn("12.34", "DBIT", creditor="Netflix.com")]}
    )
    summary = await sync_connection(db_session, connection, client2)
    await db_session.commit()

    assert summary.modified == 1
    [row] = [
        r
        for r in (await db_session.execute(select(Transaction))).scalars().all()
        if r.date == date(2026, 7, 1)
    ]
    assert row.category_id is None


@pytest.mark.asyncio
async def test_bank_sync_ignores_history_from_a_different_scope(db_session: AsyncSession):
    user, connection, _account, _category = await _seed(db_session)
    other_scope = Scope(user_id=user.id, name="Family", sort_order=1)
    db_session.add(other_scope)
    await db_session.flush()
    other_group = CategoryGroup(user_id=user.id, name="Bills", scope_id=other_scope.id)
    db_session.add(other_group)
    await db_session.flush()
    other_category = Category(
        user_id=user.id,
        group_id=other_group.id,
        name="Rent",
        goal_kind="monthly",
        goal_amount_cents=1000,
    )
    db_session.add(other_category)
    await db_session.flush()
    other_account = Account(
        user_id=user.id,
        name="Family Checking",
        type="checking",
        scope_id=other_scope.id,
    )
    db_session.add(other_account)
    await db_session.flush()
    await _add_history(
        db_session,
        user,
        other_account,
        other_category,
        payee_name="Netflix.com",
        on=date(2026, 6, 1),
    )

    client = FakeBankingClient(
        transactions_by_uid={"uid_1": [_txn("9.99", "DBIT", creditor="Netflix.com")]}
    )
    await sync_connection(db_session, connection, client)
    await db_session.commit()

    [row] = [
        r
        for r in (await db_session.execute(select(Transaction))).scalars().all()
        if r.date == date(2026, 7, 1)
    ]
    assert row.category_id is None


@pytest.mark.asyncio
async def test_import_ynab_suggests_category_from_payee_history(client: AsyncClient):
    headers = await register_user(client)
    account = await create_account(client, headers)
    group = await create_group(client, headers)
    streaming = await create_category(client, headers, group, "Streaming")

    r = await client.post(
        "/api/transactions/import-ynab",
        json={
            "rows": [
                {
                    "account_id": account,
                    "date": "2026-06-01",
                    "payee": "Netflix",
                    "category_id": streaming,
                    "amount_cents": -999,
                },
            ]
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text

    r = await client.post(
        "/api/transactions/import-ynab",
        json={
            "rows": [
                {
                    "account_id": account,
                    "date": "2026-07-01",
                    "payee": "Netflix",
                    "amount_cents": -999,
                },
            ]
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text

    r = await client.get("/api/transactions", headers=headers)
    rows = {row["date"]: row for row in r.json()["items"]}
    assert rows["2026-07-01"]["category_id"] == streaming
    assert rows["2026-07-01"]["cleared"] is False


@pytest.mark.asyncio
async def test_import_ynab_history_suggestion_never_overrides_the_row_or_rule_category(
    client: AsyncClient,
):
    headers = await register_user(client)
    account = await create_account(client, headers)
    group = await create_group(client, headers)
    streaming = await create_category(client, headers, group, "Streaming")
    groceries = await create_category(client, headers, group, "Groceries")
    entertainment = await create_category(client, headers, group, "Entertainment")

    r = await client.post(
        "/api/transactions/import-ynab",
        json={
            "rows": [
                {
                    "account_id": account,
                    "date": "2026-06-01",
                    "payee": "Netflix",
                    "category_id": streaming,
                    "amount_cents": -999,
                },
            ]
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text

    await client.post(
        "/api/payee-rules",
        json={"category_id": entertainment, "contains_text": "netflix"},
        headers=headers,
    )

    r = await client.post(
        "/api/transactions/import-ynab",
        json={
            "rows": [
                {
                    "account_id": account,
                    "date": "2026-07-01",
                    "payee": "Netflix",
                    "amount_cents": -999,
                },
                {
                    "account_id": account,
                    "date": "2026-07-02",
                    "payee": "Netflix",
                    "category_id": groceries,
                    "amount_cents": -500,
                },
            ]
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text

    r = await client.get("/api/transactions", headers=headers)
    rows = {row["date"]: row["category_id"] for row in r.json()["items"]}
    assert rows["2026-07-01"] == entertainment  # rule wins over history suggestion
    assert rows["2026-07-02"] == groceries  # row's own category wins over everything
