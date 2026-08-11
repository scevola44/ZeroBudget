from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select, update

from app.deps import CurrentUser, DbSession
from app.models import Payee, Transaction
from app.schemas.payee import (
    PayeeMergeRequest,
    PayeeMergeResponse,
    PayeeResponse,
    PayeeUpdate,
)

router = APIRouter(prefix="/api/payees", tags=["payees"])


async def _owned_payee(db: DbSession, user_id: int, payee_id: int) -> Payee:
    payee = await db.get(Payee, payee_id)
    if payee is None or payee.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payee not found")
    return payee


@router.get("", response_model=list[PayeeResponse])
async def list_payees(db: DbSession, current_user: CurrentUser) -> list[PayeeResponse]:
    payees = (
        (
            await db.execute(
                select(Payee)
                .where(Payee.user_id == current_user.id)
                .order_by(Payee.name)
            )
        )
        .scalars()
        .all()
    )
    return [PayeeResponse.model_validate(p) for p in payees]


@router.patch("/{payee_id}", response_model=PayeeResponse)
async def rename_payee(
    payee_id: int, payload: PayeeUpdate, db: DbSession, current_user: CurrentUser
) -> PayeeResponse:
    """Rename a payee, updating every transaction that mirrors its name."""
    payee = await _owned_payee(db, current_user.id, payee_id)
    new_name = payload.name.strip()
    if not new_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Name cannot be blank"
        )

    collision = await db.scalar(
        select(Payee.id).where(
            Payee.user_id == current_user.id,
            func.lower(Payee.name) == new_name.lower(),
            Payee.id != payee_id,
        )
    )
    if collision is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="You already have a payee with that name.",
        )

    payee.name = new_name
    await db.execute(
        update(Transaction)
        .where(Transaction.user_id == current_user.id, Transaction.payee_id == payee_id)
        .values(payee=new_name)
    )
    await db.commit()
    await db.refresh(payee)
    return PayeeResponse.model_validate(payee)


@router.post("/merge", response_model=PayeeMergeResponse)
async def merge_payees(
    payload: PayeeMergeRequest, db: DbSession, current_user: CurrentUser
) -> PayeeMergeResponse:
    """Fold ``source_id`` into ``target_id``: reassign its transactions, then delete it."""
    if payload.source_id == payload.target_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot merge a payee into itself.",
        )
    source = await _owned_payee(db, current_user.id, payload.source_id)
    target = await _owned_payee(db, current_user.id, payload.target_id)

    result = await db.execute(
        update(Transaction)
        .where(Transaction.user_id == current_user.id, Transaction.payee_id == source.id)
        .values(payee_id=target.id, payee=target.name)
    )
    await db.delete(source)
    await db.commit()
    return PayeeMergeResponse(merged_count=result.rowcount or 0)
