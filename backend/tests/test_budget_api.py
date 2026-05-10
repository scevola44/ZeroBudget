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
    assert body["personal_ready_to_assign_cents"] == 0
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
    assert body["personal_ready_to_assign_cents"] == 30_000  # 1000 - 700, NOT 1000 - 300 - 700
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
    assert body["personal_ready_to_assign_cents"] == 100_000
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
    assert body["personal_ready_to_assign_cents"] == 110_000

    groups = {g["name"]: g for g in body["groups"]}
    assert set(groups) == {"Bills", "Fun"}
    bills_cats = {c["name"]: c for c in groups["Bills"]["categories"]}
    assert bills_cats["Rent"]["assigned_cents"] == 60_000
    assert bills_cats["Electricity"]["assigned_cents"] == 10_000
    fun_cats = {c["name"]: c for c in groups["Fun"]["categories"]}
    assert fun_cats["Concerts"]["assigned_cents"] == 20_000


@pytest.mark.asyncio
async def test_budget_row_includes_goal_fields(client: AsyncClient):
    headers = await register_user(client)
    account = await create_account(client, headers)
    group = await create_group(client, headers)
    cat = await create_category(
        client,
        headers,
        group,
        name="Trip",
        goal_kind="target_date",
        goal_amount_cents=120_000,
        goal_target_month="2026-09-01",
    )
    await _add_inflow(client, headers, account, 200_000, "2026-04-01")
    await _assign(client, headers, "2026-04", cat, 0)

    body = (await client.get("/api/budget/2026-04", headers=headers)).json()
    row = body["groups"][0]["categories"][0]
    assert row["goal_kind"] == "target_date"
    assert row["goal_amount_cents"] == 120_000
    assert row["goal_target_month"] == "2026-09-01"
    # April → September is 6 months inclusive, balance is 0, so we should
    # need ~120_000/6 = 20_000 each month.
    assert row["needed_this_month_cents"] == 20_000


@pytest.mark.asyncio
async def test_monthly_goal_needed_drops_to_zero_when_balance_meets_goal(
    client: AsyncClient,
):
    headers = await register_user(client)
    account = await create_account(client, headers)
    group = await create_group(client, headers)
    cat = await create_category(
        client,
        headers,
        group,
        name="Rent",
        goal_kind="monthly",
        goal_amount_cents=50_000,
    )
    await _add_inflow(client, headers, account, 100_000, "2026-04-01")
    await _assign(client, headers, "2026-04", cat, 50_000)

    body = (await client.get("/api/budget/2026-04", headers=headers)).json()
    row = body["groups"][0]["categories"][0]
    assert row["goal_kind"] == "monthly"
    assert row["needed_this_month_cents"] == 0


@pytest.mark.asyncio
async def test_future_assignment_reduces_past_month_ready_to_assign(client: AsyncClient):
    """Assigning in May must also reduce Ready-to-Assign for April (within scope)."""
    headers = await register_user(client)
    account = await create_account(client, headers)
    group = await create_group(client, headers)
    cat = await create_category(client, headers, group)

    await _add_inflow(client, headers, account, 100_000, "2026-04-01")
    await _assign(client, headers, "2026-05", cat, 40_000)

    april = (await client.get("/api/budget/2026-04", headers=headers)).json()
    may = (await client.get("/api/budget/2026-05", headers=headers)).json()
    assert april["personal_ready_to_assign_cents"] == 60_000
    assert may["personal_ready_to_assign_cents"] == 60_000


@pytest.mark.asyncio
async def test_budget_response_carries_both_rta_fields_and_group_scope(client: AsyncClient):
    headers = await register_user(client)
    await create_group(client, headers, "Hobbies", scope="personal")
    await create_group(client, headers, "Family", scope="shared")

    body = (await client.get("/api/budget/2026-04", headers=headers)).json()
    assert body["personal_ready_to_assign_cents"] == 0
    assert body["shared_ready_to_assign_cents"] == 0
    by_name = {g["name"]: g for g in body["groups"]}
    assert by_name["Hobbies"]["scope"] == "personal"
    assert by_name["Family"]["scope"] == "shared"


@pytest.mark.asyncio
async def test_personal_and_shared_rta_are_independent_pools(client: AsyncClient):
    headers = await register_user(client)
    personal_account = await create_account(client, headers, "Personal", scope="personal")
    shared_account = await create_account(client, headers, "Joint", scope="shared")
    personal_group = await create_group(client, headers, "Hobbies", scope="personal")
    shared_group = await create_group(client, headers, "Family", scope="shared")
    hobbies = await create_category(client, headers, personal_group, "Hobbies")
    groceries = await create_category(client, headers, shared_group, "Groceries")

    await _add_inflow(client, headers, personal_account, 100_000, "2026-04-01")
    await _add_inflow(client, headers, shared_account, 80_000, "2026-04-01")
    await _assign(client, headers, "2026-04", hobbies, 30_000)
    await _assign(client, headers, "2026-04", groceries, 50_000)

    body = (await client.get("/api/budget/2026-04", headers=headers)).json()
    assert body["personal_ready_to_assign_cents"] == 70_000
    assert body["shared_ready_to_assign_cents"] == 30_000


@pytest.mark.asyncio
async def test_transfer_pair_moves_money_between_pools(client: AsyncClient):
    headers = await register_user(client)
    personal_account = await create_account(client, headers, "Personal", scope="personal")
    shared_account = await create_account(client, headers, "Joint", scope="shared")

    await _add_inflow(client, headers, personal_account, 100_000, "2026-04-01")
    # Transfer pair: -600 from personal, +600 into shared, both uncategorized.
    await _add_inflow(client, headers, personal_account, -60_000, "2026-04-02")
    await _add_inflow(client, headers, shared_account, 60_000, "2026-04-02")

    body = (await client.get("/api/budget/2026-04", headers=headers)).json()
    assert body["personal_ready_to_assign_cents"] == 40_000
    assert body["shared_ready_to_assign_cents"] == 60_000


@pytest.mark.asyncio
async def test_cross_scope_transaction_is_rejected(client: AsyncClient):
    headers = await register_user(client)
    personal_account = await create_account(client, headers, "Personal", scope="personal")
    shared_group = await create_group(client, headers, "Family", scope="shared")
    groceries = await create_category(client, headers, shared_group, "Groceries")

    r = await client.post(
        "/api/transactions",
        json={
            "account_id": personal_account,
            "category_id": groceries,
            "date": "2026-04-05",
            "payee": "Aldi",
            "memo": "",
            "amount_cents": -3_000,
        },
        headers=headers,
    )
    assert r.status_code == 422, r.text
    assert "scope" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_uncategorized_transaction_across_scopes_is_allowed(client: AsyncClient):
    """The strict scope guard must not break inflows or transfers, which are
    intentionally uncategorized."""
    headers = await register_user(client)
    shared_account = await create_account(client, headers, "Joint", scope="shared")

    r = await client.post(
        "/api/transactions",
        json={
            "account_id": shared_account,
            "category_id": None,
            "date": "2026-04-01",
            "payee": "Salary",
            "memo": "",
            "amount_cents": 100_000,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_account_scope_change_blocked_when_categorized_txns_exist(client: AsyncClient):
    headers = await register_user(client)
    account = await create_account(client, headers, "A", scope="personal")
    group = await create_group(client, headers, "G", scope="personal")
    cat = await create_category(client, headers, group)

    r = await client.post(
        "/api/transactions",
        json={
            "account_id": account,
            "category_id": cat,
            "date": "2026-04-05",
            "payee": "x",
            "memo": "",
            "amount_cents": -1_000,
        },
        headers=headers,
    )
    assert r.status_code == 201

    r = await client.patch(
        f"/api/accounts/{account}", json={"scope": "shared"}, headers=headers
    )
    assert r.status_code == 400
    assert "categorized" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_account_scope_change_allowed_when_only_uncategorized_txns(client: AsyncClient):
    headers = await register_user(client)
    account = await create_account(client, headers, "A", scope="personal")
    await _add_inflow(client, headers, account, 50_000, "2026-04-01")

    r = await client.patch(
        f"/api/accounts/{account}", json={"scope": "shared"}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["scope"] == "shared"

    body = (await client.get("/api/budget/2026-04", headers=headers)).json()
    assert body["personal_ready_to_assign_cents"] == 0
    assert body["shared_ready_to_assign_cents"] == 50_000


@pytest.mark.asyncio
async def test_group_scope_change_blocked_when_categories_exist(client: AsyncClient):
    headers = await register_user(client)
    group = await create_group(client, headers, "G", scope="personal")
    await create_category(client, headers, group)

    r = await client.patch(
        f"/api/category-groups/{group}", json={"scope": "shared"}, headers=headers
    )
    assert r.status_code == 400
