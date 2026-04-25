"""Thin async wrapper around the (sync) plaid-python SDK.

Only the calls ZeroBudget actually makes are exposed. Each method runs the
underlying SDK call inside ``asyncio.to_thread`` so routers stay async.

Tests override the ``get_plaid_client`` dependency with a fake, so this
module is never imported there — it's safe for the SDK-heavy imports to
live at module top level.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from plaid import Environment
from plaid.api import plaid_api
from plaid.api_client import ApiClient
from plaid.configuration import Configuration
from plaid.exceptions import ApiException
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
from plaid.model.item_get_request import ItemGetRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.item_remove_request import ItemRemoveRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.transactions_sync_request import TransactionsSyncRequest

from app.config import Settings, get_settings


class PlaidError(RuntimeError):
    """Structured wrapper around Plaid API errors so routers can map to HTTP."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass
class ExchangeResult:
    access_token: str
    item_id: str


@dataclass
class SyncResult:
    added: list[dict[str, Any]]
    modified: list[dict[str, Any]]
    removed: list[dict[str, Any]]
    next_cursor: str


_ENVIRONMENTS = {
    "sandbox": Environment.Sandbox,
    "production": Environment.Production,
}


def _build_api(settings: Settings) -> plaid_api.PlaidApi:
    if not settings.plaid_client_id or not settings.plaid_secret:
        raise PlaidError(
            "PLAID_NOT_CONFIGURED",
            "Plaid credentials are not configured (PLAID_CLIENT_ID / PLAID_SECRET).",
        )
    env = _ENVIRONMENTS.get(settings.plaid_env.lower())
    if env is None:
        raise PlaidError(
            "PLAID_ENV_INVALID",
            f"PLAID_ENV must be one of {sorted(_ENVIRONMENTS)}, got {settings.plaid_env!r}.",
        )
    configuration = Configuration(
        host=env,
        api_key={
            "clientId": settings.plaid_client_id,
            "secret": settings.plaid_secret,
        },
    )
    return plaid_api.PlaidApi(ApiClient(configuration))


def _to_error(exc: ApiException) -> PlaidError:
    # Plaid returns a JSON body with error_code / error_message; the SDK puts
    # it on ``exc.body`` as a raw bytes/str. We extract defensively — if parse
    # fails, fall back to the SDK's string form.
    import json

    code = "PLAID_API_ERROR"
    message = str(exc)
    body = getattr(exc, "body", None)
    if body:
        try:
            parsed = json.loads(body)
            code = parsed.get("error_code") or code
            message = parsed.get("error_message") or message
        except (ValueError, TypeError):
            pass
    return PlaidError(code, message)


class PlaidClient:
    """High-level Plaid calls, async-friendly."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._api = _build_api(self._settings)

    async def create_link_token(self, user_id: int) -> str:
        request = LinkTokenCreateRequest(
            products=[Products(p) for p in self._settings.plaid_products_list],
            client_name="ZeroBudget",
            country_codes=[CountryCode(c) for c in self._settings.plaid_country_codes_list],
            language="en",
            user=LinkTokenCreateRequestUser(client_user_id=str(user_id)),
        )
        response = await self._call(self._api.link_token_create, request)
        return response["link_token"]

    async def exchange_public_token(self, public_token: str) -> ExchangeResult:
        request = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = await self._call(self._api.item_public_token_exchange, request)
        return ExchangeResult(
            access_token=response["access_token"], item_id=response["item_id"]
        )

    async def get_accounts(self, access_token: str) -> list[dict[str, Any]]:
        request = AccountsGetRequest(access_token=access_token)
        response = await self._call(self._api.accounts_get, request)
        return response["accounts"]

    async def get_institution_name(self, access_token: str) -> str | None:
        item_response = await self._call(
            self._api.item_get, ItemGetRequest(access_token=access_token)
        )
        institution_id = item_response["item"].get("institution_id")
        if not institution_id:
            return None
        inst_response = await self._call(
            self._api.institutions_get_by_id,
            InstitutionsGetByIdRequest(
                institution_id=institution_id,
                country_codes=[
                    CountryCode(c) for c in self._settings.plaid_country_codes_list
                ],
            ),
        )
        return inst_response["institution"].get("name")

    async def sync_transactions(self, access_token: str, cursor: str | None) -> SyncResult:
        """Walk every page of /transactions/sync and merge into a single result."""
        added: list[dict[str, Any]] = []
        modified: list[dict[str, Any]] = []
        removed: list[dict[str, Any]] = []
        current = cursor or ""
        while True:
            request = TransactionsSyncRequest(
                access_token=access_token,
                cursor=current,
            )
            response = await self._call(self._api.transactions_sync, request)
            added.extend(response["added"])
            modified.extend(response["modified"])
            removed.extend(response["removed"])
            current = response["next_cursor"]
            if not response["has_more"]:
                break
        return SyncResult(added=added, modified=modified, removed=removed, next_cursor=current)

    async def remove_item(self, access_token: str) -> None:
        await self._call(self._api.item_remove, ItemRemoveRequest(access_token=access_token))

    async def _call(self, fn: Any, request: Any) -> dict[str, Any]:
        def _run() -> dict[str, Any]:
            try:
                return fn(request).to_dict()
            except ApiException as exc:
                raise _to_error(exc) from exc

        return await asyncio.to_thread(_run)


_client: PlaidClient | None = None


def get_plaid_client() -> PlaidClient:
    """FastAPI dependency. Lazily instantiated + cached per process."""
    global _client
    if _client is None:
        _client = PlaidClient()
    return _client
