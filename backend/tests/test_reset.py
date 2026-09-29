"""Reset router: selectable wipes of transactions and assignments."""

import pytest
from httpx import AsyncClient

from tests.conftest import (
    create_account,
    create_category,
    create_group,
    list_transactions,
    mark_as_bank_imported,
    register_user,
    tombstoned_external_ids,
)

MONTH = "2026-07"


async def _add_transaction(client: AsyncClient, headers: dict, account_id: int) -> int:
    r = await client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "category_id": None,
            "date": "2026-07-01",
            "payee": "",
            "memo": "",
            "amount_cents": 5_000,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _assign(client: AsyncClient, headers: dict, category_id: int) -> None:
    r = await client.post(
        f"/api/budget/{MONTH}/assign",
        json={"category_id": category_id, "amount_cents": 2_500},
        headers=headers,
    )
    assert r.status_code == 204, r.text


async def _assigned_cents(client: AsyncClient, headers: dict, category_id: int) -> int:
    r = await client.get(f"/api/budget/{MONTH}", headers=headers)
    assert r.status_code == 200, r.text
    categories = [c for g in r.json()["groups"] for c in g["categories"]]
    return next(c["assigned_cents"] for c in categories if c["id"] == category_id)


@pytest.mark.asyncio
async def test_transactions_option_deletes_all_transactions_and_keeps_accounts(
    client: AsyncClient,
):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    await _add_transaction(client, headers, checking)
    await _add_transaction(client, headers, savings)

    r = await client.post("/api/reset", json={"options": ["transactions"]}, headers=headers)

    assert r.status_code == 200
    assert r.json()["deleted_transactions"] == 2
    assert await list_transactions(client, headers) == []
    accounts = (await client.get("/api/accounts", headers=headers)).json()
    assert [a["balance_cents"] for a in accounts] == [0, 0]


@pytest.mark.asyncio
async def test_transactions_option_leaves_assignments_untouched(client: AsyncClient):
    headers = await register_user(client)
    group = await create_group(client, headers)
    category = await create_category(client, headers, group)
    await _assign(client, headers, category)

    await client.post("/api/reset", json={"options": ["transactions"]}, headers=headers)

    assert await _assigned_cents(client, headers, category) == 2_500


@pytest.mark.asyncio
async def test_assignments_option_clears_assignments_but_keeps_categories_and_transactions(
    client: AsyncClient,
):
    headers = await register_user(client)
    account = await create_account(client, headers)
    await _add_transaction(client, headers, account)
    group = await create_group(client, headers)
    category = await create_category(client, headers, group)
    await _assign(client, headers, category)

    r = await client.post("/api/reset", json={"options": ["assignments"]}, headers=headers)

    assert r.status_code == 200
    assert r.json()["deleted_assignments"] == 1
    assert await _assigned_cents(client, headers, category) == 0
    assert len(await list_transactions(client, headers)) == 1


@pytest.mark.asyncio
async def test_both_options_can_be_applied_together(client: AsyncClient):
    headers = await register_user(client)
    account = await create_account(client, headers)
    await _add_transaction(client, headers, account)
    group = await create_group(client, headers)
    category = await create_category(client, headers, group)
    await _assign(client, headers, category)

    r = await client.post(
        "/api/reset", json={"options": ["transactions", "assignments"]}, headers=headers
    )

    assert r.json() == {"deleted_transactions": 1, "deleted_assignments": 1}


@pytest.mark.asyncio
async def test_reset_does_not_touch_other_users(client: AsyncClient):
    mine = await register_user(client, "me@example.com")
    theirs = await register_user(client, "them@example.com")
    their_account = await create_account(client, theirs)
    await _add_transaction(client, theirs, their_account)

    await client.post("/api/reset", json={"options": ["transactions"]}, headers=mine)

    assert len(await list_transactions(client, theirs)) == 1


@pytest.mark.asyncio
async def test_transactions_option_clears_tombstones_so_resync_can_reimport(
    client: AsyncClient,
):
    headers = await register_user(client)
    account = await create_account(client, headers)
    txn_id = await _add_transaction(client, headers, account)
    await mark_as_bank_imported(txn_id)
    await client.delete(f"/api/transactions/{txn_id}", headers=headers)
    assert await tombstoned_external_ids()

    await client.post("/api/reset", json={"options": ["transactions"]}, headers=headers)

    assert await tombstoned_external_ids() == set()


@pytest.mark.asyncio
async def test_reset_requires_at_least_one_option(client: AsyncClient):
    headers = await register_user(client)
    r = await client.post("/api/reset", json={"options": []}, headers=headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_reset_rejects_unknown_option(client: AsyncClient):
    headers = await register_user(client)
    r = await client.post("/api/reset", json={"options": ["everything"]}, headers=headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_reset_requires_authentication(client: AsyncClient):
    r = await client.post("/api/reset", json={"options": ["transactions"]})
    assert r.status_code == 401
