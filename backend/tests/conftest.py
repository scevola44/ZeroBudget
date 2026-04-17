"""Shared pytest fixtures.

We spin up a fresh in-memory SQLite DB for each test and override FastAPI's
``get_db`` dependency to use it. This keeps the API smoke tests self-contained
and fast — no Postgres required.
"""

import os

# Force an in-memory SQLite URL before any app modules are imported. The
# connection is shared via ``StaticPool`` below so all sessions see the same DB.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["JWT_SECRET"] = "test-secret-long-enough-for-hs256-key-32bytes"
# Stable Fernet key so tests can round-trip encrypted values across sessions.
os.environ["PLAID_ENCRYPTION_KEY"] = "UTxtCGAy-teDR0N8K2tUap0l6aguAg1OtH_rDulrel0="

from collections.abc import AsyncIterator  # noqa: E402

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import *  # noqa: F401,F403,E402


def _enable_sqlite_fks(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    event.listen(engine.sync_engine, "connect", _enable_sqlite_fks)
    TestSession = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with TestSession() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    await engine.dispose()


async def register_user(
    client: AsyncClient, email: str = "user@example.com", password: str = "supersecret"
) -> dict[str, str]:
    """Register a user and return an Authorization header dict."""
    r = await client.post(
        "/api/auth/register", json={"email": email, "password": password}
    )
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def create_account(client: AsyncClient, headers: dict[str, str], name: str = "Checking") -> int:
    r = await client.post(
        "/api/accounts", json={"name": name, "type": "checking"}, headers=headers
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def create_group(client: AsyncClient, headers: dict[str, str], name: str = "Bills") -> int:
    r = await client.post("/api/category-groups", json={"name": name}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def create_category(
    client: AsyncClient, headers: dict[str, str], group_id: int, name: str = "Rent"
) -> int:
    r = await client.post(
        "/api/categories",
        json={"group_id": group_id, "name": name},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]
