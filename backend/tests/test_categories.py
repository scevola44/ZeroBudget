"""Categories router: groups + categories CRUD, ownership isolation."""

import pytest
from httpx import AsyncClient

from tests.conftest import (
    FAMILY,
    PERSONAL,
    create_account,
    create_category,
    create_group,
    list_transactions,
    register_user,
)


@pytest.mark.asyncio
async def test_list_empty(client: AsyncClient):
    headers = await register_user(client)
    r = await client.get("/api/category-groups", headers=headers)
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_create_group_and_nested_category(client: AsyncClient):
    headers = await register_user(client)
    group_id = await create_group(client, headers, "Bills")
    await create_category(client, headers, group_id, "Rent")
    await create_category(client, headers, group_id, "Electricity")

    r = await client.get("/api/category-groups", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["name"] == "Bills"
    assert [c["name"] for c in body[0]["categories"]] == ["Rent", "Electricity"]
    rent = body[0]["categories"][0]
    assert rent["goal_kind"] == "monthly"
    assert rent["goal_amount_cents"] == 10_000
    assert rent["goal_target_month"] is None


@pytest.mark.asyncio
async def test_multiple_groups_are_listed_in_order(client: AsyncClient):
    headers = await register_user(client)
    await create_group(client, headers, "Bills")
    await create_group(client, headers, "Fun")
    await create_group(client, headers, "Savings")

    groups = (await client.get("/api/category-groups", headers=headers)).json()
    assert [g["name"] for g in groups] == ["Bills", "Fun", "Savings"]
    assert all(g["categories"] == [] for g in groups)


@pytest.mark.asyncio
async def test_update_group_renames(client: AsyncClient):
    headers = await register_user(client)
    group_id = await create_group(client, headers, "Old")
    r = await client.patch(
        f"/api/category-groups/{group_id}",
        json={"name": "New"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["name"] == "New"


@pytest.mark.asyncio
async def test_delete_group_removes_it(client: AsyncClient):
    headers = await register_user(client)
    group_id = await create_group(client, headers)
    r = await client.delete(f"/api/category-groups/{group_id}", headers=headers)
    assert r.status_code == 204
    assert (await client.get("/api/category-groups", headers=headers)).json() == []


@pytest.mark.asyncio
async def test_update_category_can_move_groups(client: AsyncClient):
    headers = await register_user(client)
    g1 = await create_group(client, headers, "Bills")
    g2 = await create_group(client, headers, "Fun")
    cat_id = await create_category(client, headers, g1, "Rent")

    r = await client.patch(
        f"/api/categories/{cat_id}",
        json={"group_id": g2, "name": "Concert"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["group_id"] == g2
    assert r.json()["name"] == "Concert"


@pytest.mark.asyncio
async def test_delete_category(client: AsyncClient):
    headers = await register_user(client)
    g = await create_group(client, headers)
    cat_id = await create_category(client, headers, g)
    r = await client.delete(f"/api/categories/{cat_id}", headers=headers)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_cannot_create_category_in_other_users_group(client: AsyncClient):
    alice = await register_user(client, "alice@example.com")
    bob = await register_user(client, "bob@example.com")
    g = await create_group(client, alice, "Alice bills")

    r = await client.post(
        "/api/categories",
        json={
            "group_id": g,
            "name": "Hijack",
            "goal_kind": "monthly",
            "goal_amount_cents": 10_000,
        },
        headers=bob,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_cannot_move_category_into_different_scope_group(client: AsyncClient):
    headers = await register_user(client)
    personal_group = await create_group(client, headers, "Personal", scope=PERSONAL)
    shared_group = await create_group(client, headers, "Family", scope=FAMILY)
    dining = await create_category(client, headers, personal_group, "Dining")

    r = await client.patch(
        f"/api/categories/{dining}",
        json={"group_id": shared_group},
        headers=headers,
    )
    assert r.status_code == 422, r.text

    groups = (await client.get("/api/category-groups", headers=headers)).json()
    personal = next(g for g in groups if g["id"] == personal_group)
    assert any(c["id"] == dining for c in personal["categories"])


@pytest.mark.asyncio
async def test_cannot_move_category_into_other_users_group(client: AsyncClient):
    alice = await register_user(client, "alice@example.com")
    bob = await register_user(client, "bob@example.com")
    alice_group = await create_group(client, alice, "Alice group")
    bob_group = await create_group(client, bob, "Bob group")
    bob_cat = await create_category(client, bob, bob_group, "Bob cat")

    # Bob tries to move his own category into Alice's group.
    r = await client.patch(
        f"/api/categories/{bob_cat}",
        json={"group_id": alice_group},
        headers=bob,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_cannot_update_or_delete_other_users_group(client: AsyncClient):
    alice = await register_user(client, "alice@example.com")
    bob = await register_user(client, "bob@example.com")
    alice_group = await create_group(client, alice)

    r = await client.patch(
        f"/api/category-groups/{alice_group}", json={"name": "boom"}, headers=bob
    )
    assert r.status_code == 404
    r = await client.delete(f"/api/category-groups/{alice_group}", headers=bob)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_deleting_a_category_can_rehome_its_transactions(client: AsyncClient):
    headers = await register_user(client)
    account = await create_account(client, headers)
    group = await create_group(client, headers)
    dining = await create_category(client, headers, group, "Dining")
    groceries = await create_category(client, headers, group, "Groceries")

    r = await client.post(
        "/api/transactions",
        json={
            "account_id": account,
            "category_id": dining,
            "date": "2026-04-05",
            "payee": "Cafe",
            "memo": "",
            "amount_cents": -2_500,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text

    r = await client.delete(
        f"/api/categories/{dining}?reassign_to={groceries}", headers=headers
    )
    assert r.status_code == 204, r.text

    rows = await list_transactions(client, headers)
    assert [row["category_id"] for row in rows] == [groceries]


@pytest.mark.asyncio
async def test_deleting_a_category_without_reassignment_uncategorizes(client: AsyncClient):
    headers = await register_user(client)
    account = await create_account(client, headers)
    group = await create_group(client, headers)
    dining = await create_category(client, headers, group, "Dining")

    await client.post(
        "/api/transactions",
        json={
            "account_id": account,
            "category_id": dining,
            "date": "2026-04-05",
            "payee": "Cafe",
            "memo": "",
            "amount_cents": -2_500,
        },
        headers=headers,
    )

    r = await client.delete(f"/api/categories/{dining}", headers=headers)
    assert r.status_code == 204, r.text

    rows = await list_transactions(client, headers)
    assert [row["category_id"] for row in rows] == [None]


@pytest.mark.asyncio
async def test_reassigning_across_scopes_is_rejected(client: AsyncClient):
    """The moved transactions would sit in a category whose scope disagrees
    with their account — the state the transaction scope guard prevents."""
    headers = await register_user(client)
    personal_group = await create_group(client, headers, "Personal", scope=PERSONAL)
    shared_group = await create_group(client, headers, "Family", scope=FAMILY)
    dining = await create_category(client, headers, personal_group, "Dining")
    joint_food = await create_category(client, headers, shared_group, "Food")

    r = await client.delete(
        f"/api/categories/{dining}?reassign_to={joint_food}", headers=headers
    )
    assert r.status_code == 422, r.text

    groups = (await client.get("/api/category-groups", headers=headers)).json()
    surviving = {c["id"] for g in groups for c in g["categories"]}
    assert dining in surviving
