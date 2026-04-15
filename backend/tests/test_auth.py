"""Auth error paths and edge cases.

The happy path is covered by ``test_api_smoke.py``; these tests pin down what
happens when things go wrong.
"""

import pytest
from httpx import AsyncClient

from tests.conftest import register_user


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(client: AsyncClient):
    await register_user(client, "dup@example.com")
    r = await client.post(
        "/api/auth/register",
        json={"email": "dup@example.com", "password": "supersecret"},
    )
    assert r.status_code == 409
    assert "already registered" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_rejects_short_password(client: AsyncClient):
    r = await client.post(
        "/api/auth/register",
        json={"email": "short@example.com", "password": "short"},
    )
    # Pydantic validation → 422.
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_register_rejects_invalid_email(client: AsyncClient):
    r = await client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "password": "supersecret"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    await register_user(client, "alice@example.com", "correct-password-1")
    r = await client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "wrong-password-9"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    r = await client.post(
        "/api/auth/login",
        json={"email": "ghost@example.com", "password": "supersecret"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_login_success_returns_usable_token(client: AsyncClient):
    await register_user(client, "alice@example.com", "supersecret")
    r = await client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "supersecret"},
    )
    assert r.status_code == 200
    token = r.json()["access_token"]

    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "alice@example.com"


@pytest.mark.asyncio
async def test_me_without_token(client: AsyncClient):
    r = await client.get("/api/auth/me")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_with_garbage_token(client: AsyncClient):
    r = await client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_with_token_for_deleted_user(client: AsyncClient):
    # Edge case: a token is valid but the user it points at no longer exists.
    # We simulate this by signing a token with a user id that was never created.
    from app.security import create_access_token

    token = create_access_token(user_id=99999)
    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
