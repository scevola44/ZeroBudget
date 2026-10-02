"""The health check doubles as the identity probe for clients given only a URL."""

import pytest
from httpx import AsyncClient

from app.main import get_app_version


@pytest.mark.asyncio
async def test_health_identifies_the_server_as_zerobudget(client: AsyncClient):
    r = await client.get("/api/health")

    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "service": "zerobudget",
        "version": get_app_version(),
    }


@pytest.mark.asyncio
async def test_health_needs_no_authentication(client: AsyncClient):
    r = await client.get("/api/health", headers={"Authorization": "Bearer not-a-token"})

    assert r.status_code == 200
