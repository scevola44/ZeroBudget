"""Async client for the Enable Banking API.

Every Enable Banking specific — JWT claims, endpoint paths, payload field
names — lives in this one module, so any discrepancy discovered against the
live API is a one-file fix. Tests override the ``get_banking_client``
dependency with a fake and never import the network paths here.

API model (differs from Plaid):
- App auth: short-lived RS256 JWT minted from the application's private key.
- User auth: redirect-based PSD2 consent — ``POST /auth`` returns a bank URL,
  the bank redirects back with a ``code``, ``POST /sessions`` turns the code
  into a long-lived session (up to 90/180 days depending on the bank).
- No delta sync: transactions are re-fetched over a date window, paginated
  via ``continuation_key``.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
import jwt

from app.config import Settings, get_settings

# EB JWTs may live up to 24h; one hour is plenty for our request pattern and
# keeps the blast radius of a leaked token small.
_JWT_TTL_SECONDS = 3600
# Re-mint when the cached JWT has less than this long to live.
_JWT_REFRESH_MARGIN_SECONDS = 60
_ASPSP_CACHE_TTL = timedelta(hours=24)
_REQUEST_TIMEOUT_SECONDS = 30.0
# How long a consent we ask the bank for. Banks cap this (90 or 180 days
# under PSD2); EB clamps to the ASPSP's maximum.
CONSENT_VALIDITY_DAYS = 180


class BankingError(RuntimeError):
    """Structured wrapper around Enable Banking API errors so routers can map to HTTP."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _to_error(response: httpx.Response) -> BankingError:
    try:
        body = response.json()
        detail = body.get("message") or body.get("detail") or response.text
    except ValueError:
        detail = response.text
    if response.status_code in (401, 403):
        # Expired/revoked PSD2 consent surfaces as 401/403 on data endpoints.
        return BankingError("SESSION_EXPIRED", f"Bank session rejected: {detail}")
    if response.status_code == 429:
        return BankingError("RATE_LIMITED", f"Enable Banking rate limit hit: {detail}")
    return BankingError(
        "BANKING_API_ERROR",
        f"Enable Banking API error {response.status_code}: {detail}",
    )


class BankingClient:
    """High-level Enable Banking calls, async-friendly."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        if not self._settings.enable_banking_app_id or not (
            self._settings.enable_banking_private_key_path
            or self._settings.enable_banking_private_key
        ):
            raise BankingError(
                "BANKING_NOT_CONFIGURED",
                "Enable Banking credentials are not configured "
                "(ENABLE_BANKING_APP_ID / ENABLE_BANKING_PRIVATE_KEY[_PATH]).",
            )
        self._http = httpx.AsyncClient(
            base_url=self._settings.enable_banking_api_base,
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
        self._jwt: str = ""
        self._jwt_expires_at: float = 0.0
        self._aspsp_cache: list[dict[str, Any]] | None = None
        self._aspsp_cache_at: datetime | None = None

    def _mint_jwt(self) -> str:
        now = int(time.time())
        if self._jwt and now < self._jwt_expires_at - _JWT_REFRESH_MARGIN_SECONDS:
            return self._jwt
        self._jwt = jwt.encode(
            {
                "iss": "enablebanking.com",
                "aud": "api.enablebanking.com",
                "iat": now,
                "exp": now + _JWT_TTL_SECONDS,
            },
            self._settings.enable_banking_private_key_pem,
            algorithm="RS256",
            headers={"kid": self._settings.enable_banking_app_id},
        )
        self._jwt_expires_at = now + _JWT_TTL_SECONDS
        return self._jwt

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = await self._http.request(
                method,
                path,
                json=json,
                params=params,
                headers={"Authorization": f"Bearer {self._mint_jwt()}"},
            )
        except httpx.HTTPError as exc:
            raise BankingError("BANKING_UNREACHABLE", f"Enable Banking request failed: {exc}") from exc
        if response.status_code >= 400:
            raise _to_error(response)
        return response.json()

    async def list_aspsps(self, countries: list[str]) -> list[dict[str, Any]]:
        """Banks available for linking, filtered to the configured countries.

        Cached in-memory for 24h — the list is near-static and every call
        counts against the free-tier quota.
        """
        now = datetime.now(timezone.utc)
        if (
            self._aspsp_cache is None
            or self._aspsp_cache_at is None
            or now - self._aspsp_cache_at > _ASPSP_CACHE_TTL
        ):
            body = await self._request("GET", "/aspsps")
            self._aspsp_cache = body.get("aspsps", [])
            self._aspsp_cache_at = now
        wanted = set(countries)
        return [a for a in self._aspsp_cache if a.get("country") in wanted]

    async def start_auth(
        self,
        aspsp_name: str,
        aspsp_country: str,
        state: str,
        redirect_url: str,
    ) -> str:
        """Begin the bank authorization; returns the URL to send the user to."""
        valid_until = datetime.now(timezone.utc) + timedelta(days=CONSENT_VALIDITY_DAYS)
        body = await self._request(
            "POST",
            "/auth",
            json={
                "access": {"valid_until": valid_until.isoformat()},
                "aspsp": {"name": aspsp_name, "country": aspsp_country},
                "state": state,
                "redirect_url": redirect_url,
                "psu_type": "personal",
            },
        )
        return body["url"]

    async def create_session(self, code: str) -> dict[str, Any]:
        """Exchange the redirect ``code`` for a session.

        Returns the raw session body: ``session_id``, ``accounts`` (list of
        account objects with ``uid``, ``account_id.iban``, ``currency``,
        ``product``...), and ``access.valid_until``.
        """
        return await self._request("POST", "/sessions", json={"code": code})

    async def get_session(self, session_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/sessions/{session_id}")

    async def delete_session(self, session_id: str) -> None:
        await self._request("DELETE", f"/sessions/{session_id}")

    async def get_transactions(
        self, account_uid: str, date_from: date
    ) -> list[dict[str, Any]]:
        """All transactions since ``date_from``, following pagination."""
        transactions: list[dict[str, Any]] = []
        continuation_key: str | None = None
        while True:
            params: dict[str, Any] = {"date_from": date_from.isoformat()}
            if continuation_key:
                params["continuation_key"] = continuation_key
            body = await self._request(
                "GET", f"/accounts/{account_uid}/transactions", params=params
            )
            transactions.extend(body.get("transactions", []))
            continuation_key = body.get("continuation_key")
            if not continuation_key:
                break
        return transactions

    async def get_balances(self, account_uid: str) -> list[dict[str, Any]]:
        """Raw balance entries for an account (Berlin Group ``balance_type``s)."""
        body = await self._request("GET", f"/accounts/{account_uid}/balances")
        return body.get("balances", [])

    async def aclose(self) -> None:
        await self._http.aclose()


_client: BankingClient | None = None


def get_banking_client() -> BankingClient:
    """FastAPI dependency. Lazily instantiated + cached per process."""
    global _client
    if _client is None:
        _client = BankingClient()
    return _client
