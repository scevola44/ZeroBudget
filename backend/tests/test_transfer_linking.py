"""Linking two transactions that already exist into one transfer.

A bank sync fetches each account separately, so a real transfer arrives as two
unrelated uncategorized rows. Until they are linked they read as real income and
real spending; ``POST /transfer`` is no help because it creates *new* legs.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import (
    FAMILY,
    create_account,
    create_category,
    create_group,
    list_transactions,
    ready_to_assign,
    register_user,
)

TRANSFER_CENTS = 60_000
SALARY_CENTS = 100_000


async def _add_transaction(
    client: AsyncClient,
    headers: dict,
    account_id: int,
    amount_cents: int,
    *,
    date: str = "2026-04-02",
    payee: str = "Own transfer",
    category_id: int | None = None,
    is_ready_to_assign: bool = False,
) -> int:
    """Stand in for a bank-synced row: the API shape is identical."""
    r = await client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "is_ready_to_assign": is_ready_to_assign,
            "date": date,
            "payee": payee,
            "memo": "",
            "amount_cents": amount_cents,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _link(client: AsyncClient, headers: dict, txn_id: int, peer_id: int):
    return await client.post(
        f"/api/transactions/{txn_id}/transfer-link",
        json={"peer_transaction_id": peer_id},
        headers=headers,
    )


async def _rows_by_id(client: AsyncClient, headers: dict) -> dict:
    rows = await list_transactions(client, headers)
    return {row["id"]: row for row in rows}


async def _ready_to_assign(client: AsyncClient, headers: dict, month: str = "2026-04") -> tuple:
    body = (await client.get(f"/api/budget/{month}", headers=headers)).json()
    return (
        await ready_to_assign(client, headers, body),
        await ready_to_assign(client, headers, body, FAMILY),
    )


@pytest.mark.asyncio
async def test_linking_two_imported_rows_makes_them_a_transfer_pair(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    outflow = await _add_transaction(client, headers, checking, -TRANSFER_CENTS)
    inflow = await _add_transaction(client, headers, savings, TRANSFER_CENTS)

    r = await _link(client, headers, outflow, inflow)
    assert r.status_code == 200, r.text

    by_id = await _rows_by_id(client, headers)
    assert by_id[outflow]["transfer_peer_id"] == inflow
    assert by_id[inflow]["transfer_peer_id"] == outflow
    assert by_id[outflow]["transfer_peer_account_id"] == savings
    assert by_id[inflow]["transfer_peer_account_id"] == checking


@pytest.mark.asyncio
async def test_the_response_reports_the_outflow_as_the_from_leg(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    outflow = await _add_transaction(client, headers, checking, -TRANSFER_CENTS)
    inflow = await _add_transaction(client, headers, savings, TRANSFER_CENTS)

    # Linked from the inflow's side, so direction can't come from the URL.
    body = (await _link(client, headers, inflow, outflow)).json()

    assert body["from_transaction"]["id"] == outflow
    assert body["to_transaction"]["id"] == inflow


@pytest.mark.asyncio
async def test_linked_legs_keep_their_own_dates(client: AsyncClient):
    # Money leaves one bank on the 31st and lands at the other on the 2nd.
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    outflow = await _add_transaction(
        client, headers, checking, -TRANSFER_CENTS, date="2026-03-31"
    )
    inflow = await _add_transaction(
        client, headers, savings, TRANSFER_CENTS, date="2026-04-02"
    )

    assert (await _link(client, headers, outflow, inflow)).status_code == 200

    by_id = await _rows_by_id(client, headers)
    assert by_id[outflow]["date"] == "2026-03-31"
    assert by_id[inflow]["date"] == "2026-04-02"


@pytest.mark.asyncio
async def test_linking_clears_a_category_the_user_had_set(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    group = await create_group(client, headers, "Bills")
    category = await create_category(client, headers, group, "Rent")
    outflow = await _add_transaction(
        client, headers, checking, -TRANSFER_CENTS, category_id=category
    )
    inflow = await _add_transaction(client, headers, savings, TRANSFER_CENTS)

    assert (await _link(client, headers, outflow, inflow)).status_code == 200

    by_id = await _rows_by_id(client, headers)
    assert by_id[outflow]["category_id"] is None


@pytest.mark.asyncio
async def test_linking_clears_a_ready_to_assign_flag_the_user_had_set(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    outflow = await _add_transaction(
        client, headers, checking, -TRANSFER_CENTS, is_ready_to_assign=True
    )
    inflow = await _add_transaction(client, headers, savings, TRANSFER_CENTS)

    assert (await _link(client, headers, outflow, inflow)).status_code == 200

    by_id = await _rows_by_id(client, headers)
    assert by_id[outflow]["is_ready_to_assign"] is False


@pytest.mark.asyncio
async def test_linking_mismatched_amounts_is_rejected(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    outflow = await _add_transaction(client, headers, checking, -TRANSFER_CENTS)
    short = await _add_transaction(client, headers, savings, TRANSFER_CENTS - 50)

    r = await _link(client, headers, outflow, short)

    assert r.status_code == 422
    assert "equal and opposite" in r.json()["detail"]


@pytest.mark.asyncio
async def test_linking_two_rows_in_the_same_account_is_rejected(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    outflow = await _add_transaction(client, headers, checking, -TRANSFER_CENTS)
    inflow = await _add_transaction(client, headers, checking, TRANSFER_CENTS)

    assert (await _link(client, headers, outflow, inflow)).status_code == 422


@pytest.mark.asyncio
async def test_linking_a_row_to_itself_is_rejected(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    outflow = await _add_transaction(client, headers, checking, -TRANSFER_CENTS)

    assert (await _link(client, headers, outflow, outflow)).status_code == 422


@pytest.mark.asyncio
async def test_linking_a_row_that_is_already_a_transfer_leg_is_rejected(
    client: AsyncClient,
):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    joint = await create_account(client, headers, "Joint")
    outflow = await _add_transaction(client, headers, checking, -TRANSFER_CENTS)
    inflow = await _add_transaction(client, headers, savings, TRANSFER_CENTS)
    spare = await _add_transaction(client, headers, joint, TRANSFER_CENTS)
    assert (await _link(client, headers, outflow, inflow)).status_code == 200

    r = await _link(client, headers, outflow, spare)

    assert r.status_code == 409


@pytest.mark.asyncio
async def test_another_users_transaction_cannot_be_linked(client: AsyncClient):
    owner = await register_user(client, email="owner@example.com")
    checking = await create_account(client, owner, "Checking")
    outflow = await _add_transaction(client, owner, checking, -TRANSFER_CENTS)

    stranger = await register_user(client, email="stranger@example.com")
    their_savings = await create_account(client, stranger, "Savings")
    theirs = await _add_transaction(client, stranger, their_savings, TRANSFER_CENTS)

    assert (await _link(client, owner, outflow, theirs)).status_code == 404


@pytest.mark.asyncio
async def test_a_linked_pair_stops_moving_ready_to_assign(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    await _add_transaction(
        client, headers, checking, SALARY_CENTS, date="2026-04-01", payee="Salary"
    )
    outflow = await _add_transaction(client, headers, checking, -TRANSFER_CENTS)
    inflow = await _add_transaction(client, headers, savings, TRANSFER_CENTS)

    assert (await _link(client, headers, outflow, inflow)).status_code == 200

    assert await _ready_to_assign(client, headers) == (SALARY_CENTS, 0)


@pytest.mark.asyncio
async def test_a_linked_pair_split_across_months_leaves_both_months_intact(
    client: AsyncClient,
):
    # The legs no longer cancel each other out within one month, so excluding
    # them is what keeps March whole — the money never stopped being the user's.
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    await _add_transaction(
        client, headers, checking, SALARY_CENTS, date="2026-03-01", payee="Salary"
    )
    outflow = await _add_transaction(
        client, headers, checking, -TRANSFER_CENTS, date="2026-03-31"
    )
    inflow = await _add_transaction(
        client, headers, savings, TRANSFER_CENTS, date="2026-04-02"
    )

    assert (await _link(client, headers, outflow, inflow)).status_code == 200

    assert await _ready_to_assign(client, headers, "2026-03") == (SALARY_CENTS, 0)
    assert await _ready_to_assign(client, headers, "2026-04") == (SALARY_CENTS, 0)


@pytest.mark.asyncio
async def test_unlinking_keeps_both_transactions(client: AsyncClient):
    # Unlike DELETE, which drops the pair: these are real bank records.
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    outflow = await _add_transaction(client, headers, checking, -TRANSFER_CENTS)
    inflow = await _add_transaction(client, headers, savings, TRANSFER_CENTS)
    assert (await _link(client, headers, outflow, inflow)).status_code == 200

    r = await client.delete(
        f"/api/transactions/{outflow}/transfer-link", headers=headers
    )
    assert r.status_code == 204, r.text

    by_id = await _rows_by_id(client, headers)
    assert set(by_id) == {outflow, inflow}
    assert by_id[outflow]["transfer_peer_id"] is None
    assert by_id[inflow]["transfer_peer_id"] is None


@pytest.mark.asyncio
async def test_unlinking_a_row_that_is_not_a_transfer_is_rejected(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    plain = await _add_transaction(client, headers, checking, -TRANSFER_CENTS)

    r = await client.delete(f"/api/transactions/{plain}/transfer-link", headers=headers)

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_an_unlinked_pair_can_be_linked_again(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    outflow = await _add_transaction(client, headers, checking, -TRANSFER_CENTS)
    inflow = await _add_transaction(client, headers, savings, TRANSFER_CENTS)
    assert (await _link(client, headers, outflow, inflow)).status_code == 200
    await client.delete(f"/api/transactions/{outflow}/transfer-link", headers=headers)

    assert (await _link(client, headers, outflow, inflow)).status_code == 200


@pytest.mark.asyncio
async def test_candidates_offer_the_matching_row_in_the_other_account(
    client: AsyncClient,
):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    outflow = await _add_transaction(
        client, headers, checking, -TRANSFER_CENTS, date="2026-03-31"
    )
    inflow = await _add_transaction(
        client, headers, savings, TRANSFER_CENTS, date="2026-04-02"
    )
    await _add_transaction(client, headers, savings, 1_250, payee="Coffee")

    r = await client.get(
        f"/api/transactions/transfer-candidates?transaction_id={outflow}",
        headers=headers,
    )
    assert r.status_code == 200, r.text

    body = r.json()
    assert [c["transaction"]["id"] for c in body] == [inflow]
    assert body[0]["date_offset_days"] == 2


@pytest.mark.asyncio
async def test_candidates_can_be_narrowed_to_one_account(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    joint = await create_account(client, headers, "Joint")
    outflow = await _add_transaction(client, headers, checking, -TRANSFER_CENTS)
    await _add_transaction(client, headers, savings, TRANSFER_CENTS)
    in_joint = await _add_transaction(client, headers, joint, TRANSFER_CENTS)

    r = await client.get(
        f"/api/transactions/transfer-candidates?transaction_id={outflow}"
        f"&account_id={joint}",
        headers=headers,
    )

    assert [c["transaction"]["id"] for c in r.json()] == [in_joint]


@pytest.mark.asyncio
async def test_suggestions_surface_an_unlinked_pair(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    outflow = await _add_transaction(
        client, headers, checking, -TRANSFER_CENTS, date="2026-03-31"
    )
    inflow = await _add_transaction(
        client, headers, savings, TRANSFER_CENTS, date="2026-04-02"
    )

    r = await client.get(
        "/api/transactions/transfer-suggestions"
        "?start_date=2026-03-01&end_date=2026-04-30",
        headers=headers,
    )
    assert r.status_code == 200, r.text

    body = r.json()
    assert len(body) == 1
    assert body[0]["outflow"]["id"] == outflow
    assert body[0]["inflow"]["id"] == inflow


@pytest.mark.asyncio
async def test_a_linked_pair_stops_being_suggested(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    outflow = await _add_transaction(client, headers, checking, -TRANSFER_CENTS)
    inflow = await _add_transaction(client, headers, savings, TRANSFER_CENTS)
    assert (await _link(client, headers, outflow, inflow)).status_code == 200

    r = await client.get(
        "/api/transactions/transfer-suggestions"
        "?start_date=2026-03-01&end_date=2026-04-30",
        headers=headers,
    )

    assert r.json() == []


@pytest.mark.asyncio
async def test_linking_to_an_account_creates_the_missing_leg(client: AsyncClient):
    # Stands in for a manual savings account: a bank sync never writes anything
    # there, so there's nothing for transfer-candidates to ever find.
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    group = await create_group(client, headers, "Bills")
    category = await create_category(client, headers, group, "Rent")
    outflow = await _add_transaction(
        client,
        headers,
        checking,
        -TRANSFER_CENTS,
        date="2026-04-05",
        payee="To savings",
        category_id=category,
    )

    r = await client.post(
        f"/api/transactions/{outflow}/transfer-link",
        json={"to_account_id": savings},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    body = r.json()
    inflow = body["to_transaction"]["id"]
    assert body["from_transaction"]["id"] == outflow
    by_id = await _rows_by_id(client, headers)
    assert by_id[outflow]["transfer_peer_id"] == inflow
    assert by_id[outflow]["category_id"] is None
    assert by_id[inflow]["account_id"] == savings
    assert by_id[inflow]["amount_cents"] == TRANSFER_CENTS
    assert by_id[inflow]["date"] == "2026-04-05"
    assert by_id[inflow]["payee"] == "To savings"
    assert by_id[inflow]["category_id"] is None


@pytest.mark.asyncio
async def test_linking_to_an_account_works_even_when_that_account_is_synced(
    client: AsyncClient,
):
    # Creating the missing leg isn't restricted to unsynced targets — it's just
    # that unsynced targets are the case with no other way forward.
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    joint = await create_account(client, headers, "Joint")
    outflow = await _add_transaction(client, headers, checking, -TRANSFER_CENTS)

    r = await client.post(
        f"/api/transactions/{outflow}/transfer-link",
        json={"to_account_id": joint},
        headers=headers,
    )

    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_linking_with_neither_field_is_rejected(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    outflow = await _add_transaction(client, headers, checking, -TRANSFER_CENTS)

    r = await client.post(
        f"/api/transactions/{outflow}/transfer-link", json={}, headers=headers
    )

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_linking_with_both_fields_is_rejected(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    outflow = await _add_transaction(client, headers, checking, -TRANSFER_CENTS)
    inflow = await _add_transaction(client, headers, savings, TRANSFER_CENTS)

    r = await client.post(
        f"/api/transactions/{outflow}/transfer-link",
        json={"peer_transaction_id": inflow, "to_account_id": savings},
        headers=headers,
    )

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_creating_a_leg_in_another_users_account_is_rejected(client: AsyncClient):
    owner = await register_user(client, email="owner@example.com")
    checking = await create_account(client, owner, "Checking")
    outflow = await _add_transaction(client, owner, checking, -TRANSFER_CENTS)

    stranger = await register_user(client, email="stranger@example.com")
    their_savings = await create_account(client, stranger, "Savings")

    r = await client.post(
        f"/api/transactions/{outflow}/transfer-link",
        json={"to_account_id": their_savings},
        headers=owner,
    )

    assert r.status_code == 400


@pytest.mark.asyncio
async def test_payee_suggestions_offer_creating_the_missing_leg(client: AsyncClient):
    # Savings is never bank-synced, so nothing was ever going to write its half
    # of the transfer for the amount+date matcher to find.
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    outflow = await _add_transaction(
        client, headers, checking, -TRANSFER_CENTS, payee="To Savings"
    )

    r = await client.get(
        "/api/transactions/transfer-payee-suggestions"
        "?start_date=2026-03-01&end_date=2026-04-30",
        headers=headers,
    )
    assert r.status_code == 200, r.text

    body = r.json()
    assert len(body) == 1
    assert body[0]["transaction"]["id"] == outflow
    assert body[0]["to_account_id"] == savings
    assert body[0]["to_account_name"] == "Savings"


@pytest.mark.asyncio
async def test_payee_suggestions_ignore_a_merchant_that_merely_contains_the_account_name(
    client: AsyncClient,
):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    await create_account(client, headers, "Savings")
    await _add_transaction(
        client, headers, checking, -1_250, payee="Savings Superstore"
    )

    r = await client.get(
        "/api/transactions/transfer-payee-suggestions"
        "?start_date=2026-03-01&end_date=2026-04-30",
        headers=headers,
    )

    assert r.json() == []


@pytest.mark.asyncio
async def test_payee_suggestions_stop_once_the_row_is_linked(client: AsyncClient):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    outflow = await _add_transaction(
        client, headers, checking, -TRANSFER_CENTS, payee="To Savings"
    )
    assert (
        await client.post(
            f"/api/transactions/{outflow}/transfer-link",
            json={"to_account_id": savings},
            headers=headers,
        )
    ).status_code == 200

    r = await client.get(
        "/api/transactions/transfer-payee-suggestions"
        "?start_date=2026-03-01&end_date=2026-04-30",
        headers=headers,
    )

    assert r.json() == []


@pytest.mark.asyncio
async def test_suggestions_ignore_another_users_transactions(client: AsyncClient):
    stranger = await register_user(client, email="stranger@example.com")
    their_checking = await create_account(client, stranger, "Checking")
    await _add_transaction(client, stranger, their_checking, -TRANSFER_CENTS)

    headers = await register_user(client, email="owner@example.com")
    savings = await create_account(client, headers, "Savings")
    await _add_transaction(client, headers, savings, TRANSFER_CENTS)

    r = await client.get(
        "/api/transactions/transfer-suggestions"
        "?start_date=2026-03-01&end_date=2026-04-30",
        headers=headers,
    )

    assert r.json() == []
