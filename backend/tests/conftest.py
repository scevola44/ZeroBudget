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
os.environ["BANK_ENCRYPTION_KEY"] = "UTxtCGAy-teDR0N8K2tUap0l6aguAg1OtH_rDulrel0="
# Banking router tests exercise the connect flow with a fake client; the
# redirect URL just has to be present.
os.environ["ENABLE_BANKING_REDIRECT_URL"] = "http://test/banking/callback"

from collections.abc import AsyncIterator  # noqa: E402

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import *  # noqa: F401,F403,E402
from app.models import Scope  # noqa: E402 — named import for the helpers below


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


PERSONAL = "Personal"
FAMILY = "Family"


async def add_scope(db: AsyncSession, user_id: int, name: str = PERSONAL) -> Scope:
    """Create a scope for a user built directly through the ORM.

    Tests that go through ``/api/auth/register`` get their scopes seeded for
    free; the ones that construct a ``User`` row themselves need this.
    """
    scope = Scope(user_id=user_id, name=name, sort_order=0)
    db.add(scope)
    await db.flush()
    return scope


async def scope_ids(client: AsyncClient, headers: dict[str, str]) -> dict[str, int]:
    """Name -> id for a user's scopes. Registration seeds Personal and Family."""
    r = await client.get("/api/scopes", headers=headers)
    assert r.status_code == 200, r.text
    return {s["name"]: s["id"] for s in r.json()}


async def scope_id(client: AsyncClient, headers: dict[str, str], name: str) -> int:
    return (await scope_ids(client, headers))[name]


async def create_account(
    client: AsyncClient,
    headers: dict[str, str],
    name: str = "Checking",
    *,
    scope: str = PERSONAL,
    type: str = "checking",
) -> int:
    """Create an account in the scope *named* ``scope``.

    Tests name scopes rather than passing ids so they keep reading as English;
    the id is resolved here.
    """
    r = await client.post(
        "/api/accounts",
        json={
            "name": name,
            "type": type,
            "scope_id": await scope_id(client, headers, scope),
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def create_group(
    client: AsyncClient,
    headers: dict[str, str],
    name: str = "Bills",
    *,
    scope: str = PERSONAL,
) -> int:
    r = await client.post(
        "/api/category-groups",
        json={"name": name, "scope_id": await scope_id(client, headers, scope)},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def ready_to_assign(
    client: AsyncClient,
    headers: dict[str, str],
    budget_body: dict,
    scope: str = PERSONAL,
) -> int:
    """One scope's Ready to Assign, out of an already-fetched budget response.

    The response carries a row per scope keyed by id, so the name the test
    reads in has to be resolved against the user's scopes.
    """
    wanted = await scope_id(client, headers, scope)
    for row in budget_body["ready_to_assign"]:
        if row["scope_id"] == wanted:
            return row["ready_to_assign_cents"]
    raise AssertionError(f"no ready_to_assign entry for scope {scope!r}")


async def create_category(
    client: AsyncClient,
    headers: dict[str, str],
    group_id: int,
    name: str = "Rent",
    *,
    goal_kind: str = "monthly",
    goal_amount_cents: int = 10_000,
    goal_target_month: str | None = None,
) -> int:
    body: dict = {
        "group_id": group_id,
        "name": name,
        "goal_kind": goal_kind,
        "goal_amount_cents": goal_amount_cents,
    }
    if goal_target_month is not None:
        body["goal_target_month"] = goal_target_month
    r = await client.post("/api/categories", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]
