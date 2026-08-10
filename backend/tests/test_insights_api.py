"""Insights router: range validation, per-scope isolation, and reconciliation.

``test_insights_reconciles_with_the_budget_page_for_the_same_month`` is the
ROADMAP Phase 5 acceptance criterion — the numbers on the Insights page must be
the same numbers the Budget page shows for that month.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import create_account, create_category, create_group, register_user

APRIL = "2026-04"


async def _post_transaction(
    client: AsyncClient,
    headers: dict,
    account_id: int,
    amount_cents: int,
    date: str,
    category_id: int | None = None,
) -> None:
    r = await client.post(
        "/api/transactions",
        json={
            "account_id": account_id,
            "category_id": category_id,
            "date": date,
            "payee": "",
            "memo": "",
            "amount_cents": amount_cents,
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text


async def _assign(
    client: AsyncClient, headers: dict, month: str, category_id: int, amount_cents: int
) -> None:
    r = await client.post(
        f"/api/budget/{month}/assign",
        json={"category_id": category_id, "amount_cents": amount_cents},
        headers=headers,
    )
    assert r.status_code == 204, r.text


async def _get_insights(
    client: AsyncClient, headers: dict, start: str = APRIL, end: str = APRIL
):
    return await client.get(
        f"/api/insights?start_month={start}&end_month={end}", headers=headers
    )


@pytest.mark.asyncio
async def test_insights_require_authentication(client: AsyncClient):
    r = await client.get(f"/api/insights?start_month={APRIL}&end_month={APRIL}")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_empty_insights_report_zero_for_both_scopes(client: AsyncClient):
    headers = await register_user(client)

    body = (await _get_insights(client, headers)).json()

    assert body["period"]["start_month"] == APRIL
    assert body["period"]["month_count"] == 1
    assert body["breakdown"]["scope_split"]["total_spent_cents"] == 0
    for scope in ("personal", "shared"):
        assert body["breakdown"][scope]["total_spent_cents"] == 0
        assert body["income_vs_spending"][scope]["income_cents"] == 0
        assert body["overspending"][scope]["categories"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["2026-13", "not-a-month", "2026", "2026-04-01"])
async def test_malformed_months_are_400(client: AsyncClient, value: str):
    headers = await register_user(client)

    start = await _get_insights(client, headers, start=value)
    end = await _get_insights(client, headers, end=value)

    assert start.status_code == 400
    assert end.status_code == 400


@pytest.mark.asyncio
async def test_an_inverted_range_is_400(client: AsyncClient):
    headers = await register_user(client)

    r = await _get_insights(client, headers, start="2026-06", end="2026-04")

    assert r.status_code == 400


@pytest.mark.asyncio
async def test_an_excessively_long_range_is_400(client: AsyncClient):
    headers = await register_user(client)

    r = await _get_insights(client, headers, start="2000-01", end="2026-04")

    assert r.status_code == 400


@pytest.mark.asyncio
async def test_missing_range_parameters_are_422(client: AsyncClient):
    headers = await register_user(client)

    r = await client.get("/api/insights", headers=headers)

    assert r.status_code == 422


@pytest.mark.asyncio
async def test_period_reports_the_baseline_window_it_compared_against(
    client: AsyncClient,
):
    headers = await register_user(client)

    body = (await _get_insights(client, headers)).json()

    assert body["period"]["baseline_start_month"] == "2025-10"
    assert body["period"]["baseline_end_month"] == "2026-03"


@pytest.mark.asyncio
async def test_overspending_publishes_the_rule_it_selected_rows_by(
    client: AsyncClient,
):
    """The page states the rule in its footnote; it must read it, not guess it."""
    headers = await register_user(client)

    overspending = (await _get_insights(client, headers)).json()["overspending"]

    assert overspending["threshold_pct"] == 10.0
    assert overspending["min_notable_cents"] == 1_000
    assert overspending["min_baseline_months"] == 3


@pytest.mark.asyncio
async def test_a_trivial_dip_into_the_red_is_not_reported(client: AsyncClient):
    headers = await register_user(client)
    account = await create_account(client, headers)
    group = await create_group(client, headers)
    groceries = await create_category(client, headers, group, "Groceries")

    await _assign(client, headers, APRIL, groceries, 24_700)
    await _post_transaction(client, headers, account, -25_000, "2026-04-05", groceries)

    overspending = (await _get_insights(client, headers)).json()["overspending"][
        "personal"
    ]

    assert overspending["categories"] == []
    assert overspending["on_track_count"] == 1


@pytest.mark.asyncio
async def test_personal_and_family_spending_are_reported_separately(
    client: AsyncClient,
):
    headers = await register_user(client)
    personal_account = await create_account(client, headers, "Personal", scope="personal")
    joint_account = await create_account(client, headers, "Joint", scope="shared")
    personal_group = await create_group(client, headers, "Daily", scope="personal")
    family_group = await create_group(client, headers, "Household", scope="shared")
    groceries = await create_category(client, headers, personal_group, "Groceries")
    rent = await create_category(client, headers, family_group, "Rent")

    await _post_transaction(
        client, headers, personal_account, -40_000, "2026-04-05", groceries
    )
    await _post_transaction(client, headers, joint_account, -90_000, "2026-04-03", rent)

    body = (await _get_insights(client, headers)).json()

    assert body["breakdown"]["personal"]["total_spent_cents"] == 40_000
    assert body["breakdown"]["shared"]["total_spent_cents"] == 90_000
    assert body["breakdown"]["scope_split"] == {
        "personal_spent_cents": 40_000,
        "shared_spent_cents": 90_000,
        "total_spent_cents": 130_000,
    }
    assert [row["name"] for row in body["breakdown"]["personal"]["categories"]] == [
        "Groceries"
    ]


@pytest.mark.asyncio
async def test_rows_carry_category_and_group_names(client: AsyncClient):
    headers = await register_user(client)
    account = await create_account(client, headers)
    group = await create_group(client, headers, "Daily")
    groceries = await create_category(client, headers, group, "Groceries")

    await _post_transaction(client, headers, account, -40_000, "2026-04-05", groceries)

    body = (await _get_insights(client, headers)).json()

    category = body["breakdown"]["personal"]["categories"][0]
    assert category["name"] == "Groceries"
    assert category["group_name"] == "Daily"
    assert body["breakdown"]["personal"]["groups"][0] == {
        "group_id": group,
        "name": "Daily",
        "spent_cents": 40_000,
        "sort_index": 0,
    }


@pytest.mark.asyncio
async def test_uncategorized_outflow_is_in_the_scope_total_but_in_no_category(
    client: AsyncClient,
):
    headers = await register_user(client)
    account = await create_account(client, headers)

    await _post_transaction(client, headers, account, -5_000, "2026-04-06")

    body = (await _get_insights(client, headers)).json()

    assert body["breakdown"]["personal"]["uncategorized_spent_cents"] == 5_000
    assert body["breakdown"]["personal"]["total_spent_cents"] == 5_000
    assert body["breakdown"]["personal"]["categories"] == []


@pytest.mark.asyncio
async def test_income_is_uncategorized_inflow_and_spending_is_everything_else(
    client: AsyncClient,
):
    headers = await register_user(client)
    account = await create_account(client, headers)
    group = await create_group(client, headers)
    groceries = await create_category(client, headers, group, "Groceries")

    await _post_transaction(client, headers, account, 250_000, "2026-04-01")
    await _post_transaction(client, headers, account, -40_000, "2026-04-05", groceries)
    await _post_transaction(client, headers, account, 3_000, "2026-04-09", groceries)

    flow = (await _get_insights(client, headers)).json()["income_vs_spending"]["personal"]

    assert flow["income_cents"] == 250_000
    assert flow["spent_cents"] == 40_000
    assert flow["refund_cents"] == 3_000
    assert flow["net_cents"] == 213_000
    assert [month["month"] for month in flow["months"]] == [APRIL]


@pytest.mark.asyncio
async def test_every_month_of_a_multi_month_range_gets_a_flow_row(client: AsyncClient):
    headers = await register_user(client)

    flow = (
        await _get_insights(client, headers, start="2026-02", end="2026-04")
    ).json()["income_vs_spending"]["personal"]

    assert [month["month"] for month in flow["months"]] == [
        "2026-02",
        "2026-03",
        "2026-04",
    ]


@pytest.mark.asyncio
async def test_future_transactions_do_not_affect_the_range(client: AsyncClient):
    headers = await register_user(client)
    account = await create_account(client, headers)
    group = await create_group(client, headers)
    groceries = await create_category(client, headers, group, "Groceries")

    await _post_transaction(client, headers, account, -40_000, "2026-04-05", groceries)
    await _post_transaction(client, headers, account, -99_000, "2026-05-05", groceries)

    body = (await _get_insights(client, headers)).json()

    assert body["breakdown"]["personal"]["total_spent_cents"] == 40_000


@pytest.mark.asyncio
async def test_insights_only_see_the_requesting_users_data(client: AsyncClient):
    alice = await register_user(client, email="alice@example.com")
    bob = await register_user(client, email="bob@example.com")
    alice_account = await create_account(client, alice)
    alice_group = await create_group(client, alice)
    alice_groceries = await create_category(client, alice, alice_group, "Groceries")
    await _post_transaction(
        client, alice, alice_account, -40_000, "2026-04-05", alice_groceries
    )

    body = (await _get_insights(client, bob)).json()

    assert body["breakdown"]["scope_split"]["total_spent_cents"] == 0
    assert body["breakdown"]["personal"]["categories"] == []


@pytest.mark.asyncio
async def test_a_category_whose_available_went_negative_is_flagged(
    client: AsyncClient,
):
    headers = await register_user(client)
    account = await create_account(client, headers)
    group = await create_group(client, headers)
    groceries = await create_category(client, headers, group, "Groceries")

    await _assign(client, headers, APRIL, groceries, 10_000)
    await _post_transaction(client, headers, account, -25_000, "2026-04-05", groceries)

    overspending = (await _get_insights(client, headers)).json()["overspending"][
        "personal"
    ]

    assert len(overspending["categories"]) == 1
    row = overspending["categories"][0]
    assert row["name"] == "Groceries"
    assert row["worst_balance_cents"] == -15_000
    assert row["worst_balance_month"] == APRIL
    assert "available_negative" in row["flags"]
    assert overspending["on_track_count"] == 0


@pytest.mark.asyncio
async def test_a_healthy_category_is_counted_as_on_track_not_listed(
    client: AsyncClient,
):
    headers = await register_user(client)
    account = await create_account(client, headers)
    group = await create_group(client, headers)
    groceries = await create_category(client, headers, group, "Groceries")

    await _assign(client, headers, APRIL, groceries, 30_000)
    await _post_transaction(client, headers, account, -25_000, "2026-04-05", groceries)

    overspending = (await _get_insights(client, headers)).json()["overspending"][
        "personal"
    ]

    assert overspending["categories"] == []
    assert overspending["on_track_count"] == 1


@pytest.mark.asyncio
async def test_insights_reconciles_with_the_budget_page_for_the_same_month(
    client: AsyncClient,
):
    """ROADMAP Phase 5 acceptance criterion: category activity on the Budget page
    is the same money the Insights breakdown reports as spending."""
    headers = await register_user(client)
    personal_account = await create_account(client, headers, "Personal")
    joint_account = await create_account(client, headers, "Joint", scope="shared")
    personal_group = await create_group(client, headers, "Daily", scope="personal")
    family_group = await create_group(client, headers, "Household", scope="shared")
    groceries = await create_category(client, headers, personal_group, "Groceries")
    fun = await create_category(client, headers, personal_group, "Fun")
    rent = await create_category(client, headers, family_group, "Rent")

    await _post_transaction(
        client, headers, personal_account, -40_000, "2026-04-05", groceries
    )
    await _post_transaction(
        client, headers, personal_account, 4_000, "2026-04-11", groceries
    )
    await _post_transaction(client, headers, personal_account, -7_500, "2026-04-18", fun)
    await _post_transaction(client, headers, joint_account, -90_000, "2026-04-03", rent)
    await _post_transaction(client, headers, personal_account, -5_000, "2026-04-06")

    budget = (await client.get(f"/api/budget/{APRIL}", headers=headers)).json()
    insights = (await _get_insights(client, headers)).json()

    budget_activity = {
        category["id"]: category["activity_cents"]
        for group in budget["groups"]
        for category in group["categories"]
    }
    for scope in ("personal", "shared"):
        breakdown = insights["breakdown"][scope]
        for row in breakdown["categories"]:
            assert row["activity_cents"] == budget_activity[row["category_id"]]

        # The scope's whole categorized movement, both ways round.
        assert sum(
            budget_activity[row["category_id"]] for row in breakdown["categories"]
        ) == sum(
            row["refund_cents"] - row["spent_cents"] for row in breakdown["categories"]
        )
        assert breakdown["total_spent_cents"] == sum(
            row["spent_cents"] for row in breakdown["categories"]
        ) + breakdown["uncategorized_spent_cents"]

    assert insights["breakdown"]["personal"]["total_spent_cents"] == 52_500
    assert insights["breakdown"]["shared"]["total_spent_cents"] == 90_000
