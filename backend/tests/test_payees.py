"""Payees router: list, rename, merge; and payee_id resolution on write."""

import pytest
from httpx import AsyncClient

from tests.conftest import create_account, register_user
from tests.test_transactions import _add_txn


@pytest.mark.asyncio
async def test_creating_a_transaction_resolves_a_payee(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    txn_id = await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=1000, payee="Aldi")

    r = await client.get("/api/payees", headers=headers)
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert names == ["Aldi"]

    txn = (await client.get("/api/transactions", headers=headers)).json()["items"][0]
    assert txn["id"] == txn_id
    assert txn["payee_id"] == r.json()[0]["id"]


@pytest.mark.asyncio
async def test_same_payee_typed_twice_resolves_to_one_row(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=1000, payee="Aldi")
    await _add_txn(client, headers, account_id=a, date="2026-04-02", amount=2000, payee="aldi")

    r = await client.get("/api/payees", headers=headers)
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_blank_payee_is_not_resolved(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=1000, payee="")

    r = await client.get("/api/payees", headers=headers)
    assert r.json() == []
    txn = (await client.get("/api/transactions", headers=headers)).json()["items"][0]
    assert txn["payee_id"] is None


@pytest.mark.asyncio
async def test_editing_payee_reresolves_it(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    txn_id = await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=1000, payee="Aldi")

    r = await client.patch(
        f"/api/transactions/{txn_id}", json={"payee": "Lidl"}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["payee"] == "Lidl"

    payees = (await client.get("/api/payees", headers=headers)).json()
    assert sorted(p["name"] for p in payees) == ["Aldi", "Lidl"]


@pytest.mark.asyncio
async def test_rename_payee_updates_all_its_transactions(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=1000, payee="Aldi")
    await _add_txn(client, headers, account_id=a, date="2026-04-02", amount=2000, payee="Aldi")

    payee_id = (await client.get("/api/payees", headers=headers)).json()[0]["id"]
    r = await client.patch(
        f"/api/payees/{payee_id}", json={"name": "Aldi Süd"}, headers=headers
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Aldi Süd"

    txns = (await client.get("/api/transactions", headers=headers)).json()["items"]
    assert all(t["payee"] == "Aldi Süd" for t in txns)


@pytest.mark.asyncio
async def test_rename_to_an_existing_name_is_rejected(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=1000, payee="Aldi")
    await _add_txn(client, headers, account_id=a, date="2026-04-02", amount=2000, payee="Lidl")

    payees = {p["name"]: p["id"] for p in (await client.get("/api/payees", headers=headers)).json()}
    r = await client.patch(
        f"/api/payees/{payees['Aldi']}", json={"name": "Lidl"}, headers=headers
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_merge_payees_reassigns_transactions_and_deletes_source(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=1000, payee="Aldi")
    await _add_txn(client, headers, account_id=a, date="2026-04-02", amount=2000, payee="Aldi Sued")

    payees = {p["name"]: p["id"] for p in (await client.get("/api/payees", headers=headers)).json()}
    r = await client.post(
        "/api/payees/merge",
        json={"source_id": payees["Aldi Sued"], "target_id": payees["Aldi"]},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["merged_count"] == 1

    remaining = (await client.get("/api/payees", headers=headers)).json()
    assert [p["name"] for p in remaining] == ["Aldi"]
    txns = (await client.get("/api/transactions", headers=headers)).json()["items"]
    assert all(t["payee"] == "Aldi" and t["payee_id"] == payees["Aldi"] for t in txns)


@pytest.mark.asyncio
async def test_merge_into_itself_is_rejected(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    await _add_txn(client, headers, account_id=a, date="2026-04-01", amount=1000, payee="Aldi")
    payee_id = (await client.get("/api/payees", headers=headers)).json()[0]["id"]

    r = await client.post(
        "/api/payees/merge",
        json={"source_id": payee_id, "target_id": payee_id},
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_cannot_rename_or_merge_other_users_payee(client: AsyncClient):
    alice = await register_user(client, "alice@example.com")
    bob = await register_user(client, "bob@example.com")
    a = await create_account(client, alice)
    await _add_txn(client, alice, account_id=a, date="2026-04-01", amount=1000, payee="Aldi")
    alice_payee = (await client.get("/api/payees", headers=alice)).json()[0]["id"]

    r = await client.patch(f"/api/payees/{alice_payee}", json={"name": "Hijacked"}, headers=bob)
    assert r.status_code == 404

    r = await client.post(
        "/api/payees/merge",
        json={"source_id": alice_payee, "target_id": alice_payee},
        headers=bob,
    )
    assert r.status_code in (404, 422)


@pytest.mark.asyncio
async def test_synthetic_payees_are_not_resolved(client: AsyncClient):
    """Balance-adjustment transactions never surface in the payee list."""
    headers = await register_user(client)
    a = await create_account(client, headers)
    r = await client.post(
        f"/api/accounts/{a}/balance", json={"balance_cents": 5000}, headers=headers
    )
    assert r.status_code == 200

    payees = (await client.get("/api/payees", headers=headers)).json()
    assert payees == []
