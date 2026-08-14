"""Find-or-create a Payee from raw typed or bank-provided text.

Every write path that used to store a plain payee string now needs to resolve
that string to a Payee row first. Centralizing it here keeps that lookup
(case/whitespace-insensitive, so retyping "amazon" after "Amazon" already
exists reuses the row instead of creating a near-duplicate) from drifting
between the transactions router, bank sync, and YNAB import.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payee


async def resolve_payee(db: AsyncSession, user_id: int, name: str) -> Payee | None:
    """Find-or-create ``name`` as a Payee of ``user_id``.

    Blank input means "no payee" — returns ``None``, matching the old
    empty-string convention on ``Transaction.payee``.
    """
    normalized = name.strip()
    if not normalized:
        return None

    existing = await db.scalar(
        select(Payee).where(
            Payee.user_id == user_id, func.lower(Payee.name) == normalized.lower()
        )
    )
    if existing is not None:
        return existing

    payee = Payee(user_id=user_id, name=normalized)
    db.add(payee)
    await db.flush()
    return payee
