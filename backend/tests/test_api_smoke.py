"""End-to-end smoke test of the API through the zero-based happy path."""

import pytest
from httpx import AsyncClient


async def _register(client: AsyncClient, email: str = "alice@example.com") -> str:
    r = await client.post(
        "/api/auth/register", json={"email": email, "password": "supersecret"}
    )
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_full_zero_based_flow(client: AsyncClient):
    token = await _register(client)
    headers = {"Authorization": f"Bearer {token}"}

    # /me works with the issued token.
    me = await client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"

    # Create an account.
    acct = await client.post(
        "/api/accounts", json={"name": "Checking", "type": "checking"}, headers=headers
    )
    assert acct.status_code == 201, acct.text
    account_id = acct.json()["id"]
    assert acct.json()["balance_cents"] == 0

    # Add a +1000.00 EUR inflow with no category — the source of Ready-to-Assign.
    inflow = await client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "category_id": None,
            "date": "2026-04-02",
            "payee": "Employer",
            "memo": "April salary",
            "amount_cents": 100_000,
        },
        headers=headers,
    )
    assert inflow.status_code == 201, inflow.text

    # Create a category group + category.
    group = await client.post(
        "/api/category-groups", json={"name": "Bills"}, headers=headers
    )
    assert group.status_code == 201, group.text
    group_id = group.json()["id"]

    cat = await client.post(
        "/api/categories",
        json={
            "group_id": group_id,
            "name": "Rent",
            "goal_kind": "monthly",
            "goal_amount_cents": 50_000,
        },
        headers=headers,
    )
    assert cat.status_code == 201, cat.text
    rent_id = cat.json()["id"]

    # Ready-to-Assign = 1000.00 before we assign anything.
    budget = await client.get("/api/budget/2026-04", headers=headers)
    assert budget.status_code == 200, budget.text
    body = budget.json()
    assert body["ready_to_assign_cents"] == 100_000
    assert body["groups"][0]["categories"][0]["name"] == "Rent"

    # Assign 600.00 to Rent.
    r = await client.post(
        "/api/budget/2026-04/assign",
        json={"category_id": rent_id, "amount_cents": 60_000},
        headers=headers,
    )
    assert r.status_code == 204, r.text

    # Log a -150.00 outflow against Rent.
    out = await client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "category_id": rent_id,
            "date": "2026-04-10",
            "payee": "Landlord",
            "memo": "",
            "amount_cents": -15_000,
        },
        headers=headers,
    )
    assert out.status_code == 201, out.text

    # Verify the budget view.
    budget = (await client.get("/api/budget/2026-04", headers=headers)).json()
    assert budget["ready_to_assign_cents"] == 40_000  # 1000 - 600
    rent_row = budget["groups"][0]["categories"][0]
    assert rent_row["assigned_cents"] == 60_000
    assert rent_row["activity_cents"] == -15_000
    assert rent_row["balance_cents"] == 45_000  # 600 - 150

    # Account balance reflects both transactions.
    accounts = (await client.get("/api/accounts", headers=headers)).json()
    assert accounts[0]["balance_cents"] == 85_000  # 1000 - 150

    # Next month: Rent balance rolls forward, no new assignment yet.
    may_budget = (await client.get("/api/budget/2026-05", headers=headers)).json()
    may_rent = may_budget["groups"][0]["categories"][0]
    assert may_rent["assigned_cents"] == 0
    assert may_rent["activity_cents"] == 0
    assert may_rent["balance_cents"] == 45_000


@pytest.mark.asyncio
async def test_users_are_isolated(client: AsyncClient):
    alice = await _register(client, "alice@example.com")
    bob = await _register(client, "bob@example.com")

    # Alice creates an account.
    r = await client.post(
        "/api/accounts",
        json={"name": "Alice checking", "type": "checking"},
        headers={"Authorization": f"Bearer {alice}"},
    )
    assert r.status_code == 201

    # Bob cannot see it.
    r = await client.get(
        "/api/accounts", headers={"Authorization": f"Bearer {bob}"}
    )
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_auth_required(client: AsyncClient):
    r = await client.get("/api/accounts")
    assert r.status_code == 401
