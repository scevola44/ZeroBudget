"""Payee-contains-category auto-categorization rules.

Pure matcher tests first, then integration tests against the two places a
rule is ever applied: a first-time bank sync insert, and a YNAB import row
that arrives with no category of its own.
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
    PayeeCategoryRule,
    Scope,
    Transaction,
    User,
)
from app.services.bank_sync import sync_connection
from app.services.encryption import encrypt
from app.services.payee_rules import CategoryRule, match_rule
from tests.conftest import (
    _enable_sqlite_fks,
    create_account,
    create_category,
    create_group,
    register_user,
)


def _rule(category_id: int, contains_text: str, rule_id: int = 1) -> CategoryRule:
    return CategoryRule(id=rule_id, category_id=category_id, contains_text=contains_text)


def test_rule_matches_substring_case_insensitively():
    assert match_rule("VISA Netflix.com", [_rule(7, "netflix")]) == 7


def test_no_match_returns_none():
    assert match_rule("Coffee Shop", [_rule(7, "netflix")]) is None


def test_blank_payee_never_matches():
    assert match_rule("   ", [_rule(7, "")]) is None


def test_first_matching_rule_in_given_order_wins():
    rules = [_rule(1, "shop", rule_id=1), _rule(2, "coffee shop", rule_id=2)]
    assert match_rule("Coffee Shop Downtown", rules) == 1


# ---------------------------------------------------------------------------
# Bank sync integration
# ---------------------------------------------------------------------------


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


async def _seed_with_category(db: AsyncSession) -> tuple[User, BankConnection, Account, Category]:
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


@pytest.mark.asyncio
async def test_bank_sync_applies_matching_rule_to_new_uncategorized_transaction(
    db_session: AsyncSession,
):
    user, connection, account, category = await _seed_with_category(db_session)
    db_session.add(
        PayeeCategoryRule(user_id=user.id, category_id=category.id, contains_text="netflix")
    )
    await db_session.flush()

    client = FakeBankingClient(
        transactions_by_uid={"uid_1": [_txn("9.99", "DBIT", creditor="Netflix.com")]}
    )
    await sync_connection(db_session, connection, client)
    await db_session.commit()

    [row] = (await db_session.execute(select(Transaction))).scalars().all()
    assert row.category_id == category.id


@pytest.mark.asyncio
async def test_bank_sync_leaves_non_matching_transaction_uncategorized(
    db_session: AsyncSession,
):
    user, connection, account, category = await _seed_with_category(db_session)
    db_session.add(
        PayeeCategoryRule(user_id=user.id, category_id=category.id, contains_text="netflix")
    )
    await db_session.flush()

    client = FakeBankingClient(
        transactions_by_uid={"uid_1": [_txn("9.99", "DBIT", creditor="Coffee Shop")]}
    )
    await sync_connection(db_session, connection, client)
    await db_session.commit()

    [row] = (await db_session.execute(select(Transaction))).scalars().all()
    assert row.category_id is None


@pytest.mark.asyncio
async def test_bank_sync_never_overwrites_a_category_on_resync(db_session: AsyncSession):
    user, connection, account, category = await _seed_with_category(db_session)
    db_session.add(
        PayeeCategoryRule(user_id=user.id, category_id=category.id, contains_text="netflix")
    )
    await db_session.flush()

    client = FakeBankingClient(
        transactions_by_uid={"uid_1": [_txn("9.99", "DBIT", creditor="Netflix.com")]}
    )
    await sync_connection(db_session, connection, client)
    await db_session.commit()

    [row] = (await db_session.execute(select(Transaction))).scalars().all()
    row.category_id = None  # simulate the user deliberately clearing it
    await db_session.commit()

    # Amount changes so the second sync treats the row as "modified", not a
    # fresh insert — the rule must not re-fire on an update.
    client2 = FakeBankingClient(
        transactions_by_uid={"uid_1": [_txn("12.34", "DBIT", creditor="Netflix.com")]}
    )
    summary = await sync_connection(db_session, connection, client2)
    await db_session.commit()

    assert summary.modified == 1
    [row] = (await db_session.execute(select(Transaction))).scalars().all()
    assert row.category_id is None


@pytest.mark.asyncio
async def test_rule_matching_an_out_of_scope_category_is_skipped_not_errored(
    db_session: AsyncSession,
):
    user, connection, account, category = await _seed_with_category(db_session)
    # A second scope, with the category living there instead of the synced
    # account's scope — the rule can never legally apply to this account.
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
    db_session.add(
        PayeeCategoryRule(
            user_id=user.id, category_id=other_category.id, contains_text="netflix"
        )
    )
    await db_session.flush()

    client = FakeBankingClient(
        transactions_by_uid={"uid_1": [_txn("9.99", "DBIT", creditor="Netflix.com")]}
    )
    summary = await sync_connection(db_session, connection, client)
    await db_session.commit()

    assert summary.added == 1
    [row] = (await db_session.execute(select(Transaction))).scalars().all()
    assert row.category_id is None


# ---------------------------------------------------------------------------
# YNAB import integration + CRUD, via the HTTP API
# ---------------------------------------------------------------------------


async def _create_rule(
    client: AsyncClient, headers: dict, *, category_id: int, contains_text: str, sort_order: int = 0
) -> dict:
    r = await client.post(
        "/api/payee-rules",
        json={"category_id": category_id, "contains_text": contains_text, "sort_order": sort_order},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_import_ynab_applies_rule_only_when_row_has_no_category(client: AsyncClient):
    headers = await register_user(client)
    account = await create_account(client, headers)
    group = await create_group(client, headers)
    streaming = await create_category(client, headers, group, "Streaming")
    groceries = await create_category(client, headers, group, "Groceries")
    await _create_rule(client, headers, category_id=streaming, contains_text="netflix")

    r = await client.post(
        "/api/transactions/import-ynab",
        json={
            "rows": [
                {
                    "account_id": account,
                    "date": "2026-04-01",
                    "payee": "Netflix",
                    "amount_cents": -999,
                },
                {
                    "account_id": account,
                    "date": "2026-04-02",
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
    rows = {row["amount_cents"]: row["category_id"] for row in r.json()["items"]}
    assert rows[-999] == streaming  # no category on the row -> rule applied
    assert rows[-500] == groceries  # row already had a category -> rule skipped


@pytest.mark.asyncio
async def test_payee_rule_crud(client: AsyncClient):
    headers = await register_user(client)
    group = await create_group(client, headers)
    category = await create_category(client, headers, group)

    created = await _create_rule(client, headers, category_id=category, contains_text="rent")
    r = await client.get("/api/payee-rules", headers=headers)
    assert [rule["id"] for rule in r.json()] == [created["id"]]

    r = await client.patch(
        f"/api/payee-rules/{created['id']}", json={"contains_text": "landlord"}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["contains_text"] == "landlord"

    r = await client.delete(f"/api/payee-rules/{created['id']}", headers=headers)
    assert r.status_code == 204
    r = await client.get("/api/payee-rules", headers=headers)
    assert r.json() == []


@pytest.mark.asyncio
async def test_create_payee_rule_rejects_unowned_category(client: AsyncClient):
    headers = await register_user(client)
    r = await client.post(
        "/api/payee-rules",
        json={"category_id": 999_999, "contains_text": "rent"},
        headers=headers,
    )
    assert r.status_code == 400
