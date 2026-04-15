"""Budget router: assignment upsert, month parsing, ownership, multi-group shape."""

import pytest
from httpx import AsyncClient

from tests.conftest import create_account, create_category, create_group, register_user


async def _add_inflow(client: AsyncClient, headers: dict, account_id: int, amount: int, date: str):
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


async def _assign(client: AsyncClient, headers: dict, month: str, category_id: int, amount: int):
    r = await client.post(
        f"/api/budget/{month}/assign",
        json={"category_id": category_id, "amount_cents": amount},
        headers=headers,
    )
    assert r.status_code == 204, r.text


@pytest.mark.asyncio
async def test_empty_budget_has_zero_ready_to_assign(client: AsyncClient):
    headers = await register_user(client)
    r = await client.get("/api/budget/2026-04", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["month"] == "2026-04"
    assert body["ready_to_assign_cents"] == 0
    assert body["groups"] == []


@pytest.mark.asyncio
async def test_assign_upsert_overwrites_previous_value(client: AsyncClient):
    """The second assignment must replace the first, not stack on top of it."""
    headers = await register_user(client)
    account = await create_account(client, headers)
    group = await create_group(client, headers)
    cat = await create_category(client, headers, group)

    await _add_inflow(client, headers, account, 100_000, "2026-04-01")

    await _assign(client, headers, "2026-04", cat, 30_000)
    await _assign(client, headers, "2026-04", cat, 70_000)

    body = (await client.get("/api/budget/2026-04", headers=headers)).json()
    assert body["ready_to_assign_cents"] == 30_000  # 1000 - 700, NOT 1000 - 300 - 700
    rent_row = body["groups"][0]["categories"][0]
    assert rent_row["assigned_cents"] == 70_000


@pytest.mark.asyncio
async def test_assign_can_reduce_to_zero(client: AsyncClient):
    headers = await register_user(client)
    account = await create_account(client, headers)
    group = await create_group(client, headers)
    cat = await create_category(client, headers, group)

    await _add_inflow(client, headers, account, 100_000, "2026-04-01")
    await _assign(client, headers, "2026-04", cat, 50_000)
    await _assign(client, headers, "2026-04", cat, 0)

    body = (await client.get("/api/budget/2026-04", headers=headers)).json()
    assert body["ready_to_assign_cents"] == 100_000
    assert body["groups"][0]["categories"][0]["assigned_cents"] == 0


@pytest.mark.asyncio
async def test_invalid_month_format_is_400(client: AsyncClient):
    headers = await register_user(client)
    for bad in ["2026-13", "not-a-month", "2026", "2026-04-01"]:
        r = await client.get(f"/api/budget/{bad}", headers=headers)
        assert r.status_code == 400, f"expected 400 for {bad!r}, got {r.status_code}"


@pytest.mark.asyncio
async def test_cannot_assign_to_other_users_category(client: AsyncClient):
    alice = await register_user(client, "alice@example.com")
    bob = await register_user(client, "bob@example.com")
    alice_group = await create_group(client, alice)
    alice_cat = await create_category(client, alice, alice_group)

    r = await client.post(
        "/api/budget/2026-04/assign",
        json={"category_id": alice_cat, "amount_cents": 10_000},
        headers=bob,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_multi_group_budget_response_shape(client: AsyncClient):
    headers = await register_user(client)
    account = await create_account(client, headers)

    bills = await create_group(client, headers, "Bills")
    fun = await create_group(client, headers, "Fun")
    rent = await create_category(client, headers, bills, "Rent")
    power = await create_category(client, headers, bills, "Electricity")
    concerts = await create_category(client, headers, fun, "Concerts")

    await _add_inflow(client, headers, account, 200_000, "2026-04-01")
    await _assign(client, headers, "2026-04", rent, 60_000)
    await _assign(client, headers, "2026-04", power, 10_000)
    await _assign(client, headers, "2026-04", concerts, 20_000)

    body = (await client.get("/api/budget/2026-04", headers=headers)).json()
    assert body["ready_to_assign_cents"] == 110_000

    groups = {g["name"]: g for g in body["groups"]}
    assert set(groups) == {"Bills", "Fun"}
    bills_cats = {c["name"]: c for c in groups["Bills"]["categories"]}
    assert bills_cats["Rent"]["assigned_cents"] == 60_000
    assert bills_cats["Electricity"]["assigned_cents"] == 10_000
    fun_cats = {c["name"]: c for c in groups["Fun"]["categories"]}
    assert fun_cats["Concerts"]["assigned_cents"] == 20_000


@pytest.mark.asyncio
async def test_ready_to_assign_respects_month_boundary(client: AsyncClient):
    """Assigning in May shouldn't reduce Ready-to-Assign for April."""
    headers = await register_user(client)
    account = await create_account(client, headers)
    group = await create_group(client, headers)
    cat = await create_category(client, headers, group)

    await _add_inflow(client, headers, account, 100_000, "2026-04-01")
    await _assign(client, headers, "2026-05", cat, 40_000)

    april = (await client.get("/api/budget/2026-04", headers=headers)).json()
    may = (await client.get("/api/budget/2026-05", headers=headers)).json()
    assert april["ready_to_assign_cents"] == 100_000
    assert may["ready_to_assign_cents"] == 60_000
