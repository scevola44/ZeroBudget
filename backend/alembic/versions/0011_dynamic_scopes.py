"""dynamic, user-managed scopes

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-13

Turns the hard-coded ``"personal"`` / ``"shared"`` strings into rows in a new
``scopes`` table, one set per user, and repoints ``accounts``,
``category_groups`` and ``bank_auth_requests`` at them by foreign key.

Every existing user gets both defaults regardless of whether they used the
second one, because the compile-time constants gave them both. The names chosen
here ("Personal", "Family") are the ones the UI already displayed, so nothing
visibly changes for an existing instance.

The old string -> new name mapping is written out literally rather than
imported from ``app.models.scope``: a migration is a record of what the schema
looked like at this revision, and must keep working after the app's constants
move on.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables that carried a scope string, in FK-safe order. Each one also carries
# ``user_id``, which is what scopes the backfill to the row's own owner.
SCOPED_TABLES: tuple[str, ...] = ("accounts", "category_groups", "bank_auth_requests")

PERSONAL_SCOPE_NAME = "Personal"
SHARED_SCOPE_NAME = "Family"


def upgrade() -> None:
    op.create_table(
        "scopes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("user_id", "name", name="uq_scopes_user_name"),
    )
    op.create_index("ix_scopes_user_id", "scopes", ["user_id"])

    # Personal first so it keeps sort_order 0, which is the index the UI colours
    # by — existing chips stay the colours the user already knows them by.
    for sort_order, name in enumerate((PERSONAL_SCOPE_NAME, SHARED_SCOPE_NAME)):
        op.execute(
            sa.text(
                "INSERT INTO scopes (user_id, name, sort_order) "
                "SELECT id, :name, :sort_order FROM users"
            ).bindparams(name=name, sort_order=sort_order)
        )

    for table in SCOPED_TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column("scope_id", sa.Integer(), nullable=True))

        op.execute(
            sa.text(
                f"UPDATE {table} SET scope_id = ("  # noqa: S608 — table names are a literal tuple
                "  SELECT s.id FROM scopes s"
                f"  WHERE s.user_id = {table}.user_id"
                "    AND s.name = CASE "
                f"      {table}.scope WHEN 'shared' THEN :shared_name ELSE :personal_name"
                "    END"
                ")"
            ).bindparams(shared_name=SHARED_SCOPE_NAME, personal_name=PERSONAL_SCOPE_NAME)
        )

        # Fail loudly on a row the backfill could not place rather than letting
        # the NOT NULL below abort with a schema already half-converted.
        orphans = op.get_bind().execute(
            sa.text(f"SELECT COUNT(*) FROM {table} WHERE scope_id IS NULL")  # noqa: S608
        ).scalar_one()
        if orphans:
            raise RuntimeError(
                f"{orphans} row(s) in {table} could not be matched to a scope; "
                "aborting before the column is made NOT NULL."
            )

        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column("scope_id", existing_type=sa.Integer(), nullable=False)
            batch_op.create_foreign_key(
                f"fk_{table}_scope_id", "scopes", ["scope_id"], ["id"], ondelete="RESTRICT"
            )
            batch_op.create_index(f"ix_{table}_scope_id", ["scope_id"])
            batch_op.drop_column("scope")


def downgrade() -> None:
    """Restore the string columns.

    Lossy on purpose: any scope the user added beyond the original two has no
    string equivalent, so its rows collapse to ``"personal"``. Downgrading past
    this revision after using the feature therefore merges those pools.
    """
    for table in SCOPED_TABLES:
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column("scope", sa.String(length=16), nullable=True))

        op.execute(
            sa.text(
                f"UPDATE {table} SET scope = CASE WHEN scope_id IN ("  # noqa: S608
                "  SELECT id FROM scopes WHERE name = :shared_name"
                ") THEN 'shared' ELSE 'personal' END"
            ).bindparams(shared_name=SHARED_SCOPE_NAME)
        )

        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column("scope", existing_type=sa.String(length=16), nullable=False)
            batch_op.drop_index(f"ix_{table}_scope_id")
            batch_op.drop_constraint(f"fk_{table}_scope_id", type_="foreignkey")
            batch_op.drop_column("scope_id")

    op.drop_index("ix_scopes_user_id", table_name="scopes")
    op.drop_table("scopes")
