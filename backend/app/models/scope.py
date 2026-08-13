from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# The scopes a newly registered user starts with. "Personal" is the user's own
# money; "Family" is money in a joint account managed jointly with someone
# outside the app. They are only defaults — the user renames, adds and removes
# them from Settings.
DEFAULT_SCOPE_NAMES: tuple[str, ...] = ("Personal", "Family")

# Matches every other user-facing name column (accounts, category_groups, categories).
SCOPE_NAME_MAX_LENGTH = 120


class Scope(Base):
    """An independent budget pool.

    A scope partitions accounts and category groups into pools that share one
    user, one app, and one screen — but have separate Ready-to-Assign totals.
    This replaces YNAB's multi-budget concept and is the reason this app exists:
    budgeting a joint account alongside your own money in one view.

    Nothing about the app's behaviour depends on *which* scope a row is in;
    scopes are symmetric, and every rule (transfers between pools, keeping a
    category's scope in step with its account's) is stated in terms of "same
    scope or not".
    """

    __tablename__ = "scopes"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_scopes_user_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(SCOPE_NAME_MAX_LENGTH), nullable=False)
    # Display order, and the index the UI colours scopes by. Not necessarily
    # contiguous: deleting a scope leaves a gap on purpose, so the survivors
    # keep the colours the user already knows them by.
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
