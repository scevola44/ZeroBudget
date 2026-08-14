from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import CurrentUser, DbSession
from app.models import Payee, Transaction
from app.schemas.payee import (
    PayeeMergeRequest,
    PayeeMergeResponse,
    PayeeRenameRequest,
    PayeeResponse,
)

router = APIRouter(prefix="/api/payees", tags=["payees"])


async def _owned_payee(db: AsyncSession, user_id: int, payee_id: int) -> Payee:
    payee = await db.get(Payee, payee_id)
    if payee is None or payee.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payee not found")
    return payee


async def _reject_duplicate_name(
    db: AsyncSession, user_id: int, name: str, *, excluding_id: int | None = None
) -> None:
    query = select(Payee.id).where(
        Payee.user_id == user_id, func.lower(Payee.name) == name.lower()
    )
    if excluding_id is not None:
        query = query.where(Payee.id != excluding_id)
    if await db.scalar(query.limit(1)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'A payee called "{name}" already exists. Merge them instead.',
        )


@router.get("", response_model=list[PayeeResponse])
async def list_payees(
    db: DbSession,
    current_user: CurrentUser,
    q: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=200),
) -> list[Payee]:
    """Payees whose name starts with ``q``, most recently used first.

    Blank ``q`` returns every payee (bounded by ``limit``) — the shape the
    Settings management list needs. A payee with no transactions yet sorts
    last rather than being excluded.
    """
    stmt = (
        select(Payee)
        .outerjoin(Transaction, Transaction.payee_id == Payee.id)
        .where(Payee.user_id == current_user.id)
    )
    if q:
        stmt = stmt.where(Payee.name.ilike(f"{q}%"))
    stmt = (
        stmt.group_by(Payee.id)
        .order_by(func.max(Transaction.date).desc().nulls_last())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


@router.patch("/{payee_id}", response_model=PayeeResponse)
async def rename_payee(
    payee_id: int, payload: PayeeRenameRequest, db: DbSession, current_user: CurrentUser
) -> Payee:
    """Rename a payee. O(1): only this row changes — every transaction that
    references it by ``payee_id`` displays the new name immediately, with no
    transaction rows touched."""
    payee = await _owned_payee(db, current_user.id, payee_id)
    name = payload.name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Payee name cannot be blank.",
        )
    await _reject_duplicate_name(db, current_user.id, name, excluding_id=payee.id)
    payee.name = name
    await db.commit()
    await db.refresh(payee)
    return payee


@router.post("/{payee_id}/merge", response_model=PayeeMergeResponse)
async def merge_payees(
    payee_id: int, payload: PayeeMergeRequest, db: DbSession, current_user: CurrentUser
) -> PayeeMergeResponse:
    """Fold ``source_ids`` into ``payee_id``: every transaction referencing a
    source payee is reassigned, then the now-orphaned source payees are
    deleted."""
    target = await _owned_payee(db, current_user.id, payee_id)
    if payee_id in payload.source_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A payee cannot be merged into itself.",
        )
    sources = [
        await _owned_payee(db, current_user.id, source_id)
        for source_id in payload.source_ids
    ]

    result = await db.execute(
        update(Transaction)
        .where(Transaction.payee_id.in_([s.id for s in sources]))
        .values(payee_id=target.id)
    )
    for source in sources:
        await db.delete(source)
    await db.commit()
    return PayeeMergeResponse(reassigned=result.rowcount or 0)
