"""End-to-end exercise of the Alembic chain against a real (file) database.

Every other test builds the schema with ``Base.metadata.create_all`` (see
``conftest.py``), so without this module no migration is ever executed by CI —
and ``0011`` rewrites live production data. Alembic runs in a **subprocess**
here for two reasons: ``alembic/env.py`` calls ``asyncio.run()``, which cannot
be nested inside pytest-asyncio's loop, and it reads the database URL from the
lru_cached ``get_settings()``, which only a fresh process re-reads. It is also
exactly how production applies migrations (``Dockerfile``: ``alembic upgrade
head && uvicorn ...``).
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent

# The revision immediately before scopes became rows, and the string values the
# ``scope`` column held at that point.
PRE_SCOPES_REVISION = "0010"
LEGACY_PERSONAL = "personal"
LEGACY_SHARED = "shared"

SCOPED_TABLES = ("accounts", "category_groups", "bank_auth_requests")

# The column holding the per-row label the fixture encodes the legacy scope in,
# so one assertion can walk all three tables.
LABEL_COLUMN = {
    "accounts": "name",
    "category_groups": "name",
    "bank_auth_requests": "state",
}


def run_alembic(db_path: Path, *args: str) -> None:
    """Run the alembic CLI against ``db_path``, raising with its output on failure."""
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
        "JWT_SECRET": "test-secret-long-enough-for-hs256-key-32bytes",
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"alembic {' '.join(args)} failed:\n{result.stdout}\n{result.stderr}"
        )


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "migration_test.db"


def seed_pre_scopes_data(db_path: Path) -> None:
    """Two users, each with rows in both legacy scopes on all three tables.

    Two users is the point: the backfill joins on a name, so a single-user
    fixture would pass even if the correlation to ``user_id`` were missing.
    """
    conn = sqlite3.connect(db_path)
    try:
        for user_id, email in ((1, "a@example.com"), (2, "b@example.com")):
            conn.execute(
                "INSERT INTO users (id, email, hashed_password) VALUES (?, ?, 'x')",
                (user_id, email),
            )
            for legacy_scope in (LEGACY_PERSONAL, LEGACY_SHARED):
                conn.execute(
                    "INSERT INTO accounts (user_id, name, type, scope, closed) "
                    "VALUES (?, ?, 'checking', ?, 0)",
                    (user_id, f"acct-{user_id}-{legacy_scope}", legacy_scope),
                )
                conn.execute(
                    "INSERT INTO category_groups (user_id, name, sort_order, scope) "
                    "VALUES (?, ?, 0, ?)",
                    (user_id, f"group-{user_id}-{legacy_scope}", legacy_scope),
                )
                conn.execute(
                    "INSERT INTO bank_auth_requests "
                    "(user_id, state, aspsp_name, aspsp_country, scope) "
                    "VALUES (?, ?, 'Mock', 'FI', ?)",
                    (user_id, f"state-{user_id}-{legacy_scope}", legacy_scope),
                )
        conn.commit()
    finally:
        conn.close()


def fetch_all(db_path: Path, sql: str) -> list[tuple]:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def column_names(db_path: Path, table: str) -> set[str]:
    return {row[1] for row in fetch_all(db_path, f"PRAGMA table_info({table})")}


def test_upgrade_moves_every_row_to_its_own_users_scope(db_path: Path) -> None:
    run_alembic(db_path, "upgrade", PRE_SCOPES_REVISION)
    seed_pre_scopes_data(db_path)

    run_alembic(db_path, "upgrade", "head")

    scopes = fetch_all(
        db_path, "SELECT user_id, name, sort_order FROM scopes ORDER BY user_id, sort_order"
    )
    assert scopes == [
        (1, "Personal", 0),
        (1, "Family", 1),
        (2, "Personal", 0),
        (2, "Family", 1),
    ]

    for table in SCOPED_TABLES:
        rows = fetch_all(
            db_path,
            f"SELECT t.user_id, t.{LABEL_COLUMN[table]}, s.user_id, s.name "
            f"FROM {table} t JOIN scopes s ON s.id = t.scope_id ORDER BY t.id",
        )
        assert len(rows) == 4, f"{table} lost rows during the migration"
        for row_user_id, label, scope_user_id, scope_name in rows:
            assert scope_user_id == row_user_id, (
                f"{table} row {label!r} bound to another user's scope"
            )
            expected = "Family" if label.endswith(LEGACY_SHARED) else "Personal"
            assert scope_name == expected, f"{table} row {label!r} landed in {scope_name}"


def test_upgrade_drops_the_legacy_string_column(db_path: Path) -> None:
    run_alembic(db_path, "upgrade", PRE_SCOPES_REVISION)
    seed_pre_scopes_data(db_path)

    run_alembic(db_path, "upgrade", "head")

    for table in SCOPED_TABLES:
        columns = column_names(db_path, table)
        assert "scope_id" in columns
        assert "scope" not in columns


def test_upgrade_preserves_foreign_keys_through_the_sqlite_table_rebuild(
    db_path: Path,
) -> None:
    """``batch_alter_table`` recreates the table on SQLite; FKs must survive.

    ``accounts`` declares its ``users`` and ``bank_connections`` foreign keys
    without explicit names, which is the classic way an Alembic batch rebuild
    silently drops them.
    """
    run_alembic(db_path, "upgrade", PRE_SCOPES_REVISION)
    before = {
        table: {row[2] for row in fetch_all(db_path, f"PRAGMA foreign_key_list({table})")}
        for table in SCOPED_TABLES
    }

    run_alembic(db_path, "upgrade", "head")

    for table in SCOPED_TABLES:
        after = {row[2] for row in fetch_all(db_path, f"PRAGMA foreign_key_list({table})")}
        assert before[table] <= after, f"{table} lost a foreign key: {before[table] - after}"
        assert "scopes" in after


def test_downgrade_restores_the_legacy_strings(db_path: Path) -> None:
    run_alembic(db_path, "upgrade", PRE_SCOPES_REVISION)
    seed_pre_scopes_data(db_path)
    run_alembic(db_path, "upgrade", "head")

    run_alembic(db_path, "downgrade", PRE_SCOPES_REVISION)

    for table in SCOPED_TABLES:
        columns = column_names(db_path, table)
        assert "scope" in columns
        assert "scope_id" not in columns

    labelled = fetch_all(db_path, "SELECT name, scope FROM accounts ORDER BY id")
    for name, scope in labelled:
        assert scope == (LEGACY_SHARED if name.endswith(LEGACY_SHARED) else LEGACY_PERSONAL)

    assert fetch_all(db_path, "SELECT name FROM sqlite_master WHERE name = 'scopes'") == []
