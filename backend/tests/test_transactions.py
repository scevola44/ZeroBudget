"""Transactions router: CRUD, filters, ownership, category clearing."""

from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Account, DeletedExternalTransaction, Transaction, User
from app.routers.transactions import _delete_transactions_cascading, delete_transaction
from tests.conftest import (
    FAMILY,
    PERSONAL,
    _enable_sqlite_fks,
    add_scope,
    create_account,
    create_category,
    create_group,
    list_transactions,
    register_user,
)


async def _add_txn(
    client: AsyncClient,
    headers: dict,
    *,
    account_id: int,
    date: str,
    amount: int,
    category_id: int | None = None,
    payee: str = "",
    is_ready_to_assign: bool = False,
) -> int:
    r = await client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "is_ready_to_assign": is_ready_to_assign,
            "date": date,
            "payee": payee,
            "memo": "",
            "amount_cents": amount,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_list_empty(client: AsyncClient):
    headers = await register_user(client)
    assert await list_transactions(client, headers) == []


@pytest.mark.asyncio
async def test_filter_by_account(client: AsyncClient):
    headers = await register_user(client)
    a1 = await create_account(client, headers, "A1")
    a2 = await create_account(client, headers, "A2")

    await _add_txn(client, headers, account_id=a1, date="2026-04-01", amount=1000)
    await _add_txn(client, headers, account_id=a1, date="2026-04-02", amount=2000)
    await _add_txn(client, headers, account_id=a2, date="2026-04-03", amount=3000)

    rows = await list_transactions(client, headers, account_id=a1)
    amounts = sorted(t["amount_cents"] for t in rows)
    assert amounts == [1000, 2000]


@pytest.mark.asyncio
async def test_filter_by_month(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)

    await _add_txn(client, headers, account_id=a, date="2026-03-31", amount=100)
    await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=200)
    await _add_txn(client, headers, account_id=a, date="2026-04-15", amount=300)
    await _add_txn(client, headers, account_id=a, date="2026-04-30", amount=400)
    await _add_txn(client, headers, account_id=a, date="2026-05-01", amount=500)

    rows = await list_transactions(client, headers, month="2026-04")
    amounts = sorted(t["amount_cents"] for t in rows)
    assert amounts == [200, 300, 400]


@pytest.mark.asyncio
async def test_unassigned_count(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers, "A1")
    b = await create_account(client, headers, "A2")
    group = await create_group(client, headers)
    category = await create_category(client, headers, group)

    # Genuinely unassigned: the only one that should count.
    await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=-100)
    # Categorized.
    await _add_txn(
        client, headers, account_id=a, date="2026-04-02", amount=-200, category_id=category
    )
    # Deliberately uncategorized.
    await _add_txn(
        client, headers, account_id=a, date="2026-04-03", amount=500, is_ready_to_assign=True
    )
    # A transfer pair: uncategorized on both legs, but never "needs a category".
    outflow = await _add_txn(client, headers, account_id=a, date="2026-04-04", amount=-300)
    inflow = await _add_txn(client, headers, account_id=b, date="2026-04-04", amount=300)
    link = await client.post(
        f"/api/transactions/{outflow}/transfer-link",
        json={"peer_transaction_id": inflow},
        headers=headers,
    )
    assert link.status_code == 200, link.text

    r = await client.get("/api/transactions/unassigned-count", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"count": 1}


@pytest.mark.asyncio
async def test_unassigned_count_ignores_other_months_and_users(client: AsyncClient):
    headers = await register_user(client, email="a@example.com")
    other_headers = await register_user(client, email="b@example.com")
    a = await create_account(client, headers)
    other_account = await create_account(client, other_headers)

    # Old, outside any "current month" — still counted, since this is all-time.
    await _add_txn(client, headers, account_id=a, date="2020-01-01", amount=-100)
    # Belongs to a different user entirely.
    await _add_txn(client, other_headers, account_id=other_account, date="2026-04-01", amount=-100)

    r = await client.get("/api/transactions/unassigned-count", headers=headers)
    assert r.status_code == 200
    assert r.json() == {"count": 1}


@pytest.mark.asyncio
async def test_create_with_invalid_account_is_rejected(client: AsyncClient):
    headers = await register_user(client)
    r = await client.post(
        "/api/transactions",
        json={
            "account_id": 9999,
            "category_id": None,
            "date": "2026-04-01",
            "payee": "",
            "memo": "",
            "amount_cents": 1000,
        },
        headers=headers,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_create_with_invalid_category_is_rejected(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    r = await client.post(
        "/api/transactions",
        json={
            "account_id": a,
            "category_id": 9999,
            "date": "2026-04-01",
            "payee": "",
            "memo": "",
            "amount_cents": 1000,
        },
        headers=headers,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_cannot_assign_to_other_users_category(client: AsyncClient):
    alice = await register_user(client, "alice@example.com")
    bob = await register_user(client, "bob@example.com")
    alice_group = await create_group(client, alice)
    alice_cat = await create_category(client, alice, alice_group)

    bob_account = await create_account(client, bob)
    r = await client.post(
        "/api/transactions",
        json={
            "account_id": bob_account,
            "category_id": alice_cat,
            "date": "2026-04-01",
            "payee": "",
            "memo": "",
            "amount_cents": -1000,
        },
        headers=bob,
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_update_transaction_fields(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    txn_id = await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=1000, payee="old")

    r = await client.patch(
        f"/api/transactions/{txn_id}",
        json={"payee": "new", "amount_cents": 2000, "memo": "updated"},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["payee"] == "new"
    assert body["amount_cents"] == 2000
    assert body["memo"] == "updated"


@pytest.mark.asyncio
async def test_update_can_clear_category(client: AsyncClient):
    """PATCH with an explicit category_id=null must unset the category.

    This is the knob that turns a previously-categorized transaction back into
    unassigned inflow — and it relies on ``model_fields_set`` detection, which
    is easy to get wrong.
    """
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    cat = await create_category(client, headers, g)
    txn_id = await _add_txn(
        client, headers, account_id=a, date="2026-04-01", amount=5000, category_id=cat
    )

    r = await client.patch(
        f"/api/transactions/{txn_id}",
        json={"category_id": None},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["category_id"] is None


@pytest.mark.asyncio
async def test_delete_transaction(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    txn_id = await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=1000)

    r = await client.delete(f"/api/transactions/{txn_id}", headers=headers)
    assert r.status_code == 204
    assert await list_transactions(client, headers) == []


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


@pytest.mark.asyncio
async def test_delete_tombstones_bank_imported_transaction(db_session: AsyncSession):
    """Deleting a bank-imported row must leave its external_transaction_id
    tombstoned, or the next sync would re-import it right back (see
    app.services.bank_sync)."""
    user = User(email="user@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    scope = await add_scope(db_session, user.id)
    account = Account(
        user_id=user.id, name="Checking", type="checking", scope_id=scope.id
    )
    db_session.add(account)
    await db_session.flush()
    external_id = f"{account.id}:ref-1"
    txn = Transaction(
        user_id=user.id,
        account_id=account.id,
        date=date(2026, 4, 1),
        amount_cents=-1000,
        external_transaction_id=external_id,
    )
    db_session.add(txn)
    await db_session.flush()

    await delete_transaction(txn.id, db_session, user)

    assert (await db_session.get(Transaction, txn.id)) is None
    tombstone = (
        await db_session.execute(
            select(DeletedExternalTransaction).where(
                DeletedExternalTransaction.external_transaction_id == external_id
            )
        )
    ).scalar_one()
    assert tombstone.user_id == user.id


@pytest.mark.asyncio
async def test_delete_does_not_tombstone_manually_entered_transaction(
    db_session: AsyncSession,
):
    """No external_transaction_id means nothing for a sync to re-import, so a
    manually entered transaction's deletion shouldn't leave a tombstone."""
    user = User(email="user@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    scope = await add_scope(db_session, user.id)
    account = Account(
        user_id=user.id, name="Checking", type="checking", scope_id=scope.id
    )
    db_session.add(account)
    await db_session.flush()
    txn = Transaction(
        user_id=user.id, account_id=account.id, date=date(2026, 4, 1), amount_cents=-1000
    )
    db_session.add(txn)
    await db_session.flush()

    await delete_transaction(txn.id, db_session, user)

    tombstones = (
        await db_session.execute(select(DeletedExternalTransaction))
    ).scalars().all()
    assert tombstones == []


@pytest.mark.asyncio
async def test_bulk_delete_removes_selected_transactions(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    t1 = await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=-100)
    t2 = await _add_txn(client, headers, account_id=a, date="2026-04-02", amount=-200)
    keep = await _add_txn(client, headers, account_id=a, date="2026-04-03", amount=-300)

    r = await client.post(
        "/api/transactions/bulk-delete", json={"ids": [t1, t2]}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"deleted": 2}

    remaining = await list_transactions(client, headers)
    assert [t["id"] for t in remaining] == [keep]


@pytest.mark.asyncio
async def test_bulk_delete_cascades_to_transfer_peer(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers, "A1")
    b = await create_account(client, headers, "A2")
    outflow = await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=-300)
    inflow = await _add_txn(client, headers, account_id=b, date="2026-04-01", amount=300)
    link = await client.post(
        f"/api/transactions/{outflow}/transfer-link",
        json={"peer_transaction_id": inflow},
        headers=headers,
    )
    assert link.status_code == 200, link.text

    # Only the outflow leg is selected — the inflow peer should still be
    # cascade-deleted, and reflected in the response count.
    r = await client.post(
        "/api/transactions/bulk-delete", json={"ids": [outflow]}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"deleted": 2}
    assert await list_transactions(client, headers) == []


@pytest.mark.asyncio
async def test_bulk_delete_both_transfer_legs_does_not_double_delete(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers, "A1")
    b = await create_account(client, headers, "A2")
    outflow = await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=-300)
    inflow = await _add_txn(client, headers, account_id=b, date="2026-04-01", amount=300)
    link = await client.post(
        f"/api/transactions/{outflow}/transfer-link",
        json={"peer_transaction_id": inflow},
        headers=headers,
    )
    assert link.status_code == 200, link.text

    # Both legs selected explicitly — should still resolve to exactly 2 deletes.
    r = await client.post(
        "/api/transactions/bulk-delete",
        json={"ids": [outflow, inflow]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"deleted": 2}
    assert await list_transactions(client, headers) == []


@pytest.mark.asyncio
async def test_bulk_delete_ignores_other_users_ids(client: AsyncClient):
    alice = await register_user(client, "alice@example.com")
    bob = await register_user(client, "bob@example.com")
    a = await create_account(client, alice)
    b = await create_account(client, bob)
    alice_txn = await _add_txn(client, alice, account_id=a, date="2026-04-01", amount=-100)
    bob_txn = await _add_txn(client, bob, account_id=b, date="2026-04-01", amount=-100)

    r = await client.post(
        "/api/transactions/bulk-delete",
        json={"ids": [alice_txn, bob_txn]},
        headers=alice,
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"deleted": 1}
    assert await list_transactions(client, alice) == []
    remaining_bob = await list_transactions(client, bob)
    assert [t["id"] for t in remaining_bob] == [bob_txn]


@pytest.mark.asyncio
async def test_bulk_delete_rejects_empty_ids(client: AsyncClient):
    headers = await register_user(client)
    r = await client.post("/api/transactions/bulk-delete", json={"ids": []}, headers=headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_bulk_delete_tombstones_bank_imported_transactions(db_session: AsyncSession):
    """Bulk delete must tombstone bank-imported legs the same way single
    delete does, so a later sync doesn't re-import them."""
    user = User(email="user@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    scope = await add_scope(db_session, user.id)
    account = Account(
        user_id=user.id, name="Checking", type="checking", scope_id=scope.id
    )
    db_session.add(account)
    await db_session.flush()
    external_id = f"{account.id}:ref-1"
    txn = Transaction(
        user_id=user.id,
        account_id=account.id,
        date=date(2026, 4, 1),
        amount_cents=-1000,
        external_transaction_id=external_id,
    )
    db_session.add(txn)
    await db_session.flush()

    legs = await _delete_transactions_cascading(db_session, user.id, [txn])
    await db_session.commit()

    assert len(legs) == 1
    tombstone = (
        await db_session.execute(
            select(DeletedExternalTransaction).where(
                DeletedExternalTransaction.external_transaction_id == external_id
            )
        )
    ).scalar_one()
    assert tombstone.user_id == user.id


@pytest.mark.asyncio
async def test_cannot_update_or_delete_other_users_transaction(client: AsyncClient):
    alice = await register_user(client, "alice@example.com")
    bob = await register_user(client, "bob@example.com")
    a = await create_account(client, alice)
    txn_id = await _add_txn(client, alice, account_id=a, date="2026-04-01", amount=1000)

    r = await client.patch(
        f"/api/transactions/{txn_id}", json={"payee": "hijack"}, headers=bob
    )
    assert r.status_code == 404
    r = await client.delete(f"/api/transactions/{txn_id}", headers=bob)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_category_suggestions_span_all_of_the_users_accounts(client: AsyncClient):
    headers = await register_user(client)
    a1 = await create_account(client, headers, "Checking")
    a2 = await create_account(client, headers, "Savings")
    g = await create_group(client, headers)
    groceries = await create_category(client, headers, g, "Groceries")

    await _add_txn(
        client, headers, account_id=a1, date="2026-04-01", amount=-1000,
        category_id=groceries, payee="Store From Home",
    )

    r = await client.get(
        "/api/transactions/category-suggestions",
        params={"account_id": a2, "payee": "Store From Home"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json() == [groceries]


@pytest.mark.asyncio
async def test_category_suggestions_exclude_mismatched_scope_categories(client: AsyncClient):
    headers = await register_user(client)
    personal_account = await create_account(client, headers, "Checking", scope=PERSONAL)
    shared_account = await create_account(client, headers, "Joint", scope=FAMILY)
    personal_group = await create_group(client, headers, "Bills", scope=PERSONAL)
    personal_category = await create_category(client, headers, personal_group, "Rent")

    await _add_txn(
        client, headers, account_id=personal_account, date="2026-04-01", amount=-1000,
        category_id=personal_category, payee="Store From Home",
    )

    r = await client.get(
        "/api/transactions/category-suggestions",
        params={"account_id": shared_account, "payee": "Store From Home"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_create_ready_to_assign_transaction(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    txn_id = await _add_txn(
        client, headers, account_id=a, date="2026-04-01", amount=50000,
        is_ready_to_assign=True,
    )
    rows = await list_transactions(client, headers)
    txn = next(t for t in rows if t["id"] == txn_id)
    assert txn["category_id"] is None
    assert txn["is_ready_to_assign"] is True


@pytest.mark.asyncio
async def test_create_rejects_category_and_ready_to_assign_together(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    cat = await create_category(client, headers, g)

    r = await client.post(
        "/api/transactions",
        json={
            "account_id": a,
            "category_id": cat,
            "is_ready_to_assign": True,
            "date": "2026-04-01",
            "payee": "",
            "memo": "",
            "amount_cents": 1000,
        },
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_update_can_set_ready_to_assign(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    txn_id = await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=50000)

    r = await client.patch(
        f"/api/transactions/{txn_id}",
        json={"is_ready_to_assign": True},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["is_ready_to_assign"] is True


@pytest.mark.asyncio
async def test_update_can_clear_ready_to_assign(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    txn_id = await _add_txn(
        client, headers, account_id=a, date="2026-04-01", amount=50000,
        is_ready_to_assign=True,
    )

    r = await client.patch(
        f"/api/transactions/{txn_id}",
        json={"is_ready_to_assign": False},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["is_ready_to_assign"] is False


@pytest.mark.asyncio
async def test_update_rejects_category_and_ready_to_assign_in_same_payload(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    cat = await create_category(client, headers, g)
    txn_id = await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=50000)

    r = await client.patch(
        f"/api/transactions/{txn_id}",
        json={"category_id": cat, "is_ready_to_assign": True},
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_update_rejects_ready_to_assign_when_category_already_set(client: AsyncClient):
    """A single-field PATCH must still be checked against the row's existing
    state, not just against the rest of its own payload."""
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    cat = await create_category(client, headers, g)
    txn_id = await _add_txn(
        client, headers, account_id=a, date="2026-04-01", amount=50000, category_id=cat,
    )

    r = await client.patch(
        f"/api/transactions/{txn_id}",
        json={"is_ready_to_assign": True},
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_update_rejects_category_when_ready_to_assign_already_set(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    cat = await create_category(client, headers, g)
    txn_id = await _add_txn(
        client, headers, account_id=a, date="2026-04-01", amount=50000,
        is_ready_to_assign=True,
    )

    r = await client.patch(
        f"/api/transactions/{txn_id}",
        json={"category_id": cat},
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_ready_to_assign_rows_excluded_from_category_suggestion_history(client: AsyncClient):
    headers = await register_user(client)
    a1 = await create_account(client, headers, "Checking")
    a2 = await create_account(client, headers, "Savings")

    await _add_txn(
        client, headers, account_id=a1, date="2026-04-01", amount=50000,
        is_ready_to_assign=True, payee="Employer Inc",
    )

    r = await client.get(
        "/api/transactions/category-suggestions",
        params={"account_id": a2, "payee": "Employer Inc"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json() == []


# ---------------------------------------------------------------------------
# List filters, pagination, and bulk-set-category
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_filters_by_category_id(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    groceries = await create_category(client, headers, g, "Groceries")
    fun = await create_category(client, headers, g, "Fun")

    wanted = await _add_txn(
        client, headers, account_id=a, date="2026-04-01", amount=-100, category_id=groceries
    )
    await _add_txn(client, headers, account_id=a, date="2026-04-02", amount=-200, category_id=fun)

    rows = await list_transactions(client, headers, category_id=groceries)
    assert [r["id"] for r in rows] == [wanted]


@pytest.mark.asyncio
async def test_list_category_id_filter_matches_split_lines_too(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    groceries = await create_category(client, headers, g, "Groceries")
    fun = await create_category(client, headers, g, "Fun")

    r = await client.post(
        "/api/transactions",
        json={
            "account_id": a,
            "date": "2026-04-01",
            "payee": "",
            "memo": "",
            "amount_cents": -1000,
            "splits": [
                {"category_id": groceries, "amount_cents": -400},
                {"category_id": fun, "amount_cents": -600},
            ],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    split_txn_id = r.json()["id"]

    rows = await list_transactions(client, headers, category_id=groceries)
    assert [row["id"] for row in rows] == [split_txn_id]


@pytest.mark.asyncio
async def test_list_unassigned_filter_accounts_for_split_transactions_with_a_null_line(
    client: AsyncClient,
):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    groceries = await create_category(client, headers, g, "Groceries")

    fully_categorized = await client.post(
        "/api/transactions",
        json={
            "account_id": a,
            "date": "2026-04-01",
            "payee": "",
            "memo": "",
            "amount_cents": -1000,
            "splits": [
                {"category_id": groceries, "amount_cents": -400},
                {"category_id": groceries, "amount_cents": -600},
            ],
        },
        headers=headers,
    )
    has_null_line = await client.post(
        "/api/transactions",
        json={
            "account_id": a,
            "date": "2026-04-02",
            "payee": "",
            "memo": "",
            "amount_cents": -1000,
            "splits": [
                {"category_id": groceries, "amount_cents": -400},
                {"category_id": None, "amount_cents": -600},
            ],
        },
        headers=headers,
    )
    plain_unassigned = await _add_txn(client, headers, account_id=a, date="2026-04-03", amount=-500)

    rows = await list_transactions(client, headers, unassigned=True)
    ids = {row["id"] for row in rows}
    assert ids == {has_null_line.json()["id"], plain_unassigned}
    assert fully_categorized.json()["id"] not in ids


@pytest.mark.asyncio
async def test_list_unassigned_filter_excludes_transfer_legs(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers, "A1")
    b = await create_account(client, headers, "A2")
    plain_unassigned = await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=-500)

    # A transfer pair: uncategorized on both legs, but never "needs a category".
    outflow = await _add_txn(client, headers, account_id=a, date="2026-04-02", amount=-300)
    inflow = await _add_txn(client, headers, account_id=b, date="2026-04-02", amount=300)
    link = await client.post(
        f"/api/transactions/{outflow}/transfer-link",
        json={"peer_transaction_id": inflow},
        headers=headers,
    )
    assert link.status_code == 200, link.text

    rows = await list_transactions(client, headers, unassigned=True)
    ids = {row["id"] for row in rows}
    assert ids == {plain_unassigned}


@pytest.mark.asyncio
async def test_list_ready_to_assign_filter(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    rta = await _add_txn(
        client, headers, account_id=a, date="2026-04-01", amount=1000, is_ready_to_assign=True
    )
    await _add_txn(client, headers, account_id=a, date="2026-04-02", amount=-200)

    rows = await list_transactions(client, headers, ready_to_assign=True)
    assert [r["id"] for r in rows] == [rta]


@pytest.mark.asyncio
async def test_list_free_text_search_matches_payee_or_memo(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    payee_match = await _add_txn(
        client, headers, account_id=a, date="2026-04-01", amount=-100, payee="Coffee Shop"
    )
    r = await client.post(
        "/api/transactions",
        json={
            "account_id": a,
            "date": "2026-04-02",
            "payee": "",
            "memo": "Bought coffee beans",
            "amount_cents": -200,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    memo_match = r.json()["id"]
    await _add_txn(client, headers, account_id=a, date="2026-04-03", amount=-300, payee="Rent")

    rows = await list_transactions(client, headers, q="coffee")
    assert {row["id"] for row in rows} == {payee_match, memo_match}


@pytest.mark.asyncio
async def test_list_search_is_case_insensitive(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    wanted = await _add_txn(
        client, headers, account_id=a, date="2026-04-01", amount=-100, payee="AMAZON"
    )

    rows = await list_transactions(client, headers, q="amazon")
    assert [r["id"] for r in rows] == [wanted]


@pytest.mark.asyncio
async def test_list_account_id_accepts_multiple_values(client: AsyncClient):
    headers = await register_user(client)
    a1 = await create_account(client, headers, "A1")
    a2 = await create_account(client, headers, "A2")
    a3 = await create_account(client, headers, "A3")
    t1 = await _add_txn(client, headers, account_id=a1, date="2026-04-01", amount=100)
    t2 = await _add_txn(client, headers, account_id=a2, date="2026-04-02", amount=200)
    await _add_txn(client, headers, account_id=a3, date="2026-04-03", amount=300)

    r = await client.get(
        "/api/transactions", params=[("account_id", a1), ("account_id", a2)], headers=headers
    )
    assert r.status_code == 200, r.text
    assert {row["id"] for row in r.json()["items"]} == {t1, t2}


@pytest.mark.asyncio
async def test_list_without_limit_returns_everything_unpaginated(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    for i in range(5):
        await _add_txn(client, headers, account_id=a, date=f"2026-04-{i + 1:02d}", amount=100)

    r = await client.get("/api/transactions", headers=headers)
    body = r.json()
    assert len(body["items"]) == 5
    assert body["next_cursor"] is None


@pytest.mark.asyncio
async def test_list_pagination_returns_next_cursor_when_more_rows_exist(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    for i in range(5):
        await _add_txn(client, headers, account_id=a, date=f"2026-04-{i + 1:02d}", amount=100)

    r = await client.get("/api/transactions", params={"limit": 3}, headers=headers)
    body = r.json()
    assert len(body["items"]) == 3
    assert body["next_cursor"] is not None


@pytest.mark.asyncio
async def test_list_pagination_second_page_has_no_overlap_or_gap_with_the_first(
    client: AsyncClient,
):
    headers = await register_user(client)
    a = await create_account(client, headers)
    ids = [
        await _add_txn(client, headers, account_id=a, date=f"2026-04-{i + 1:02d}", amount=100)
        for i in range(5)
    ]

    first = (
        await client.get("/api/transactions", params={"limit": 3}, headers=headers)
    ).json()
    second = (
        await client.get(
            "/api/transactions",
            params={"limit": 3, "cursor": first["next_cursor"]},
            headers=headers,
        )
    ).json()

    first_ids = [row["id"] for row in first["items"]]
    second_ids = [row["id"] for row in second["items"]]
    assert set(first_ids) & set(second_ids) == set()
    assert sorted(first_ids + second_ids) == sorted(ids)
    assert second["next_cursor"] is None


@pytest.mark.asyncio
async def test_list_pagination_rejects_malformed_cursor(client: AsyncClient):
    headers = await register_user(client)
    r = await client.get(
        "/api/transactions", params={"limit": 5, "cursor": "not-a-cursor"}, headers=headers
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_bulk_set_category_updates_selected_transactions(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    groceries = await create_category(client, headers, g, "Groceries")
    t1 = await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=-100)
    t2 = await _add_txn(client, headers, account_id=a, date="2026-04-02", amount=-200)

    r = await client.post(
        "/api/transactions/bulk-set-category",
        json={"ids": [t1, t2], "category_id": groceries},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": 2}

    rows = await list_transactions(client, headers)
    assert {row["category_id"] for row in rows} == {groceries}


@pytest.mark.asyncio
async def test_bulk_set_category_clears_to_unassigned(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    groceries = await create_category(client, headers, g, "Groceries")
    t1 = await _add_txn(
        client, headers, account_id=a, date="2026-04-01", amount=-100, category_id=groceries
    )

    r = await client.post(
        "/api/transactions/bulk-set-category",
        json={"ids": [t1], "category_id": None},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": 1}

    [row] = await list_transactions(client, headers)
    assert row["category_id"] is None


@pytest.mark.asyncio
async def test_bulk_set_category_skips_transfer_legs(client: AsyncClient):
    headers = await register_user(client)
    a1 = await create_account(client, headers, "A1")
    a2 = await create_account(client, headers, "A2")
    g = await create_group(client, headers)
    groceries = await create_category(client, headers, g, "Groceries")

    r = await client.post(
        "/api/transactions/transfer",
        json={
            "from_account_id": a1,
            "to_account_id": a2,
            "date": "2026-04-01",
            "payee": "",
            "memo": "",
            "amount_cents": 1000,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    leg_id = r.json()["from_transaction"]["id"]

    r = await client.post(
        "/api/transactions/bulk-set-category",
        json={"ids": [leg_id], "category_id": groceries},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": 0}


@pytest.mark.asyncio
async def test_bulk_set_category_skips_split_transactions(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    c1 = await create_category(client, headers, g, "A")
    c2 = await create_category(client, headers, g, "B")
    c3 = await create_category(client, headers, g, "C")

    r = await client.post(
        "/api/transactions",
        json={
            "account_id": a,
            "date": "2026-04-01",
            "payee": "",
            "memo": "",
            "amount_cents": -1000,
            "splits": [
                {"category_id": c1, "amount_cents": -400},
                {"category_id": c2, "amount_cents": -600},
            ],
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    split_txn_id = r.json()["id"]

    r = await client.post(
        "/api/transactions/bulk-set-category",
        json={"ids": [split_txn_id], "category_id": c3},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": 0}


@pytest.mark.asyncio
async def test_bulk_set_category_skips_rows_outside_the_categorys_scope(client: AsyncClient):
    headers = await register_user(client)
    personal_account = await create_account(client, headers, "Checking", scope=PERSONAL)
    shared_group = await create_group(client, headers, "Bills", scope=FAMILY)
    shared_category = await create_category(client, headers, shared_group, "Rent")
    t1 = await _add_txn(
        client, headers, account_id=personal_account, date="2026-04-01", amount=-1000
    )

    r = await client.post(
        "/api/transactions/bulk-set-category",
        json={"ids": [t1], "category_id": shared_category},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"updated": 0}


@pytest.mark.asyncio
async def test_bulk_set_category_rejects_unknown_category_id(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    t1 = await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=-100)

    r = await client.post(
        "/api/transactions/bulk-set-category",
        json={"ids": [t1], "category_id": 999_999},
        headers=headers,
    )
    assert r.status_code == 400
