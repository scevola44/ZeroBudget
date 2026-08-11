"""Transactions router: bulk-category and bulk-delete endpoints."""

import pytest
from httpx import AsyncClient

from tests.conftest import create_account, create_category, create_group, register_user
from tests.test_transactions import _add_txn


async def _transfer(
    client: AsyncClient, headers: dict, from_account_id: int, to_account_id: int, amount: int
) -> dict:
    r = await client.post(
        "/api/transactions/transfer",
        json={
            "from_account_id": from_account_id,
            "to_account_id": to_account_id,
            "amount_cents": amount,
            "date": "2026-04-01",
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_bulk_set_category_happy_path(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    cat = await create_category(client, headers, g, "Groceries")

    id1 = await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=-100)
    id2 = await _add_txn(client, headers, account_id=a, date="2026-04-02", amount=-200)

    r = await client.patch(
        "/api/transactions/bulk-category",
        json={"transaction_ids": [id1, id2], "category_id": cat},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 2

    items = (await client.get("/api/transactions", headers=headers)).json()["items"]
    assert all(t["category_id"] == cat for t in items)


@pytest.mark.asyncio
async def test_bulk_set_category_to_unassigned(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    cat = await create_category(client, headers, g, "Groceries")
    id1 = await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=-100, category_id=cat)

    r = await client.patch(
        "/api/transactions/bulk-category",
        json={"transaction_ids": [id1], "category_id": None},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["updated"] == 1
    items = (await client.get("/api/transactions", headers=headers)).json()["items"]
    assert items[0]["category_id"] is None


@pytest.mark.asyncio
async def test_bulk_set_category_rejects_transfer_leg(client: AsyncClient):
    headers = await register_user(client)
    a1 = await create_account(client, headers, "A1")
    a2 = await create_account(client, headers, "A2")
    g = await create_group(client, headers)
    cat = await create_category(client, headers, g, "Groceries")

    transfer = await _transfer(client, headers, a1, a2, 1000)
    leg_id = transfer["from_transaction"]["id"]

    r = await client.patch(
        "/api/transactions/bulk-category",
        json={"transaction_ids": [leg_id], "category_id": cat},
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_bulk_set_category_rejects_split_transaction(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    c1 = await create_category(client, headers, g, "A")
    c2 = await create_category(client, headers, g, "B")

    r = await client.post(
        "/api/transactions",
        json={
            "account_id": a,
            "date": "2026-04-01",
            "payee": "",
            "memo": "",
            "amount_cents": -3000,
            "splits": [
                {"category_id": c1, "amount_cents": -2000, "memo": ""},
                {"category_id": c2, "amount_cents": -1000, "memo": ""},
            ],
        },
        headers=headers,
    )
    txn_id = r.json()["id"]

    r = await client.patch(
        "/api/transactions/bulk-category",
        json={"transaction_ids": [txn_id], "category_id": c1},
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_bulk_set_category_rejects_scope_mismatch(client: AsyncClient):
    headers = await register_user(client)
    personal_account = await create_account(client, headers, "Checking", scope="personal")
    shared_group = await create_group(client, headers, "Family", scope="shared")
    shared_cat = await create_category(client, headers, shared_group, "Groceries")
    id1 = await _add_txn(client, headers, account_id=personal_account, date="2026-04-01", amount=-100)

    r = await client.patch(
        "/api/transactions/bulk-category",
        json={"transaction_ids": [id1], "category_id": shared_cat},
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_bulk_set_category_silently_drops_unowned_ids(client: AsyncClient):
    alice = await register_user(client, "alice@example.com")
    bob = await register_user(client, "bob@example.com")
    a_bob = await create_account(client, bob)
    bob_txn = await _add_txn(client, bob, account_id=a_bob, date="2026-04-01", amount=-100)

    a_alice = await create_account(client, alice)
    g_alice = await create_group(client, alice)
    cat_alice = await create_category(client, alice, g_alice)
    alice_txn = await _add_txn(client, alice, account_id=a_alice, date="2026-04-01", amount=-100)

    r = await client.patch(
        "/api/transactions/bulk-category",
        json={"transaction_ids": [alice_txn, bob_txn, 999999], "category_id": cat_alice},
        headers=alice,
    )
    assert r.status_code == 200
    assert r.json()["updated"] == 1  # only alice_txn is hers; bob's and the bogus id are dropped

    bob_items = (await client.get("/api/transactions", headers=bob)).json()["items"]
    assert bob_items[0]["category_id"] is None  # bob's transaction untouched


@pytest.mark.asyncio
async def test_bulk_delete_happy_path(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    id1 = await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=-100)
    id2 = await _add_txn(client, headers, account_id=a, date="2026-04-02", amount=-200)
    id3 = await _add_txn(client, headers, account_id=a, date="2026-04-03", amount=-300)

    r = await client.post(
        "/api/transactions/bulk-delete", json={"transaction_ids": [id1, id2]}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == 2

    items = (await client.get("/api/transactions", headers=headers)).json()["items"]
    assert [t["id"] for t in items] == [id3]


@pytest.mark.asyncio
async def test_bulk_delete_a_transfer_pair_counts_both_legs(client: AsyncClient):
    headers = await register_user(client)
    a1 = await create_account(client, headers, "A1")
    a2 = await create_account(client, headers, "A2")
    transfer = await _transfer(client, headers, a1, a2, 1000)
    leg_id = transfer["from_transaction"]["id"]

    r = await client.post(
        "/api/transactions/bulk-delete", json={"transaction_ids": [leg_id]}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["deleted"] == 2  # deleting one leg removes both

    items = (await client.get("/api/transactions", headers=headers)).json()["items"]
    assert items == []


@pytest.mark.asyncio
async def test_bulk_delete_does_not_double_count_when_both_legs_are_selected(
    client: AsyncClient,
):
    headers = await register_user(client)
    a1 = await create_account(client, headers, "A1")
    a2 = await create_account(client, headers, "A2")
    transfer = await _transfer(client, headers, a1, a2, 1000)
    leg1 = transfer["from_transaction"]["id"]
    leg2 = transfer["to_transaction"]["id"]

    r = await client.post(
        "/api/transactions/bulk-delete", json={"transaction_ids": [leg1, leg2]}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["deleted"] == 2  # not 4 — the second leg is already gone by the time it's reached


@pytest.mark.asyncio
async def test_bulk_delete_silently_drops_unowned_ids(client: AsyncClient):
    alice = await register_user(client, "alice@example.com")
    bob = await register_user(client, "bob@example.com")
    a_bob = await create_account(client, bob)
    bob_txn = await _add_txn(client, bob, account_id=a_bob, date="2026-04-01", amount=-100)

    r = await client.post(
        "/api/transactions/bulk-delete", json={"transaction_ids": [bob_txn]}, headers=alice
    )
    assert r.status_code == 200
    assert r.json()["deleted"] == 0

    items = (await client.get("/api/transactions", headers=bob)).json()["items"]
    assert [t["id"] for t in items] == [bob_txn]
