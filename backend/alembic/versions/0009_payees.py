"""payees table + payee_id on transactions

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-11

Promotes the free-text ``Transaction.payee`` string to a normalized
``payees`` table with a ``payee_id`` FK. The string column stays (see the
TODO on ``app.models.transaction.Transaction.payee_id``) — both are kept in
sync going forward by ``services.payees.resolve_payee``.

Backfill groups existing rows by exact ``(user_id, payee)`` string match, not
case-folded: two rows typed as "Aldi" and "aldi" become two distinct payees.
That's a deliberate simplification for a one-time migration — merging
near-duplicates safely needs the merge endpoint's explicit confirmation, not
a silent guess made once during a migration. The app's own synthetic payees
(opening balance, balance adjustment) are left unresolved (``payee_id`` stays
NULL) since they describe bookkeeping, not a real counterparty.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Mirrors app.services.synthetic_payees.SYNTHETIC_PAYEES — duplicated rather
# than imported since migrations must not depend on application code that can
# change shape after this migration is written.
_SYNTHETIC_PAYEES = ("Balance Adjustment", "Opening Balance")


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
        batch_op.add_column(sa.Column("payee_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_transactions_payee_id",
            "payees",
            ["payee_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_transactions_payee_id", ["payee_id"])

    bind = op.get_bind()
    payees_table = sa.table(
        "payees",
        sa.column("id", sa.Integer()),
        sa.column("user_id", sa.Integer()),
        sa.column("name", sa.String()),
    )
    transactions_table = sa.table(
        "transactions",
        sa.column("id", sa.Integer()),
        sa.column("user_id", sa.Integer()),
        sa.column("payee", sa.String()),
        sa.column("payee_id", sa.Integer()),
    )

    distinct_payees = bind.execute(
        sa.select(transactions_table.c.user_id, transactions_table.c.payee)
        .where(transactions_table.c.payee != "")
        .where(transactions_table.c.payee.notin_(_SYNTHETIC_PAYEES))
        .distinct()
    ).all()

    for user_id, payee_name in distinct_payees:
        result = bind.execute(
            payees_table.insert().values(user_id=user_id, name=payee_name)
        )
        payee_id = result.inserted_primary_key[0]
        bind.execute(
            transactions_table.update()
            .where(
                transactions_table.c.user_id == user_id,
                transactions_table.c.payee == payee_name,
            )
            .values(payee_id=payee_id)
        )


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch_op:
        batch_op.drop_index("ix_transactions_payee_id")
        batch_op.drop_constraint("fk_transactions_payee_id", type_="foreignkey")
        batch_op.drop_column("payee_id")
    op.drop_index("ix_payees_user_id", table_name="payees")
    op.drop_table("payees")
