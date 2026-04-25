"""Goal validation rules on Category create/update."""

import pytest
from httpx import AsyncClient

from tests.conftest import create_category, create_group, register_user


@pytest.mark.asyncio
async def test_create_requires_goal_kind(client: AsyncClient):
    headers = await register_user(client)
    group_id = await create_group(client, headers)
    r = await client.post(
        "/api/categories",
        json={"group_id": group_id, "name": "Rent"},
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_target_date_requires_target_month(client: AsyncClient):
    headers = await register_user(client)
    group_id = await create_group(client, headers)
    r = await client.post(
        "/api/categories",
        json={
            "group_id": group_id,
            "name": "New phone",
            "goal_kind": "target_date",
            "goal_amount_cents": 80_000,
        },
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_monthly_rejects_target_month(client: AsyncClient):
    headers = await register_user(client)
    group_id = await create_group(client, headers)
    r = await client.post(
        "/api/categories",
        json={
            "group_id": group_id,
            "name": "Rent",
            "goal_kind": "monthly",
            "goal_amount_cents": 10_000,
            "goal_target_month": "2026-09-01",
        },
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_amount_must_be_positive(client: AsyncClient):
    headers = await register_user(client)
    group_id = await create_group(client, headers)
    for bad in (0, -1):
        r = await client.post(
            "/api/categories",
            json={
                "group_id": group_id,
                "name": "Rent",
                "goal_kind": "monthly",
                "goal_amount_cents": bad,
            },
            headers=headers,
        )
        assert r.status_code == 422, bad


@pytest.mark.asyncio
async def test_target_month_must_be_first_of_month(client: AsyncClient):
    headers = await register_user(client)
    group_id = await create_group(client, headers)
    r = await client.post(
        "/api/categories",
        json={
            "group_id": group_id,
            "name": "Trip",
            "goal_kind": "target_date",
            "goal_amount_cents": 80_000,
            "goal_target_month": "2026-09-15",
        },
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_target_date_round_trip(client: AsyncClient):
    headers = await register_user(client)
    group_id = await create_group(client, headers)
    cat_id = await create_category(
        client,
        headers,
        group_id,
        name="Trip",
        goal_kind="target_date",
        goal_amount_cents=80_000,
        goal_target_month="2026-09-01",
    )
    body = (await client.get("/api/category-groups", headers=headers)).json()
    cat = next(c for c in body[0]["categories"] if c["id"] == cat_id)
    assert cat["goal_kind"] == "target_date"
    assert cat["goal_amount_cents"] == 80_000
    assert cat["goal_target_month"] == "2026-09-01"


@pytest.mark.asyncio
async def test_patch_change_kind_requires_consistent_fields(client: AsyncClient):
    headers = await register_user(client)
    group_id = await create_group(client, headers)
    cat_id = await create_category(client, headers, group_id, "Rent")

    # Switching to target_date without supplying a target month is rejected.
    r = await client.patch(
        f"/api/categories/{cat_id}",
        json={"goal_kind": "target_date"},
        headers=headers,
    )
    assert r.status_code == 422

    # Supplying both is accepted.
    r = await client.patch(
        f"/api/categories/{cat_id}",
        json={"goal_kind": "target_date", "goal_target_month": "2026-12-01"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["goal_kind"] == "target_date"
    assert r.json()["goal_target_month"] == "2026-12-01"

    # Switching back to monthly must clear the target month — leaving the
    # stale value in place would be invalid.
    r = await client.patch(
        f"/api/categories/{cat_id}",
        json={"goal_kind": "monthly"},
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_partial_only_updates_amount(client: AsyncClient):
    headers = await register_user(client)
    group_id = await create_group(client, headers)
    cat_id = await create_category(
        client,
        headers,
        group_id,
        name="Trip",
        goal_kind="target_date",
        goal_amount_cents=80_000,
        goal_target_month="2026-09-01",
    )

    r = await client.patch(
        f"/api/categories/{cat_id}",
        json={"goal_amount_cents": 100_000},
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["goal_kind"] == "target_date"
    assert body["goal_amount_cents"] == 100_000
    assert body["goal_target_month"] == "2026-09-01"
