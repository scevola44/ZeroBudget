"""payees

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-14

Promotes the free-text ``transactions.payee`` column to a ``payees`` table,
one per user, the same shape ``0011_dynamic_scopes`` used to promote the
``scope`` string column: create the table, backfill it from the existing
string values, point a new FK column at it, then drop the string column.

Existing payee text is grouped per user, case/whitespace-insensitively (a
payee typed as both "Amazon" and "amazon" collapses to one row), keeping the
most recently dated transaction's original casing as the canonical name —
the same "most recent wins" rule ``category_suggest.py`` already uses when
ranking a payee's category history. Blank payee text gets no row; those
transactions keep ``payee_id IS NULL``, the same meaning ``payee = ""`` had.

The backfill runs in Python rather than a single SQL statement: grouping by a
normalized key while keeping one row's original casing is awkward to express
portably across SQLite (dev) and Postgres (prod) without dialect-specific
window functions, and the row counts here (one self-hosted user's lifetime of
transactions) are small enough that Python-side grouping costs nothing.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payees",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_payees_user_id_name"),
    )
    op.create_index("ix_payees_user_id", "payees", ["user_id"])

    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "payee_id",
                sa.Integer(),
                sa.ForeignKey(
                    "payees.id", ondelete="SET NULL", name="fk_transactions_payee_id"
                ),
                nullable=True,
            )
        )
        batch_op.create_index("ix_transactions_payee_id", ["payee_id"])

    _backfill_payees()

    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_column("payee")


def _backfill_payees() -> None:
    bind = op.get_bind()
    transactions = sa.table(
        "transactions",
        sa.column("id", sa.Integer()),
        sa.column("user_id", sa.Integer()),
        sa.column("payee", sa.String()),
        sa.column("date", sa.Date()),
        sa.column("payee_id", sa.Integer()),
    )
    payees = sa.table(
        "payees",
        sa.column("id", sa.Integer()),
        sa.column("user_id", sa.Integer()),
        sa.column("name", sa.String()),
    )

    rows = bind.execute(
        sa.select(
            transactions.c.id,
            transactions.c.user_id,
            transactions.c.payee,
            transactions.c.date,
        )
    ).all()

    # (user_id, normalized name) -> {"name": most-recent original casing,
    # "date": that occurrence's date, "ids": every transaction id in the group}
    groups: dict[tuple[int, str], dict] = {}
    for row in rows:
        raw = (row.payee or "").strip()
        if not raw:
            continue
        key = (row.user_id, raw.casefold())
        group = groups.setdefault(key, {"name": raw, "date": row.date, "ids": []})
        if row.date is not None and (group["date"] is None or row.date >= group["date"]):
            group["name"] = raw
            group["date"] = row.date
        group["ids"].append(row.id)

    for (user_id, _normalized), group in groups.items():
        bind.execute(payees.insert().values(user_id=user_id, name=group["name"]))
        # Re-queried rather than read off inserted_primary_key: the ``sa.table()``
        # proxy above doesn't declare a primary key, so SQLAlchemy has nothing to
        # report it from on SQLite. (user_id, name) is unique, so this is exact.
        payee_id = bind.execute(
            sa.select(payees.c.id).where(
                payees.c.user_id == user_id, payees.c.name == group["name"]
            )
        ).scalar_one()
        bind.execute(
            transactions.update()
            .where(transactions.c.id.in_(group["ids"]))
            .values(payee_id=payee_id)
        )


def downgrade() -> None:
    """Restore the string column.

    Lossy on purpose, same as ``0011``'s downgrade: any rename or merge done
    through the payee entity since upgrading has no string-column equivalent,
    so downgrading after using those features loses that history and shows
    each transaction's payee as it's named *now*, not as it was typed.
    """
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.add_column(
            sa.Column("payee", sa.String(length=255), nullable=False, server_default="")
        )

    op.execute(
        sa.text(
            "UPDATE transactions SET payee = ("
            "  SELECT p.name FROM payees p WHERE p.id = transactions.payee_id"
            ") WHERE payee_id IS NOT NULL"
        )
    )

    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_index("ix_transactions_payee_id")
        batch_op.drop_constraint("fk_transactions_payee_id", type_="foreignkey")
        batch_op.drop_column("payee_id")

    op.drop_index("ix_payees_user_id", table_name="payees")
    op.drop_table("payees")
