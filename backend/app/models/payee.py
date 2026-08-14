from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Payee(Base):
    """Who a transaction was paid to or received from.

    Scope-agnostic by design: the same real-world payee can be paid from any
    of the user's accounts, so this carries no ``scope_id``. Renaming or
    merging a payee only ever touches this table, never the transactions that
    reference it by ``payee_id`` — that's the point of promoting it out of a
    free-text column.
    """

    __tablename__ = "payees"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_payees_user_id_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
