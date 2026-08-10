"""Transfers: linked legs, pair consistency, and their effect on Ready to Assign.

A transfer is two linked transactions in different accounts, equal and
opposite, never categorized. Whether it moves Ready to Assign depends on the
two accounts' scopes — same scope is the pool's own money changing hands,
cross scope genuinely moves money between pools.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import create_account, create_category, create_group, register_user

TRANSFER_CENTS = 60_000
SALARY_CENTS = 100_000


async def _transfer(
    client: AsyncClient,
    headers: dict,
    from_account: int,
    to_account: int,
    *,
    amount_cents: int = TRANSFER_CENTS,
    date: str = "2026-04-02",
) -> dict:
    r = await client.post(
        "/api/transactions/transfer",
        json={
            "from_account_id": from_account,
            "to_account_id": to_account,
            "date": date,
            "payee": "Savings top-up",
            "memo": "",
            "amount_cents": amount_cents,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _add_inflow(
    client: AsyncClient, headers: dict, account_id: int, amount: int, date: str
) -> None:
    r = await client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "category_id": None,
            "date": date,
            "payee": "Salary",
            "memo": "",
            "amount_cents": amount,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text


async def _ready_to_assign(client: AsyncClient, headers: dict, month: str = "2026-04") -> tuple:
    body = (await client.get(f"/api/budget/{month}", headers=headers)).json()
    return body["personal_ready_to_assign_cents"], body["shared_ready_to_assign_cents"]


@pytest.mark.asyncio
async def test_transfer_creates_two_linked_uncategorized_legs(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")

    body = await _transfer(client, headers, checking, savings)
    outflow, inflow = body["from_transaction"], body["to_transaction"]

    assert outflow["amount_cents"] == -TRANSFER_CENTS
    assert inflow["amount_cents"] == TRANSFER_CENTS
    assert outflow["account_id"] == checking
    assert inflow["account_id"] == savings
    assert outflow["category_id"] is None and inflow["category_id"] is None
    assert outflow["transfer_peer_id"] == inflow["id"]
    assert inflow["transfer_peer_id"] == outflow["id"]


@pytest.mark.asyncio
async def test_transfer_between_same_account_is_rejected(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")

    r = await client.post(
        "/api/transactions/transfer",
        json={
            "from_account_id": checking,
            "to_account_id": checking,
            "date": "2026-04-02",
            "payee": "",
            "memo": "",
            "amount_cents": TRANSFER_CENTS,
        },
        headers=headers,
    )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_editing_amount_mirrors_to_the_peer_leg(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    body = await _transfer(client, headers, checking, savings)
    outflow_id, inflow_id = body["from_transaction"]["id"], body["to_transaction"]["id"]

    r = await client.patch(
        f"/api/transactions/{outflow_id}",
        json={"amount_cents": -25_000},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    rows = (await client.get("/api/transactions", headers=headers)).json()
    by_id = {t["id"]: t for t in rows}
    assert by_id[outflow_id]["amount_cents"] == -25_000
    assert by_id[inflow_id]["amount_cents"] == 25_000


@pytest.mark.asyncio
async def test_editing_date_mirrors_to_the_peer_leg(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    body = await _transfer(client, headers, checking, savings)
    inflow_id, outflow_id = body["to_transaction"]["id"], body["from_transaction"]["id"]

    r = await client.patch(
        f"/api/transactions/{inflow_id}", json={"date": "2026-04-15"}, headers=headers
    )
    assert r.status_code == 200, r.text

    rows = (await client.get("/api/transactions", headers=headers)).json()
    by_id = {t["id"]: t for t in rows}
    assert by_id[inflow_id]["date"] == "2026-04-15"
    assert by_id[outflow_id]["date"] == "2026-04-15"


@pytest.mark.asyncio
async def test_payee_and_memo_stay_on_the_edited_leg(client: AsyncClient):
    """Date and amount define the transfer; payee and memo annotate one side."""
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    body = await _transfer(client, headers, checking, savings)
    outflow_id, inflow_id = body["from_transaction"]["id"], body["to_transaction"]["id"]

    r = await client.patch(
        f"/api/transactions/{outflow_id}",
        json={"memo": "moved for the deposit"},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    rows = (await client.get("/api/transactions", headers=headers)).json()
    by_id = {t["id"]: t for t in rows}
    assert by_id[outflow_id]["memo"] == "moved for the deposit"
    assert by_id[inflow_id]["memo"] == ""


@pytest.mark.asyncio
async def test_categorizing_a_transfer_leg_is_rejected(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    group = await create_group(client, headers, "Bills")
    rent = await create_category(client, headers, group, "Rent")
    body = await _transfer(client, headers, checking, savings)

    r = await client.patch(
        f"/api/transactions/{body['from_transaction']['id']}",
        json={"category_id": rent},
        headers=headers,
    )
    assert r.status_code == 422, r.text
    assert "transfer" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_deleting_one_leg_removes_the_pair(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    body = await _transfer(client, headers, checking, savings)

    r = await client.delete(
        f"/api/transactions/{body['from_transaction']['id']}", headers=headers
    )
    assert r.status_code == 204, r.text

    rows = (await client.get("/api/transactions", headers=headers)).json()
    assert rows == []


@pytest.mark.asyncio
async def test_same_scope_transfer_leaves_both_pools_untouched(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking", scope="personal")
    savings = await create_account(client, headers, "Savings", scope="personal")
    await _add_inflow(client, headers, checking, SALARY_CENTS, "2026-04-01")

    before = await _ready_to_assign(client, headers)
    await _transfer(client, headers, checking, savings)
    after = await _ready_to_assign(client, headers)

    assert before == (SALARY_CENTS, 0)
    assert after == before


@pytest.mark.asyncio
async def test_cross_scope_transfer_moves_exactly_the_amount(client: AsyncClient):
    headers = await register_user(client)
    personal = await create_account(client, headers, "Personal", scope="personal")
    joint = await create_account(client, headers, "Joint", scope="shared")
    await _add_inflow(client, headers, personal, SALARY_CENTS, "2026-04-01")

    await _transfer(client, headers, personal, joint)

    personal_rta, shared_rta = await _ready_to_assign(client, headers)
    assert personal_rta == SALARY_CENTS - TRANSFER_CENTS
    assert shared_rta == TRANSFER_CENTS


@pytest.mark.asyncio
async def test_deleting_a_cross_scope_transfer_restores_both_pools(client: AsyncClient):
    headers = await register_user(client)
    personal = await create_account(client, headers, "Personal", scope="personal")
    joint = await create_account(client, headers, "Joint", scope="shared")
    await _add_inflow(client, headers, personal, SALARY_CENTS, "2026-04-01")
    body = await _transfer(client, headers, personal, joint)

    r = await client.delete(
        f"/api/transactions/{body['to_transaction']['id']}", headers=headers
    )
    assert r.status_code == 204, r.text

    assert await _ready_to_assign(client, headers) == (SALARY_CENTS, 0)
