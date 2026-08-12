"""HTTP-level tests for /api/banking with a fake Enable Banking client."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.config import get_settings
from app.services.banking_client import BankingError, get_banking_client
from app.main import app
from tests.conftest import register_user

MOCK_ASPSP = {"name": "Mock ASPSP", "country": "FI", "logo": None}

EUR_ACCOUNT = {
    "uid": "uid_1",
    "currency": "EUR",
    "product": "Current Account",
    "account_id": {"iban": "FI2112345600000785"},
}
USD_ACCOUNT = {
    "uid": "uid_usd",
    "currency": "USD",
    "product": "Dollar Account",
    "account_id": {"iban": "FI2112345600000786"},
}
XXX_ACCOUNT = {
    "uid": "uid_xxx",
    "currency": "XXX",
    "product": "PAYPAL_PREMIER_ACCOUNT",
    "account_id": {"iban": "FI2112345600000787"},
}

BOOKED_TXN = {
    "entry_reference": "ref-1",
    "transaction_amount": {"amount": "42.50", "currency": "EUR"},
    "credit_debit_indicator": "DBIT",
    "status": "BOOK",
    "booking_date": "2026-07-01",
    "creditor": {"name": "Coffee Shop"},
    "debtor": None,
    "remittance_information": [],
}


@dataclass
class FakeBankingClient:
    aspsps: list[dict[str, Any]] = field(default_factory=lambda: [MOCK_ASPSP])
    session: dict[str, Any] = field(default_factory=dict)
    transactions: list[dict[str, Any]] = field(default_factory=lambda: [BOOKED_TXN])
    balances: list[dict[str, Any]] = field(default_factory=list)
    create_session_error: BankingError | None = None
    deleted_sessions: list[str] = field(default_factory=list)
    get_balances_calls: list[str] = field(default_factory=list)

    async def list_aspsps(self, countries: list[str]) -> list[dict[str, Any]]:
        return [a for a in self.aspsps if a["country"] in countries]

    async def start_auth(
        self, aspsp_name: str, aspsp_country: str, state: str, redirect_url: str
    ) -> str:
        return f"https://mock.bank/auth?state={state}&redirect={redirect_url}"

    async def create_session(self, code: str) -> dict[str, Any]:
        if self.create_session_error is not None:
            raise self.create_session_error
        return self.session

    async def delete_session(self, session_id: str) -> None:
        self.deleted_sessions.append(session_id)

    async def get_transactions(self, account_uid: str, date_from: date) -> list[dict[str, Any]]:
        return self.transactions

    async def get_balances(self, account_uid: str) -> list[dict[str, Any]]:
        self.get_balances_calls.append(account_uid)
        return self.balances


def _session_body(accounts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    valid_until = (datetime.now(timezone.utc) + timedelta(days=180)).isoformat()
    return {
        "session_id": "sess-1",
        "accounts": accounts if accounts is not None else [EUR_ACCOUNT],
        "access": {"valid_until": valid_until},
    }


def _install_fake(fake: FakeBankingClient) -> None:
    app.dependency_overrides[get_banking_client] = lambda: fake


async def _connect(client, headers, fake: FakeBankingClient) -> dict[str, Any]:
    """Run the full connect flow and return the callback response body."""
    r = await client.post(
        "/api/banking/connections",
        json={"aspsp_name": "Mock ASPSP", "aspsp_country": "FI"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    state = r.json()["state"]
    r = await client.post(
        "/api/banking/connections/callback",
        json={"code": "auth-code-1", "state": state},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_list_aspsps(client):
    _install_fake(FakeBankingClient())
    headers = await register_user(client)
    r = await client.get("/api/banking/aspsps", headers=headers)
    assert r.status_code == 200
    assert r.json() == [{"name": "Mock ASPSP", "country": "FI", "logo": None}]


async def test_connect_and_callback_creates_connection_accounts_and_syncs(client):
    fake = FakeBankingClient(session=_session_body())
    _install_fake(fake)
    headers = await register_user(client)

    body = await _connect(client, headers, fake)
    assert body["connection"]["aspsp_name"] == "Mock ASPSP"
    assert len(body["account_ids"]) == 1
    assert body["skipped_accounts"] == []
    assert body["sync"]["added"] == 1

    r = await client.get("/api/banking/connections", headers=headers)
    assert len(r.json()) == 1

    r = await client.get("/api/accounts", headers=headers)
    accounts = r.json()
    assert len(accounts) == 1
    assert accounts[0]["institution_name"] == "Mock ASPSP"
    assert accounts[0]["bank_account_mask"] == "0785"
    assert accounts[0]["balance_cents"] == -4250


async def test_connect_with_shared_scope_creates_shared_accounts(client):
    fake = FakeBankingClient(session=_session_body())
    _install_fake(fake)
    headers = await register_user(client)

    r = await client.post(
        "/api/banking/connections",
        json={"aspsp_name": "Mock ASPSP", "aspsp_country": "FI", "scope": "shared"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    state = r.json()["state"]
    r = await client.post(
        "/api/banking/connections/callback",
        json={"code": "auth-code-1", "state": state},
        headers=headers,
    )
    assert r.status_code == 201, r.text

    r = await client.get("/api/accounts", headers=headers)
    accounts = r.json()
    assert len(accounts) == 1
    assert accounts[0]["scope"] == "shared"


async def test_callback_imports_opening_balance(client):
    fake = FakeBankingClient(
        session=_session_body(),
        balances=[
            {"balance_type": "CLBD", "balance_amount": {"amount": "1000.00", "currency": "EUR"}}
        ],
    )
    _install_fake(fake)
    headers = await register_user(client)

    await _connect(client, headers, fake)

    r = await client.get("/api/accounts", headers=headers)
    accounts = r.json()
    # Bank balance (100000) reconciled against the one imported transaction (-4250).
    assert accounts[0]["balance_cents"] == 100_000


async def test_callback_rejects_unknown_state(client):
    _install_fake(FakeBankingClient(session=_session_body()))
    headers = await register_user(client)
    r = await client.post(
        "/api/banking/connections/callback",
        json={"code": "auth-code-1", "state": "bogus"},
        headers=headers,
    )
    assert r.status_code == 400


async def test_callback_rejects_foreign_state(client):
    fake = FakeBankingClient(session=_session_body())
    _install_fake(fake)
    alice = await register_user(client, email="alice@example.com")
    mallory = await register_user(client, email="mallory@example.com")

    r = await client.post(
        "/api/banking/connections",
        json={"aspsp_name": "Mock ASPSP", "aspsp_country": "FI"},
        headers=alice,
    )
    state = r.json()["state"]

    r = await client.post(
        "/api/banking/connections/callback",
        json={"code": "auth-code-1", "state": state},
        headers=mallory,
    )
    assert r.status_code == 400


async def test_callback_rejects_bank_with_no_eur_accounts(client):
    fake = FakeBankingClient(session=_session_body(accounts=[USD_ACCOUNT]))
    _install_fake(fake)
    headers = await register_user(client)

    r = await client.post(
        "/api/banking/connections",
        json={"aspsp_name": "Mock ASPSP", "aspsp_country": "FI"},
        headers=headers,
    )
    state = r.json()["state"]
    r = await client.post(
        "/api/banking/connections/callback",
        json={"code": "auth-code-1", "state": state},
        headers=headers,
    )
    assert r.status_code == 400
    # The orphaned consent was revoked provider-side.
    assert fake.deleted_sessions == ["sess-1"]
    # USD is a confident non-EUR signal — no need to double-check the balance.
    assert fake.get_balances_calls == []


async def test_callback_accepts_xxx_currency_account_with_eur_balance(client):
    """PayPal-style accounts report "XXX" (ISO 4217 "no currency") at the account
    level even when their balance is EUR — fall back to the balance instead of
    rejecting outright."""
    fake = FakeBankingClient(
        session=_session_body(accounts=[XXX_ACCOUNT]),
        balances=[
            {"balance_type": "CLBD", "balance_amount": {"amount": "12.34", "currency": "EUR"}}
        ],
    )
    _install_fake(fake)
    headers = await register_user(client)

    body = await _connect(client, headers, fake)
    assert body["skipped_accounts"] == []
    assert len(body["account_ids"]) == 1
    # Called once for the connect-time currency fallback, once more for the
    # opening-balance import during the first sync.
    assert fake.get_balances_calls == ["uid_xxx", "uid_xxx"]


async def test_callback_rejects_xxx_currency_account_with_non_eur_balance(client):
    fake = FakeBankingClient(
        session=_session_body(accounts=[XXX_ACCOUNT]),
        balances=[
            {"balance_type": "CLBD", "balance_amount": {"amount": "12.34", "currency": "USD"}}
        ],
    )
    _install_fake(fake)
    headers = await register_user(client)

    r = await client.post(
        "/api/banking/connections",
        json={"aspsp_name": "Mock ASPSP", "aspsp_country": "FI"},
        headers=headers,
    )
    state = r.json()["state"]
    r = await client.post(
        "/api/banking/connections/callback",
        json={"code": "auth-code-1", "state": state},
        headers=headers,
    )
    assert r.status_code == 400
    assert fake.get_balances_calls == ["uid_xxx"]


async def test_callback_rejects_xxx_currency_account_with_no_balances(client):
    fake = FakeBankingClient(session=_session_body(accounts=[XXX_ACCOUNT]), balances=[])
    _install_fake(fake)
    headers = await register_user(client)

    r = await client.post(
        "/api/banking/connections",
        json={"aspsp_name": "Mock ASPSP", "aspsp_country": "FI"},
        headers=headers,
    )
    state = r.json()["state"]
    r = await client.post(
        "/api/banking/connections/callback",
        json={"code": "auth-code-1", "state": state},
        headers=headers,
    )
    assert r.status_code == 400


async def test_manual_sync_and_status(client):
    fake = FakeBankingClient(session=_session_body())
    _install_fake(fake)
    headers = await register_user(client)
    await _connect(client, headers, fake)

    r = await client.get("/api/banking/sync/status", headers=headers)
    status_body = r.json()
    assert status_body["mode"] == "manual"
    assert status_body["used_today"] == 1  # the link-time sync counted

    # The link sync just ran, so an immediate manual sync trips the cooldown.
    r = await client.post("/api/banking/sync", headers=headers)
    assert r.status_code == 429
    assert "ago" in r.json()["detail"]


async def test_manual_sync_runs_after_cooldown(client, monkeypatch):
    from app import routers

    fake = FakeBankingClient(session=_session_body())
    _install_fake(fake)
    headers = await register_user(client)
    await _connect(client, headers, fake)

    monkeypatch.setattr(routers.banking, "SYNC_COOLDOWN", timedelta(seconds=0))
    r = await client.post("/api/banking/sync", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert len(body["connections"]) == 1
    # Re-fetch of the same window adds nothing new.
    assert body["connections"][0]["added"] == 0
    assert body["quota"]["used_today"] == 2


async def test_manual_sync_respects_daily_quota(client, monkeypatch):
    fake = FakeBankingClient(session=_session_body())
    _install_fake(fake)
    headers = await register_user(client)
    await _connect(client, headers, fake)  # uses 1 run; default quota is small

    monkeypatch.setenv("SYNC_MAX_PER_DAY", "1")
    get_settings.cache_clear()
    try:
        r = await client.post("/api/banking/sync", headers=headers)
        assert r.status_code == 429
        assert "Daily sync limit" in r.json()["detail"]
    finally:
        monkeypatch.delenv("SYNC_MAX_PER_DAY")
        get_settings.cache_clear()


async def test_unlink_deletes_connection_and_accounts(client):
    fake = FakeBankingClient(session=_session_body())
    _install_fake(fake)
    headers = await register_user(client)
    body = await _connect(client, headers, fake)
    connection_id = body["connection"]["id"]

    r = await client.delete(f"/api/banking/connections/{connection_id}", headers=headers)
    assert r.status_code == 204
    assert fake.deleted_sessions == ["sess-1"]

    r = await client.get("/api/banking/connections", headers=headers)
    assert r.json() == []
    r = await client.get("/api/accounts", headers=headers)
    assert r.json() == []


async def test_unlink_rejects_foreign_connection(client):
    fake = FakeBankingClient(session=_session_body())
    _install_fake(fake)
    alice = await register_user(client, email="alice@example.com")
    mallory = await register_user(client, email="mallory@example.com")
    body = await _connect(client, alice, fake)
    connection_id = body["connection"]["id"]

    r = await client.delete(f"/api/banking/connections/{connection_id}", headers=mallory)
    assert r.status_code == 404
