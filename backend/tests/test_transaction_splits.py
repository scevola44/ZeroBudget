"""Split transactions: creation, validation, and interaction with deletes,
category deletion/reassignment, transfer matching, and the unassigned count.
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
)


async def _create(
    client: AsyncClient,
    headers: dict,
    *,
    account_id: int,
    date: str = "2026-04-01",
    amount: int = -1000,
    category_id: int | None = None,
    splits: list[dict] | None = None,
    is_ready_to_assign: bool = False,
):
    body = {
        "account_id": account_id,
        "category_id": category_id,
        "is_ready_to_assign": is_ready_to_assign,
        "date": date,
        "payee": "",
        "memo": "",
        "amount_cents": amount,
    }
    if splits is not None:
        body["splits"] = splits
    return await client.post("/api/transactions", json=body, headers=headers)


async def _add_txn(client: AsyncClient, headers: dict, **kwargs) -> dict:
    r = await _create(client, headers, **kwargs)
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_create_transaction_with_splits_stores_all_lines(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    groceries = await create_category(client, headers, g, "Groceries")
    rent = await create_category(client, headers, g, "Rent")

    txn = await _add_txn(
        client,
        headers,
        account_id=a,
        amount=-1000,
        splits=[
            {"category_id": groceries, "amount_cents": -400, "memo": "food"},
            {"category_id": rent, "amount_cents": -600, "memo": "rent"},
        ],
    )

    assert txn["category_id"] is None
    assert len(txn["splits"]) == 2
    assert {s["category_id"] for s in txn["splits"]} == {groceries, rent}
    assert sum(s["amount_cents"] for s in txn["splits"]) == -1000


@pytest.mark.asyncio
async def test_create_rejects_splits_that_dont_sum_to_amount(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    c1 = await create_category(client, headers, g, "A")
    c2 = await create_category(client, headers, g, "B")

    r = await _create(
        client,
        headers,
        account_id=a,
        amount=-1000,
        splits=[
            {"category_id": c1, "amount_cents": -400},
            {"category_id": c2, "amount_cents": -500},
        ],
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_rejects_single_line_split(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    c1 = await create_category(client, headers, g, "A")

    r = await _create(
        client, headers, account_id=a, amount=-1000, splits=[{"category_id": c1, "amount_cents": -1000}]
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_rejects_top_level_category_alongside_splits(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    c1 = await create_category(client, headers, g, "A")
    c2 = await create_category(client, headers, g, "B")

    r = await _create(
        client,
        headers,
        account_id=a,
        amount=-1000,
        category_id=c1,
        splits=[
            {"category_id": c1, "amount_cents": -500},
            {"category_id": c2, "amount_cents": -500},
        ],
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_rejects_ready_to_assign_alongside_splits(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    c1 = await create_category(client, headers, g, "A")
    c2 = await create_category(client, headers, g, "B")

    r = await _create(
        client,
        headers,
        account_id=a,
        amount=1000,
        is_ready_to_assign=True,
        splits=[
            {"category_id": c1, "amount_cents": 500},
            {"category_id": c2, "amount_cents": 500},
        ],
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_rejects_split_line_category_outside_account_scope(client: AsyncClient):
    headers = await register_user(client)
    personal_account = await create_account(client, headers, "Checking", scope=PERSONAL)
    shared_group = await create_group(client, headers, "Bills", scope=FAMILY)
    shared_category = await create_category(client, headers, shared_group, "Rent")
    personal_group = await create_group(client, headers, "Fun", scope=PERSONAL)
    personal_category = await create_category(client, headers, personal_group, "Games")

    r = await _create(
        client,
        headers,
        account_id=personal_account,
        amount=-1000,
        splits=[
            {"category_id": personal_category, "amount_cents": -500},
            {"category_id": shared_category, "amount_cents": -500},
        ],
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_update_replaces_splits_wholesale(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    c1 = await create_category(client, headers, g, "A")
    c2 = await create_category(client, headers, g, "B")
    c3 = await create_category(client, headers, g, "C")

    txn = await _add_txn(
        client,
        headers,
        account_id=a,
        amount=-1000,
        splits=[
            {"category_id": c1, "amount_cents": -400},
            {"category_id": c2, "amount_cents": -600},
        ],
    )

    r = await client.patch(
        f"/api/transactions/{txn['id']}",
        json={
            "date": "2026-04-01",
            "payee": "",
            "memo": "",
            "amount_cents": -1000,
            "splits": [
                {"category_id": c3, "amount_cents": -1000},
            ],
        },
        headers=headers,
    )
    # A single-line replacement is still a split with < 2 lines — rejected.
    assert r.status_code == 422

    r = await client.patch(
        f"/api/transactions/{txn['id']}",
        json={
            "date": "2026-04-01",
            "payee": "",
            "memo": "",
            "amount_cents": -1000,
            "splits": [
                {"category_id": c3, "amount_cents": -300},
                {"category_id": c1, "amount_cents": -700},
            ],
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["splits"]) == 2
    assert {s["category_id"] for s in body["splits"]} == {c3, c1}


@pytest.mark.asyncio
async def test_update_clearing_splits_reverts_to_plain_category(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    c1 = await create_category(client, headers, g, "A")
    c2 = await create_category(client, headers, g, "B")

    txn = await _add_txn(
        client,
        headers,
        account_id=a,
        amount=-1000,
        splits=[
            {"category_id": c1, "amount_cents": -400},
            {"category_id": c2, "amount_cents": -600},
        ],
    )

    r = await client.patch(
        f"/api/transactions/{txn['id']}",
        json={
            "date": "2026-04-01",
            "payee": "",
            "memo": "",
            "amount_cents": -1000,
            "category_id": c1,
            "splits": [],
        },
        headers=headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["splits"] == []
    assert body["category_id"] == c1


@pytest.mark.asyncio
async def test_update_rejects_splitting_a_transfer_leg(client: AsyncClient):
    headers = await register_user(client)
    a1 = await create_account(client, headers, "Checking")
    a2 = await create_account(client, headers, "Savings")
    g = await create_group(client, headers)
    c1 = await create_category(client, headers, g, "A")
    c2 = await create_category(client, headers, g, "B")

    r = await client.post(
        "/api/transactions/transfer",
        json={
            "from_account_id": a1,
            "to_account_id": a2,
            "date": "2026-04-01",
            "payee": "",
            "memo": "",
            "amount_cents": 1000,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    leg_id = r.json()["from_transaction"]["id"]

    r = await client.patch(
        f"/api/transactions/{leg_id}",
        json={
            "date": "2026-04-01",
            "payee": "",
            "memo": "",
            "amount_cents": -1000,
            "splits": [
                {"category_id": c1, "amount_cents": -500},
                {"category_id": c2, "amount_cents": -500},
            ],
        },
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_deleting_transaction_cascades_delete_of_its_splits(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    c1 = await create_category(client, headers, g, "A")
    c2 = await create_category(client, headers, g, "B")

    txn = await _add_txn(
        client,
        headers,
        account_id=a,
        amount=-1000,
        splits=[
            {"category_id": c1, "amount_cents": -400},
            {"category_id": c2, "amount_cents": -600},
        ],
    )

    r = await client.delete(f"/api/transactions/{txn['id']}", headers=headers)
    assert r.status_code == 204

    r = await client.get("/api/transactions", headers=headers)
    assert r.json()["items"] == []


@pytest.mark.asyncio
async def test_deleting_category_without_reassign_nulls_split_lines_referencing_it(
    client: AsyncClient,
):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    doomed = await create_category(client, headers, g, "Doomed")
    survivor = await create_category(client, headers, g, "Survivor")

    txn = await _add_txn(
        client,
        headers,
        account_id=a,
        amount=-1000,
        splits=[
            {"category_id": doomed, "amount_cents": -400},
            {"category_id": survivor, "amount_cents": -600},
        ],
    )

    r = await client.delete(f"/api/categories/{doomed}", headers=headers)
    assert r.status_code == 204

    r = await client.get("/api/transactions", headers=headers)
    [row] = r.json()["items"]
    assert row["id"] == txn["id"]
    by_category = {s["category_id"]: s["amount_cents"] for s in row["splits"]}
    assert by_category[None] == -400
    assert by_category[survivor] == -600


@pytest.mark.asyncio
async def test_deleting_category_with_reassign_updates_split_lines_too(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    old = await create_category(client, headers, g, "Old")
    new = await create_category(client, headers, g, "New")
    other = await create_category(client, headers, g, "Other")

    txn = await _add_txn(
        client,
        headers,
        account_id=a,
        amount=-1000,
        splits=[
            {"category_id": old, "amount_cents": -400},
            {"category_id": other, "amount_cents": -600},
        ],
    )

    r = await client.delete(
        f"/api/categories/{old}", params={"reassign_to": new}, headers=headers
    )
    assert r.status_code == 204

    r = await client.get("/api/transactions", headers=headers)
    [row] = r.json()["items"]
    assert row["id"] == txn["id"]
    by_category = {s["category_id"]: s["amount_cents"] for s in row["splits"]}
    assert by_category[new] == -400
    assert by_category[other] == -600


@pytest.mark.asyncio
async def test_transfer_candidates_exclude_split_transactions(client: AsyncClient):
    headers = await register_user(client)
    a1 = await create_account(client, headers, "Checking")
    a2 = await create_account(client, headers, "Savings")
    g = await create_group(client, headers)
    c1 = await create_category(client, headers, g, "A")
    c2 = await create_category(client, headers, g, "B")

    # An unsplit row that would otherwise be a perfect transfer candidate.
    outflow = await _add_txn(client, headers, account_id=a1, amount=-1000)

    # A split transaction with the same equal-and-opposite amount, in the
    # other account — must never be offered as a candidate.
    await _add_txn(
        client,
        headers,
        account_id=a2,
        amount=1000,
        splits=[
            {"category_id": c1, "amount_cents": 400},
            {"category_id": c2, "amount_cents": 600},
        ],
    )

    r = await client.get(
        "/api/transactions/transfer-candidates",
        params={"transaction_id": outflow["id"]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json() == []


@pytest.mark.asyncio
async def test_unassigned_count_ignores_fully_categorized_split_transactions(
    client: AsyncClient,
):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    c1 = await create_category(client, headers, g, "A")
    c2 = await create_category(client, headers, g, "B")

    await _add_txn(
        client,
        headers,
        account_id=a,
        amount=-1000,
        splits=[
            {"category_id": c1, "amount_cents": -400},
            {"category_id": c2, "amount_cents": -600},
        ],
    )

    r = await client.get("/api/transactions/unassigned-count", headers=headers)
    assert r.json()["count"] == 0


@pytest.mark.asyncio
async def test_unassigned_count_includes_split_transactions_with_a_null_line(
    client: AsyncClient,
):
    headers = await register_user(client)
    a = await create_account(client, headers)
    g = await create_group(client, headers)
    c1 = await create_category(client, headers, g, "A")

    await _add_txn(
        client,
        headers,
        account_id=a,
        amount=-1000,
        splits=[
            {"category_id": c1, "amount_cents": -400},
            {"category_id": None, "amount_cents": -600},
        ],
    )

    r = await client.get("/api/transactions/unassigned-count", headers=headers)
    assert r.json()["count"] == 1
