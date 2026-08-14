"""Accounts router: CRUD, ownership isolation, balance derivation."""

import pytest
from httpx import AsyncClient

from tests.conftest import (
    FAMILY,
    PERSONAL,
    create_account,
    list_transactions,
    register_user,
    scope_id,
)


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
async def test_update_changes_scope(client: AsyncClient):
    headers = await register_user(client)
    account_id = await create_account(client, headers, scope=PERSONAL)

    family = await scope_id(client, headers, FAMILY)
    r = await client.patch(
        f"/api/accounts/{account_id}",
        json={"scope_id": family},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["scope_id"] == family


@pytest.mark.asyncio
async def test_update_scope_blocked_with_categorized_transactions(client: AsyncClient):
    headers = await register_user(client)
    account_id = await create_account(client, headers, scope=PERSONAL)
    group_id = (
        await client.post(
            "/api/category-groups",
            json={
                "name": "Bills",
                "scope_id": await scope_id(client, headers, PERSONAL),
            },
            headers=headers,
        )
    ).json()["id"]
    category_id = (
        await client.post(
            "/api/categories",
            json={
                "group_id": group_id,
                "name": "Rent",
                "goal_kind": "monthly",
                "goal_amount_cents": 10_000,
            },
            headers=headers,
        )
    ).json()["id"]
    r = await client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "date": "2026-04-01",
            "payee": "Landlord",
            "memo": "",
            "amount_cents": -10_000,
        },
        headers=headers,
    )
    assert r.status_code == 201

    r = await client.patch(
        f"/api/accounts/{account_id}",
        json={"scope_id": await scope_id(client, headers, FAMILY)},
        headers=headers,
    )
    assert r.status_code == 400


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


@pytest.mark.asyncio
async def test_set_balance_creates_adjustment_transaction(client: AsyncClient):
    headers = await register_user(client)
    account_id = await create_account(client, headers)

    r = await client.post(
        f"/api/accounts/{account_id}/balance",
        json={"balance_cents": 50_000},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["balance_cents"] == 50_000

    txns = await list_transactions(client, headers, account_id=account_id)
    assert len(txns) == 1
    assert txns[0]["payee"] == "Balance Adjustment"
    assert txns[0]["amount_cents"] == 50_000
    assert txns[0]["category_id"] is None

    accounts = (await client.get("/api/accounts", headers=headers)).json()
    assert accounts[0]["balance_cents"] == 50_000


@pytest.mark.asyncio
async def test_set_balance_is_noop_when_already_matching(client: AsyncClient):
    headers = await register_user(client)
    account_id = await create_account(client, headers)

    r = await client.post(
        f"/api/accounts/{account_id}/balance",
        json={"balance_cents": 0},
        headers=headers,
    )
    assert r.status_code == 200

    txns = await list_transactions(client, headers, account_id=account_id)
    assert txns == []


@pytest.mark.asyncio
async def test_set_balance_unknown_account_is_404(client: AsyncClient):
    headers = await register_user(client)
    r = await client.post(
        "/api/accounts/9999/balance", json={"balance_cents": 100}, headers=headers
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_cannot_set_balance_on_other_users_account(client: AsyncClient):
    alice = await register_user(client, "alice@example.com")
    bob = await register_user(client, "bob@example.com")
    account_id = await create_account(client, alice, "Alice account")

    r = await client.post(
        f"/api/accounts/{account_id}/balance", json={"balance_cents": 100}, headers=bob
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_an_account_can_be_closed_and_reopened(client: AsyncClient):
    headers = await register_user(client)
    account = await create_account(client, headers, "Old Savings")

    r = await client.patch(
        f"/api/accounts/{account}", json={"closed": True}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["closed"] is True

    r = await client.patch(
        f"/api/accounts/{account}", json={"closed": False}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["closed"] is False


@pytest.mark.asyncio
async def test_a_closed_account_keeps_its_transactions_and_balance(client: AsyncClient):
    """Closing retires an account without rewriting history — the whole reason
    it exists rather than deleting."""
    headers = await register_user(client)
    account = await create_account(client, headers, "Old Savings")
    r = await client.post(
        "/api/transactions",
        json={
            "account_id": account,
            "category_id": None,
            "date": "2026-04-01",
            "payee": "",
            "memo": "",
            "amount_cents": 25_000,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text

    await client.patch(f"/api/accounts/{account}", json={"closed": True}, headers=headers)

    rows = (await client.get("/api/accounts", headers=headers)).json()
    closed_row = next(row for row in rows if row["id"] == account)
    assert closed_row["closed"] is True
    assert closed_row["balance_cents"] == 25_000


@pytest.mark.asyncio
async def test_deleting_an_account_with_transactions_is_refused(client: AsyncClient):
    headers = await register_user(client)
    account = await create_account(client, headers)
    r = await client.post(
        "/api/transactions",
        json={
            "account_id": account,
            "category_id": None,
            "date": "2026-04-01",
            "payee": "",
            "memo": "",
            "amount_cents": 1_000,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text

    r = await client.delete(f"/api/accounts/{account}", headers=headers)
    assert r.status_code == 400, r.text
    assert "close" in r.json()["detail"].lower()

    rows = (await client.get("/api/accounts", headers=headers)).json()
    assert [row["id"] for row in rows] == [account]


@pytest.mark.asyncio
async def test_an_empty_account_can_still_be_deleted(client: AsyncClient):
    headers = await register_user(client)
    account = await create_account(client, headers)

    r = await client.delete(f"/api/accounts/{account}", headers=headers)
    assert r.status_code == 204, r.text
    assert (await client.get("/api/accounts", headers=headers)).json() == []
