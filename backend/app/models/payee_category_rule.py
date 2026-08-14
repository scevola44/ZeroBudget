from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PayeeCategoryRule(Base):
    """A "payee contains X -> category Y" auto-categorization rule.

    Applied only when a bank sync or import creates a transaction with no
    category of its own — never overwrites a category the user (or the
    transaction's own import row) already set. Rules are tried in
    ``sort_order``; the first whose ``contains_text`` appears in the
    incoming payee text (case-insensitively) wins. See
    ``services/payee_rules.py`` for the matching logic.
    """

    __tablename__ = "payee_category_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), index=True, nullable=False
    )
    contains_text: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
