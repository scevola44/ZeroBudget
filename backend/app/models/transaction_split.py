from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class TransactionSplit(Base):
    """One category line of a split transaction.

    Split lines mirror ``Transaction`` closely on purpose: ``category_id`` is
    nullable with the same ``ON DELETE SET NULL`` behavior as the parent's,
    so deleting a category leaves a split line unassigned exactly like it
    would leave a plain transaction unassigned — no extra app code needed to
    keep that invariant. A transaction with splits always has
    ``category_id IS NULL`` at the parent level; the parent's amount must
    equal the sum of its lines (enforced in the router, not here).
    """

    __tablename__ = "transaction_splits"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), index=True, nullable=True
    )
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    memo: Mapped[str] = mapped_column(String(500), nullable=False, default="")
