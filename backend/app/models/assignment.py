from datetime import date

from sqlalchemy import BigInteger, Date, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MonthlyAssignment(Base):
    """Money assigned to a category for a specific month.

    ``month`` is always stored as the first day of that month (YYYY-MM-01).
    Uniqueness on (user_id, category_id, month) lets the API upsert freely.
    """

    __tablename__ = "monthly_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "category_id", "month", name="uq_assignment_user_cat_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), index=True, nullable=False
    )
    month: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
