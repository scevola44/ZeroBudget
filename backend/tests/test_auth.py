"""Auth error paths and edge cases.

The happy path is covered by ``test_api_smoke.py``; these tests pin down what
happens when things go wrong.
"""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.db import get_db
from app.main import app
from app.models import RefreshToken
from app.security import create_access_token, hash_refresh_token
from tests.conftest import register_tokens, register_user


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


async def _refresh(client: AsyncClient, refresh_token: str):
    return await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})


async def _stored_tokens() -> list[RefreshToken]:
    async for session in app.dependency_overrides[get_db]():
        return list((await session.scalars(select(RefreshToken))).all())
    raise AssertionError("no session")


@pytest.mark.asyncio
async def test_register_and_login_return_refresh_token_and_expiry(client: AsyncClient):
    registered = await register_tokens(client, "tokens@example.com")
    assert registered["refresh_token"]
    assert registered["expires_in"] > 0

    r = await client.post(
        "/api/auth/login", json={"email": "tokens@example.com", "password": "supersecret"}
    )
    assert r.status_code == 200
    assert r.json()["refresh_token"] != registered["refresh_token"]


@pytest.mark.asyncio
async def test_refresh_returns_new_working_token_pair(client: AsyncClient):
    tokens = await register_tokens(client)

    r = await _refresh(client, tokens["refresh_token"])

    assert r.status_code == 200, r.text
    renewed = r.json()
    assert renewed["refresh_token"] != tokens["refresh_token"]
    me = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {renewed['access_token']}"}
    )
    assert me.status_code == 200


@pytest.mark.asyncio
async def test_rotated_refresh_token_cannot_be_reused(client: AsyncClient):
    tokens = await register_tokens(client)
    await _refresh(client, tokens["refresh_token"])

    r = await _refresh(client, tokens["refresh_token"])

    assert r.status_code == 401


@pytest.mark.asyncio
async def test_reusing_a_rotated_token_revokes_the_whole_family(client: AsyncClient):
    tokens = await register_tokens(client)
    newest = (await _refresh(client, tokens["refresh_token"])).json()

    await _refresh(client, tokens["refresh_token"])  # replay of the stale token

    assert (await _refresh(client, newest["refresh_token"])).status_code == 401


@pytest.mark.asyncio
async def test_reuse_detection_does_not_touch_other_sessions(client: AsyncClient):
    first = await register_tokens(client)
    login = await client.post(
        "/api/auth/login", json={"email": "user@example.com", "password": "supersecret"}
    )
    second = login.json()
    await _refresh(client, first["refresh_token"])
    await _refresh(client, first["refresh_token"])  # replay revokes first's family only

    assert (await _refresh(client, second["refresh_token"])).status_code == 200


@pytest.mark.asyncio
async def test_expired_refresh_token_is_rejected(client: AsyncClient):
    tokens = await register_tokens(client)
    async for session in app.dependency_overrides[get_db]():
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == hash_refresh_token(tokens["refresh_token"]))
            .values(expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
        )
        await session.commit()

    assert (await _refresh(client, tokens["refresh_token"])).status_code == 401


@pytest.mark.asyncio
async def test_unknown_refresh_token_is_rejected(client: AsyncClient):
    assert (await _refresh(client, "not-a-real-token")).status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_is_not_accepted_as_access_token(client: AsyncClient):
    tokens = await register_tokens(client)

    r = await client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )

    assert r.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_the_session(client: AsyncClient):
    tokens = await register_tokens(client)

    r = await client.post("/api/auth/logout", json={"refresh_token": tokens["refresh_token"]})

    assert r.status_code == 204
    assert (await _refresh(client, tokens["refresh_token"])).status_code == 401


@pytest.mark.asyncio
async def test_logout_with_unknown_token_is_a_no_op(client: AsyncClient):
    r = await client.post("/api/auth/logout", json={"refresh_token": "not-a-real-token"})

    assert r.status_code == 204


@pytest.mark.asyncio
async def test_refresh_tokens_are_stored_hashed(client: AsyncClient):
    tokens = await register_tokens(client)

    stored = await _stored_tokens()

    assert [row.token_hash for row in stored] == [hash_refresh_token(tokens["refresh_token"])]
    assert tokens["refresh_token"] not in {row.token_hash for row in stored}


@pytest.mark.asyncio
async def test_login_prunes_expired_refresh_tokens_for_that_user(client: AsyncClient):
    await register_tokens(client)
    async for session in app.dependency_overrides[get_db]():
        await session.execute(
            update(RefreshToken).values(expires_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
        )
        await session.commit()

    await client.post(
        "/api/auth/login", json={"email": "user@example.com", "password": "supersecret"}
    )

    assert len(await _stored_tokens()) == 1


@pytest.mark.asyncio
async def test_access_token_without_a_refresh_token_still_works(client: AsyncClient):
    """Sessions issued before refresh tokens existed must survive the upgrade."""
    await register_tokens(client)
    legacy_token = create_access_token(1)

    r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {legacy_token}"})

    assert r.status_code == 200
