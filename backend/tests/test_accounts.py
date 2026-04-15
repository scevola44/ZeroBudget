"""Accounts router: CRUD, ownership isolation, balance derivation."""

import pytest
from httpx import AsyncClient

from tests.conftest import create_account, register_user


@pytest.mark.asyncio
async def test_list_empty(client: AsyncClient):
    headers = await register_user(client)
    r = await client.get("/api/accounts", headers=headers)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_create_and_list(client: AsyncClient):
    headers = await register_user(client)
    await create_account(client, headers, "Checking")
    await create_account(client, headers, "Savings")

    r = await client.get("/api/accounts", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert [a["name"] for a in body] == ["Checking", "Savings"]
    assert all(a["balance_cents"] == 0 for a in body)


@pytest.mark.asyncio
async def test_update_renames_account(client: AsyncClient):
    headers = await register_user(client)
    account_id = await create_account(client, headers)

    r = await client.patch(
        f"/api/accounts/{account_id}",
        json={"name": "Renamed"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Renamed"


@pytest.mark.asyncio
async def test_update_unknown_account_is_404(client: AsyncClient):
    headers = await register_user(client)
    r = await client.patch(
        "/api/accounts/9999", json={"name": "ghost"}, headers=headers
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_removes_account(client: AsyncClient):
    headers = await register_user(client)
    account_id = await create_account(client, headers)

    r = await client.delete(f"/api/accounts/{account_id}", headers=headers)
    assert r.status_code == 204

    after = await client.get("/api/accounts", headers=headers)
    assert after.json() == []


@pytest.mark.asyncio
async def test_cannot_touch_other_users_account(client: AsyncClient):
    alice = await register_user(client, "alice@example.com")
    bob = await register_user(client, "bob@example.com")
    account_id = await create_account(client, alice, "Alice account")

    # Bob can't see Alice's account.
    r = await client.get("/api/accounts", headers=bob)
    assert r.json() == []

    # Bob can't update it.
    r = await client.patch(
        f"/api/accounts/{account_id}", json={"name": "hijacked"}, headers=bob
    )
    assert r.status_code == 404

    # Bob can't delete it.
    r = await client.delete(f"/api/accounts/{account_id}", headers=bob)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_balance_reflects_transactions(client: AsyncClient):
    headers = await register_user(client)
    account_id = await create_account(client, headers)

    async def add_txn(amount: int, date: str) -> None:
        r = await client.post(
            "/api/transactions",
            json={
                "account_id": account_id,
                "category_id": None,
                "date": date,
                "payee": "",
                "memo": "",
                "amount_cents": amount,
            },
            headers=headers,
        )
        assert r.status_code == 201

    await add_txn(100_000, "2026-04-01")
    await add_txn(-25_000, "2026-04-05")
    await add_txn(5_000, "2026-04-10")

    accounts = (await client.get("/api/accounts", headers=headers)).json()
    assert accounts[0]["balance_cents"] == 80_000
