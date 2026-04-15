"""Transactions router: CRUD, filters, ownership, category clearing."""

import pytest
from httpx import AsyncClient

from tests.conftest import create_account, create_category, create_group, register_user


async def _add_txn(
    client: AsyncClient,
    headers: dict,
    *,
    account_id: int,
    date: str,
    amount: int,
    category_id: int | None = None,
    payee: str = "",
) -> int:
    r = await client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "category_id": category_id,
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
    r = await client.get("/api/transactions", headers=headers)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_filter_by_account(client: AsyncClient):
    headers = await register_user(client)
    a1 = await create_account(client, headers, "A1")
    a2 = await create_account(client, headers, "A2")

    await _add_txn(client, headers, account_id=a1, date="2026-04-01", amount=1000)
    await _add_txn(client, headers, account_id=a1, date="2026-04-02", amount=2000)
    await _add_txn(client, headers, account_id=a2, date="2026-04-03", amount=3000)

    r = await client.get(f"/api/transactions?account_id={a1}", headers=headers)
    assert r.status_code == 200
    amounts = sorted(t["amount_cents"] for t in r.json())
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

    r = await client.get("/api/transactions?month=2026-04", headers=headers)
    amounts = sorted(t["amount_cents"] for t in r.json())
    assert amounts == [200, 300, 400]


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
    assert (await client.get("/api/transactions", headers=headers)).json() == []


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
