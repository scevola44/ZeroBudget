"""Payee find-or-create, keeping ``Transaction.payee_id`` normalized.

Every write path that sets ``Transaction.payee`` calls ``resolve_payee`` so
the same real-world payee always maps to one ``Payee`` row no matter how many
times its name was typed, or with what casing.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payee
from app.services.synthetic_payees import SYNTHETIC_PAYEES


async def resolve_payee(db: AsyncSession, user_id: int, name: str) -> int | None:
    """Find-or-create a ``Payee`` for ``name``, returning its id.

    Returns ``None`` for blank names and for the app's own synthetic payees
    (opening balance, balance adjustment) — those describe a reconciling
    bookkeeping entry, not a real-world counterparty, so they stay out of the
    payee list, autocomplete, and merge UI. Lookup is case-insensitive;
    whichever casing was typed first is what the stored ``Payee.name`` keeps.
    """
    stripped = name.strip()
    if not stripped or stripped in SYNTHETIC_PAYEES:
        return None

    existing = await db.scalar(
        select(Payee).where(
            Payee.user_id == user_id,
            func.lower(Payee.name) == stripped.lower(),
        )
    )
    if existing is not None:
        return existing.id

    payee = Payee(user_id=user_id, name=stripped)
    db.add(payee)
    await db.flush()
    return payee.id
