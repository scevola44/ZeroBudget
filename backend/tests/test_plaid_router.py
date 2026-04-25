"""HTTP-level tests for the Plaid router.

The ``PlaidClient`` is swapped for a fake via FastAPI's
``dependency_overrides`` so no real Plaid calls are made.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from httpx import AsyncClient

from app.main import app
from app.services.plaid_client import ExchangeResult, SyncResult, get_plaid_client
from tests.conftest import register_user


@dataclass
class FakePlaidClient:
    link_token: str = "link-sandbox-abc"
    exchange: ExchangeResult = field(
        default_factory=lambda: ExchangeResult(
            access_token="access-sandbox-xyz", item_id="item_123"
        )
    )
    accounts: list[dict[str, Any]] = field(default_factory=list)
    institution_name: str | None = "Sandbox Bank"
    sync_result: SyncResult = field(
        default_factory=lambda: SyncResult(
            added=[], modified=[], removed=[], next_cursor="cursor_v1"
        )
    )
    removed_calls: list[str] = field(default_factory=list)

    async def create_link_token(self, user_id: int) -> str:
        return self.link_token

    async def exchange_public_token(self, public_token: str) -> ExchangeResult:
        return self.exchange

    async def get_accounts(self, access_token: str) -> list[dict[str, Any]]:
        return self.accounts

    async def get_institution_name(self, access_token: str) -> str | None:
        return self.institution_name

    async def sync_transactions(self, access_token: str, cursor: str | None) -> SyncResult:
        return self.sync_result

    async def remove_item(self, access_token: str) -> None:
        self.removed_calls.append(access_token)


def _eur_account(
    plaid_id: str = "pa_1", name: str = "Checking", mask: str = "1234", subtype: str = "checking"
) -> dict[str, Any]:
    return {
        "account_id": plaid_id,
        "name": name,
        "official_name": f"Official {name}",
        "mask": mask,
        "type": "depository",
        "subtype": subtype,
        "balances": {
            "iso_currency_code": "EUR",
            "unofficial_currency_code": None,
            "current": 1000.00,
        },
    }


def _usd_account(plaid_id: str = "pa_usd") -> dict[str, Any]:
    return {
        "account_id": plaid_id,
        "name": "USD Savings",
        "official_name": "USD Savings",
        "mask": "9999",
        "type": "depository",
        "subtype": "savings",
        "balances": {
            "iso_currency_code": "USD",
            "unofficial_currency_code": None,
            "current": 500.00,
        },
    }


def _install_fake(fake: FakePlaidClient) -> None:
    app.dependency_overrides[get_plaid_client] = lambda: fake


def _clear_fake() -> None:
    app.dependency_overrides.pop(get_plaid_client, None)


@pytest.mark.asyncio
async def test_link_token_endpoint_returns_token(client: AsyncClient):
    headers = await register_user(client)
    _install_fake(FakePlaidClient(link_token="link-xyz"))
    try:
        r = await client.post("/api/plaid/link-token", headers=headers)
        assert r.status_code == 200
        assert r.json() == {"link_token": "link-xyz"}
    finally:
        _clear_fake()


@pytest.mark.asyncio
async def test_exchange_creates_item_and_eur_accounts(client: AsyncClient):
    headers = await register_user(client)
    fake = FakePlaidClient(accounts=[_eur_account("pa_a", "Current", "1111")])
    _install_fake(fake)
    try:
        r = await client.post(
            "/api/plaid/exchange", json={"public_token": "pt"}, headers=headers
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["skipped_accounts"] == []
        assert len(body["account_ids"]) == 1
        assert body["item"]["institution_name"] == "Sandbox Bank"
        # Account created and visible via /api/accounts.
        accounts = (await client.get("/api/accounts", headers=headers)).json()
        assert len(accounts) == 1
        assert accounts[0]["plaid_mask"] == "1111"
        assert accounts[0]["institution_name"] == "Sandbox Bank"
    finally:
        _clear_fake()


@pytest.mark.asyncio
async def test_exchange_skips_non_eur_and_keeps_eur(client: AsyncClient):
    headers = await register_user(client)
    fake = FakePlaidClient(
        accounts=[_eur_account("pa_eur", "EUR acc"), _usd_account("pa_usd")]
    )
    _install_fake(fake)
    try:
        r = await client.post(
            "/api/plaid/exchange", json={"public_token": "pt"}, headers=headers
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert len(body["account_ids"]) == 1
        assert len(body["skipped_accounts"]) == 1
        assert body["skipped_accounts"][0]["plaid_account_id"] == "pa_usd"
    finally:
        _clear_fake()


@pytest.mark.asyncio
async def test_exchange_rejects_when_all_accounts_non_eur(client: AsyncClient):
    headers = await register_user(client)
    fake = FakePlaidClient(accounts=[_usd_account("pa_usd")])
    _install_fake(fake)
    try:
        r = await client.post(
            "/api/plaid/exchange", json={"public_token": "pt"}, headers=headers
        )
        assert r.status_code == 400
        # Plaid item should have been removed server-side to avoid leaking
        # a useless access token.
        assert fake.removed_calls == ["access-sandbox-xyz"]
        # No account or item was persisted.
        accounts = (await client.get("/api/accounts", headers=headers)).json()
        assert accounts == []
    finally:
        _clear_fake()


@pytest.mark.asyncio
async def test_sync_rate_limit_blocks_rapid_retry(client: AsyncClient):
    headers = await register_user(client)
    fake = FakePlaidClient(accounts=[_eur_account()])
    _install_fake(fake)
    try:
        exchange_resp = await client.post(
            "/api/plaid/exchange", json={"public_token": "pt"}, headers=headers
        )
        item_id = exchange_resp.json()["item"]["id"]
        # A manual sync immediately after link should be rate-limited, since
        # the exchange already ran the first sync and set last_synced_at.
        r = await client.post(
            f"/api/plaid/items/{item_id}/sync", headers=headers
        )
        assert r.status_code == 429
    finally:
        _clear_fake()


@pytest.mark.asyncio
async def test_unlink_cascades_accounts_and_transactions(client: AsyncClient):
    headers = await register_user(client)
    # Include one EUR transaction in the first sync so there's data to cascade.
    fake = FakePlaidClient(
        accounts=[_eur_account("pa_a", "Current", "1111")],
        sync_result=SyncResult(
            added=[
                {
                    "transaction_id": "tx_1",
                    "account_id": "pa_a",
                    "amount": 12.34,
                    "name": "coffee",
                    "merchant_name": "coffee",
                    "date": "2026-04-01",
                    "iso_currency_code": "EUR",
                    "unofficial_currency_code": None,
                    "pending": False,
                }
            ],
            modified=[],
            removed=[],
            next_cursor="c",
        ),
    )
    _install_fake(fake)
    try:
        exchange_resp = await client.post(
            "/api/plaid/exchange", json={"public_token": "pt"}, headers=headers
        )
        item_id = exchange_resp.json()["item"]["id"]
        assert exchange_resp.json()["sync"]["added"] == 1

        # Sanity: account + transaction exist.
        accounts = (await client.get("/api/accounts", headers=headers)).json()
        assert len(accounts) == 1
        txns = (
            await client.get("/api/transactions", headers=headers)
        ).json()
        assert len(txns) == 1

        r = await client.delete(f"/api/plaid/items/{item_id}", headers=headers)
        assert r.status_code == 204

        accounts_after = (await client.get("/api/accounts", headers=headers)).json()
        txns_after = (await client.get("/api/transactions", headers=headers)).json()
        assert accounts_after == []
        assert txns_after == []
    finally:
        _clear_fake()


@pytest.mark.asyncio
async def test_cannot_touch_other_users_item(client: AsyncClient):
    alice = await register_user(client, "alice@example.com")
    bob = await register_user(client, "bob@example.com")
    fake = FakePlaidClient(accounts=[_eur_account()])
    _install_fake(fake)
    try:
        exchange_resp = await client.post(
            "/api/plaid/exchange", json={"public_token": "pt"}, headers=alice
        )
        item_id = exchange_resp.json()["item"]["id"]

        r = await client.post(
            f"/api/plaid/items/{item_id}/sync", headers=bob
        )
        assert r.status_code == 404

        r = await client.delete(f"/api/plaid/items/{item_id}", headers=bob)
        assert r.status_code == 404
    finally:
        _clear_fake()


@pytest.mark.asyncio
async def test_manual_account_delete_still_works(client: AsyncClient):
    """Regression guard: Plaid additions mustn't break manual account CRUD."""
    headers = await register_user(client)
    create = await client.post(
        "/api/accounts", json={"name": "Cash", "type": "cash"}, headers=headers
    )
    assert create.status_code == 201
    account_id = create.json()["id"]
    r = await client.delete(f"/api/accounts/{account_id}", headers=headers)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_linked_account_cannot_be_deleted_directly(client: AsyncClient):
    headers = await register_user(client)
    fake = FakePlaidClient(accounts=[_eur_account()])
    _install_fake(fake)
    try:
        exchange_resp = await client.post(
            "/api/plaid/exchange", json={"public_token": "pt"}, headers=headers
        )
        account_id = exchange_resp.json()["account_ids"][0]
        r = await client.delete(f"/api/accounts/{account_id}", headers=headers)
        assert r.status_code == 400
    finally:
        _clear_fake()
