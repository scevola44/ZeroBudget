"""Payees router: autocomplete, rename, merge, and resolve-on-write."""

import pytest
from httpx import AsyncClient

from tests.conftest import create_account, register_user


async def _add_txn(
    client: AsyncClient,
    headers: dict,
    *,
    account_id: int,
    date: str,
    amount: int = -100,
    payee: str = "",
) -> dict:
    r = await client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "date": date,
            "amount_cents": amount,
            "payee": payee,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _payees(client: AsyncClient, headers: dict, q: str = "") -> list[dict]:
    r = await client.get("/api/payees", params={"q": q} if q else {}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_create_transaction_creates_new_payee_when_unseen(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)

    txn = await _add_txn(client, headers, account_id=a, date="2026-04-01", payee="Amazon")

    assert txn["payee"] == "Amazon"
    payees = await _payees(client, headers)
    assert [p["name"] for p in payees] == ["Amazon"]


@pytest.mark.asyncio
async def test_create_transaction_resolves_payee_text_to_existing_payee_case_insensitively(
    client: AsyncClient,
):
    headers = await register_user(client)
    a = await create_account(client, headers)

    await _add_txn(client, headers, account_id=a, date="2026-04-01", payee="Amazon")
    await _add_txn(client, headers, account_id=a, date="2026-04-02", payee="amazon")
    await _add_txn(client, headers, account_id=a, date="2026-04-03", payee="AMAZON")

    payees = await _payees(client, headers)
    assert len(payees) == 1


@pytest.mark.asyncio
async def test_blank_payee_creates_no_payee_row(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)

    txn = await _add_txn(client, headers, account_id=a, date="2026-04-01", payee="")

    assert txn["payee"] == ""
    assert txn["payee_id"] is None
    assert await _payees(client, headers) == []


@pytest.mark.asyncio
async def test_rename_is_instant_and_touches_no_transaction_rows(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    txn = await _add_txn(client, headers, account_id=a, date="2026-04-01", payee="Amazn")
    [payee] = await _payees(client, headers)

    r = await client.patch(
        f"/api/payees/{payee['id']}", json={"name": "Amazon"}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Amazon"

    r = await client.get("/api/transactions", headers=headers)
    [row] = r.json()["items"]
    assert row["id"] == txn["id"]
    assert row["payee"] == "Amazon"
    assert row["payee_id"] == payee["id"]


@pytest.mark.asyncio
async def test_rename_rejects_case_insensitive_collision_with_another_payee(
    client: AsyncClient,
):
    headers = await register_user(client)
    a = await create_account(client, headers)
    await _add_txn(client, headers, account_id=a, date="2026-04-01", payee="Amazon")
    await _add_txn(client, headers, account_id=a, date="2026-04-02", payee="Netflix")
    payees = {p["name"]: p["id"] for p in await _payees(client, headers)}

    r = await client.patch(
        f"/api/payees/{payees['Netflix']}", json={"name": "amazon"}, headers=headers
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_rename_rejects_blank_name(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    await _add_txn(client, headers, account_id=a, date="2026-04-01", payee="Amazon")
    [payee] = await _payees(client, headers)

    r = await client.patch(f"/api/payees/{payee['id']}", json={"name": "  "}, headers=headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_merge_reassigns_transactions_and_deletes_source_payee(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    t1 = await _add_txn(client, headers, account_id=a, date="2026-04-01", payee="Amazon")
    t2 = await _add_txn(client, headers, account_id=a, date="2026-04-02", payee="AMZN Mktp")
    t3 = await _add_txn(client, headers, account_id=a, date="2026-04-03", payee="Amazon")
    payees = {p["name"]: p["id"] for p in await _payees(client, headers)}

    r = await client.post(
        f"/api/payees/{payees['Amazon']}/merge",
        json={"source_ids": [payees["AMZN Mktp"]]},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["reassigned"] == 1

    remaining = await _payees(client, headers)
    assert [p["name"] for p in remaining] == ["Amazon"]

    r = await client.get("/api/transactions", headers=headers)
    by_id = {row["id"]: row for row in r.json()["items"]}
    assert by_id[t1["id"]]["payee"] == "Amazon"
    assert by_id[t2["id"]]["payee"] == "Amazon"
    assert by_id[t3["id"]]["payee"] == "Amazon"


@pytest.mark.asyncio
async def test_merge_rejects_target_in_source_ids(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    await _add_txn(client, headers, account_id=a, date="2026-04-01", payee="Amazon")
    [payee] = await _payees(client, headers)

    r = await client.post(
        f"/api/payees/{payee['id']}/merge",
        json={"source_ids": [payee["id"]]},
        headers=headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_autocomplete_matches_prefix_most_recently_used_first(client: AsyncClient):
    headers = await register_user(client)
    a = await create_account(client, headers)
    await _add_txn(client, headers, account_id=a, date="2026-01-01", payee="Store Old")
    await _add_txn(client, headers, account_id=a, date="2026-06-01", payee="Store New")

    payees = await _payees(client, headers, q="Store")
    assert [p["name"] for p in payees] == ["Store New", "Store Old"]

    assert await _payees(client, headers, q="Nope") == []


@pytest.mark.asyncio
async def test_payees_are_scoped_to_the_current_user(client: AsyncClient):
    headers_a = await register_user(client, email="a@example.com")
    headers_b = await register_user(client, email="b@example.com")
    account_a = await create_account(client, headers_a)
    account_b = await create_account(client, headers_b)

    await _add_txn(client, headers_a, account_id=account_a, date="2026-04-01", payee="Shared Name")
    await _add_txn(client, headers_b, account_id=account_b, date="2026-04-01", payee="Shared Name")

    payees_a = await _payees(client, headers_a)
    payees_b = await _payees(client, headers_b)
    assert len(payees_a) == 1
    assert len(payees_b) == 1
    assert payees_a[0]["id"] != payees_b[0]["id"]

    r = await client.patch(
        f"/api/payees/{payees_b[0]['id']}", json={"name": "Renamed"}, headers=headers_a
    )
    assert r.status_code == 404
