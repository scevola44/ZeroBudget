"""Managing scopes: seeding, adding, renaming, and the deletion guards.

Scopes are the partition every other feature is defined against, so the rules
that matter here are: a user always has at least one, a scope holding data
cannot vanish underneath it, and one user can never reach another's.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import (
    FAMILY,
    PERSONAL,
    create_account,
    create_category,
    create_group,
    register_user,
    scope_id,
    scope_ids,
)


@pytest.mark.asyncio
async def test_registration_seeds_personal_and_family_in_that_order(client: AsyncClient):
    headers = await register_user(client)

    r = await client.get("/api/scopes", headers=headers)

    assert r.status_code == 200, r.text
    assert [(s["name"], s["sort_order"]) for s in r.json()] == [(PERSONAL, 0), (FAMILY, 1)]


@pytest.mark.asyncio
async def test_a_new_scope_lands_after_the_existing_ones(client: AsyncClient):
    headers = await register_user(client)

    r = await client.post("/api/scopes", json={"name": "Business"}, headers=headers)

    assert r.status_code == 201, r.text
    assert r.json()["sort_order"] == 2
    assert [s["name"] for s in (await client.get("/api/scopes", headers=headers)).json()] == [
        PERSONAL,
        FAMILY,
        "Business",
    ]


@pytest.mark.asyncio
async def test_a_duplicate_name_is_rejected(client: AsyncClient):
    headers = await register_user(client)

    r = await client.post("/api/scopes", json={"name": FAMILY}, headers=headers)

    assert r.status_code == 409, r.text
    assert FAMILY in r.json()["detail"]


@pytest.mark.asyncio
async def test_names_are_trimmed_so_padding_cannot_smuggle_in_a_duplicate(
    client: AsyncClient,
):
    headers = await register_user(client)

    r = await client.post("/api/scopes", json={"name": "  Family  "}, headers=headers)

    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_renaming_a_scope_leaves_its_accounts_and_groups_where_they_are(
    client: AsyncClient,
):
    headers = await register_user(client)
    family = await scope_id(client, headers, FAMILY)
    account = await create_account(client, headers, "Joint", scope=FAMILY)
    group = await create_group(client, headers, "Bills", scope=FAMILY)

    r = await client.patch(
        f"/api/scopes/{family}", json={"name": "Household"}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Household"

    accounts = (await client.get("/api/accounts", headers=headers)).json()
    groups = (await client.get("/api/category-groups", headers=headers)).json()
    assert [a["scope_id"] for a in accounts if a["id"] == account] == [family]
    assert [g["scope_id"] for g in groups if g["id"] == group] == [family]


@pytest.mark.asyncio
async def test_an_empty_scope_can_be_deleted(client: AsyncClient):
    headers = await register_user(client)
    family = await scope_id(client, headers, FAMILY)

    r = await client.delete(f"/api/scopes/{family}", headers=headers)

    assert r.status_code == 204, r.text
    assert [s["name"] for s in (await client.get("/api/scopes", headers=headers)).json()] == [
        PERSONAL
    ]


@pytest.mark.asyncio
async def test_a_scope_holding_an_account_cannot_be_deleted(client: AsyncClient):
    headers = await register_user(client)
    family = await scope_id(client, headers, FAMILY)
    await create_account(client, headers, "Joint", scope=FAMILY)

    r = await client.delete(f"/api/scopes/{family}", headers=headers)

    assert r.status_code == 409, r.text
    assert "1 account" in r.json()["detail"]


@pytest.mark.asyncio
async def test_a_scope_holding_a_category_group_cannot_be_deleted(client: AsyncClient):
    headers = await register_user(client)
    family = await scope_id(client, headers, FAMILY)
    await create_group(client, headers, "Bills", scope=FAMILY)

    r = await client.delete(f"/api/scopes/{family}", headers=headers)

    assert r.status_code == 409, r.text
    assert "1 category group" in r.json()["detail"]


@pytest.mark.asyncio
async def test_the_blocker_message_counts_every_kind_of_holder(client: AsyncClient):
    headers = await register_user(client)
    family = await scope_id(client, headers, FAMILY)
    await create_account(client, headers, "Joint", scope=FAMILY)
    await create_account(client, headers, "Savings", scope=FAMILY)
    await create_group(client, headers, "Bills", scope=FAMILY)

    detail = (await client.delete(f"/api/scopes/{family}", headers=headers)).json()["detail"]

    assert "2 accounts" in detail
    assert "1 category group" in detail


@pytest.mark.asyncio
async def test_deleting_becomes_possible_once_the_scope_is_emptied(client: AsyncClient):
    headers = await register_user(client)
    family = await scope_id(client, headers, FAMILY)
    account = await create_account(client, headers, "Joint", scope=FAMILY)
    assert (await client.delete(f"/api/scopes/{family}", headers=headers)).status_code == 409

    await client.delete(f"/api/accounts/{account}", headers=headers)

    assert (await client.delete(f"/api/scopes/{family}", headers=headers)).status_code == 204


@pytest.mark.asyncio
async def test_the_last_scope_cannot_be_deleted(client: AsyncClient):
    headers = await register_user(client)
    scopes = await scope_ids(client, headers)
    assert (
        await client.delete(f"/api/scopes/{scopes[FAMILY]}", headers=headers)
    ).status_code == 204

    r = await client.delete(f"/api/scopes/{scopes[PERSONAL]}", headers=headers)

    assert r.status_code == 409, r.text
    assert "last scope" in r.json()["detail"]


@pytest.mark.asyncio
async def test_a_third_scope_gets_its_own_independent_ready_to_assign(client: AsyncClient):
    """The point of the whole change: pools are data, and a new one is real."""
    headers = await register_user(client)
    business = (
        await client.post("/api/scopes", json={"name": "Business"}, headers=headers)
    ).json()["id"]
    account = (
        await client.post(
            "/api/accounts",
            json={"name": "Business checking", "type": "checking", "scope_id": business},
            headers=headers,
        )
    ).json()["id"]
    await client.post(
        "/api/transactions",
        json={
            "account_id": account,
            "category_id": None,
            "date": "2026-04-02",
            "payee": "Client",
            "memo": "",
            "amount_cents": 120_000,
        },
        headers=headers,
    )

    body = (await client.get("/api/budget/2026-04", headers=headers)).json()

    rta = {row["scope_id"]: row["ready_to_assign_cents"] for row in body["ready_to_assign"]}
    scopes = await scope_ids(client, headers)
    assert rta[business] == 120_000
    assert rta[scopes[PERSONAL]] == 0
    assert rta[scopes[FAMILY]] == 0


@pytest.mark.asyncio
async def test_insights_reports_a_section_for_every_scope(client: AsyncClient):
    headers = await register_user(client)
    await client.post("/api/scopes", json={"name": "Business"}, headers=headers)

    body = (
        await client.get(
            "/api/insights?start_month=2026-04&end_month=2026-04", headers=headers
        )
    ).json()

    expected = [s["id"] for s in (await client.get("/api/scopes", headers=headers)).json()]
    assert [row["scope_id"] for row in body["breakdown"]["scopes"]] == expected
    assert [row["scope_id"] for row in body["income_vs_spending"]] == expected
    assert [row["scope_id"] for row in body["overspending"]["scopes"]] == expected
    assert [row["scope_id"] for row in body["breakdown"]["scope_split"]["scopes"]] == expected


@pytest.mark.asyncio
async def test_another_users_scope_is_invisible(client: AsyncClient):
    alice = await register_user(client, email="alice@example.com")
    mallory = await register_user(client, email="mallory@example.com")
    alice_family = await scope_id(client, alice, FAMILY)

    assert (
        await client.get("/api/scopes", headers=mallory)
    ).json() != (await client.get("/api/scopes", headers=alice)).json()
    assert (
        await client.patch(
            f"/api/scopes/{alice_family}", json={"name": "Stolen"}, headers=mallory
        )
    ).status_code == 404
    assert (
        await client.delete(f"/api/scopes/{alice_family}", headers=mallory)
    ).status_code == 404


@pytest.mark.asyncio
async def test_an_account_cannot_be_created_in_another_users_scope(client: AsyncClient):
    alice = await register_user(client, email="alice@example.com")
    mallory = await register_user(client, email="mallory@example.com")
    alice_family = await scope_id(client, alice, FAMILY)

    r = await client.post(
        "/api/accounts",
        json={"name": "Trojan", "type": "checking", "scope_id": alice_family},
        headers=mallory,
    )

    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_a_category_group_cannot_be_created_in_another_users_scope(
    client: AsyncClient,
):
    alice = await register_user(client, email="alice@example.com")
    mallory = await register_user(client, email="mallory@example.com")
    alice_family = await scope_id(client, alice, FAMILY)

    r = await client.post(
        "/api/category-groups",
        json={"name": "Trojan", "scope_id": alice_family},
        headers=mallory,
    )

    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_an_account_cannot_be_moved_into_another_users_scope(client: AsyncClient):
    alice = await register_user(client, email="alice@example.com")
    mallory = await register_user(client, email="mallory@example.com")
    alice_family = await scope_id(client, alice, FAMILY)
    account = await create_account(client, mallory)

    r = await client.patch(
        f"/api/accounts/{account}", json={"scope_id": alice_family}, headers=mallory
    )

    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_cross_scope_category_reassignment_names_the_scopes(client: AsyncClient):
    """The rejection reaches the user, so it must read as names, not ids."""
    headers = await register_user(client)
    personal_group = await create_group(client, headers, "Daily", scope=PERSONAL)
    family_group = await create_group(client, headers, "Joint", scope=FAMILY)
    groceries = await create_category(client, headers, personal_group, "Groceries")
    rent = await create_category(client, headers, family_group, "Rent")

    r = await client.delete(
        f"/api/categories/{groceries}", params={"reassign_to": rent}, headers=headers
    )

    assert r.status_code == 422, r.text
    assert PERSONAL in r.json()["detail"]
    assert FAMILY in r.json()["detail"]


@pytest.mark.asyncio
async def test_a_cross_scope_transaction_names_the_scopes(client: AsyncClient):
    headers = await register_user(client)
    account = await create_account(client, headers, "Personal checking", scope=PERSONAL)
    family_group = await create_group(client, headers, "Joint", scope=FAMILY)
    rent = await create_category(client, headers, family_group, "Rent")

    r = await client.post(
        "/api/transactions",
        json={
            "account_id": account,
            "category_id": rent,
            "date": "2026-04-05",
            "payee": "Landlord",
            "memo": "",
            "amount_cents": -90_000,
        },
        headers=headers,
    )

    assert r.status_code == 422, r.text
    assert PERSONAL in r.json()["detail"]
    assert FAMILY in r.json()["detail"]
