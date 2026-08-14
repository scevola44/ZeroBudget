"""Pins the persisted ``transfer_match_candidates`` table against a fresh
from-scratch recompute, the same "two independent computations must agree"
pattern ``test_insights_calc.py`` uses to keep ``insights_calc`` and
``budget_calc`` from drifting apart.

``transfer_candidate_store.sync_candidates_for`` is maintained incrementally
at several write chokepoints (create, edit, link, unlink, delete). If any of
them forgot to call it, the persisted table would silently drift from what
``transfer_match``'s pure functions say the true candidate set is — these
tests would catch that by disagreeing, rather than by asserting a fixed
expected output that a bug could accidentally still satisfy.
"""

from datetime import date

import pytest
from httpx import AsyncClient

from app.services.transfer_match import MatchRow, find_candidates, suggest_pairs
from tests.conftest import (
    create_account,
    create_category,
    create_group,
    list_transactions,
    register_user,
)

TRANSFER_CENTS = 60_000


async def _add_transaction(
    client: AsyncClient,
    headers: dict,
    account_id: int,
    amount_cents: int,
    *,
    date: str = "2026-04-02",
    payee: str = "Own transfer",
    category_id: int | None = None,
) -> int:
    r = await client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "is_ready_to_assign": False,
            "date": date,
            "payee": payee,
            "memo": "",
            "amount_cents": amount_cents,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _to_match_row(row: dict) -> MatchRow:
    return MatchRow(
        id=row["id"],
        account_id=row["account_id"],
        category_id=row["category_id"],
        date=date.fromisoformat(row["date"]),
        amount_cents=row["amount_cents"],
        payee=row["payee"],
        transfer_peer_id=row["transfer_peer_id"],
    )


async def _all_match_rows(client: AsyncClient, headers: dict) -> list[MatchRow]:
    rows = await list_transactions(client, headers)
    return [_to_match_row(r) for r in rows]


async def _stored_candidate_ids(client: AsyncClient, headers: dict, transaction_id: int) -> set:
    r = await client.get(
        "/api/transactions/transfer-candidates",
        params={"transaction_id": transaction_id},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return {c["transaction"]["id"] for c in r.json()}


async def _stored_suggested_pairs(client: AsyncClient, headers: dict) -> set[tuple[int, int]]:
    r = await client.get(
        "/api/transactions/transfer-suggestions",
        params={"start_date": "2026-01-01", "end_date": "2026-12-31"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return {(s["outflow"]["id"], s["inflow"]["id"]) for s in r.json()}


@pytest.mark.asyncio
async def test_persisted_candidates_reconcile_with_a_fresh_recompute_across_every_write_path(
    client: AsyncClient,
):
    headers = await register_user(client)
    checking = await create_account(client, headers, "Checking")
    savings = await create_account(client, headers, "Savings")
    joint = await create_account(client, headers, "Joint")

    # A plain matching pair: create.
    pair_a_out = await _add_transaction(
        client, headers, checking, -TRANSFER_CENTS, date="2026-04-02"
    )
    pair_a_in = await _add_transaction(
        client, headers, savings, TRANSFER_CENTS, date="2026-04-03"
    )

    # A categorized leg: still a manual-link candidate, never an automatic
    # suggestion. Categorizing it after the fact must not leave a stale
    # candidate row behind for a category-blind lookup to miss.
    pair_b_out = await _add_transaction(client, headers, checking, -30_000, date="2026-04-05")
    pair_b_in = await _add_transaction(client, headers, savings, 30_000, date="2026-04-05")
    group_id = await create_group(client, headers)
    category_id = await create_category(client, headers, group_id)
    patch_r = await client.patch(
        f"/api/transactions/{pair_b_out}",
        json={"category_id": category_id},
        headers=headers,
    )
    assert patch_r.status_code == 200, patch_r.text

    # A pair that starts mismatched, then is edited into matching: PATCH.
    pair_c_out = await _add_transaction(client, headers, checking, -45_000, date="2026-04-10")
    pair_c_in = await _add_transaction(client, headers, joint, 40_000, date="2026-04-10")
    edit_r = await client.patch(
        f"/api/transactions/{pair_c_in}", json={"amount_cents": 45_000}, headers=headers
    )
    assert edit_r.status_code == 200, edit_r.text

    # A pair that's linked, then unlinked: link/unlink.
    pair_d_out = await _add_transaction(client, headers, checking, -20_000, date="2026-04-12")
    pair_d_in = await _add_transaction(client, headers, savings, 20_000, date="2026-04-12")
    link_r = await client.post(
        f"/api/transactions/{pair_d_out}/transfer-link",
        json={"peer_transaction_id": pair_d_in},
        headers=headers,
    )
    assert link_r.status_code == 200, link_r.text
    unlink_r = await client.delete(f"/api/transactions/{pair_d_out}/transfer-link", headers=headers)
    assert unlink_r.status_code == 204, unlink_r.text

    # A pair that would have matched, but one leg is deleted: delete.
    pair_e_out = await _add_transaction(client, headers, checking, -15_000, date="2026-04-15")
    pair_e_in = await _add_transaction(client, headers, savings, 15_000, date="2026-04-15")
    del_r = await client.delete(f"/api/transactions/{pair_e_in}", headers=headers)
    assert del_r.status_code == 204, del_r.text

    all_rows = await _all_match_rows(client, headers)
    by_id = {row.id: row for row in all_rows}

    # find_candidates reconciliation, for every transaction still linkable.
    for txn_id in (
        pair_a_out,
        pair_a_in,
        pair_b_out,
        pair_b_in,
        pair_c_out,
        pair_c_in,
        pair_d_out,
        pair_d_in,
        pair_e_out,
    ):
        target = by_id[txn_id]
        expected = {
            row.id for row in find_candidates(target, [r for r in all_rows if r.id != txn_id])
        }
        actual = await _stored_candidate_ids(client, headers, txn_id)
        assert actual == expected, f"transaction {txn_id}: {actual} != {expected}"

    # suggest_pairs reconciliation, over the whole visible ledger.
    expected_pairs = {
        (pair.outflow_id, pair.inflow_id) for pair in suggest_pairs(all_rows)
    }
    actual_pairs = await _stored_suggested_pairs(client, headers)
    assert actual_pairs == expected_pairs

    # Sanity: the scenario actually exercised what it claims to.
    assert (pair_a_out, pair_a_in) in actual_pairs
    assert (pair_c_out, pair_c_in) in actual_pairs
    # Unlinking restores the pair as a fresh candidate/suggestion, exactly as
    # if it had never been linked.
    assert (pair_d_out, pair_d_in) in actual_pairs
    assert pair_b_in in await _stored_candidate_ids(client, headers, pair_b_out)
    assert (pair_b_out, pair_b_in) not in actual_pairs
    assert await _stored_candidate_ids(client, headers, pair_e_out) == set()
