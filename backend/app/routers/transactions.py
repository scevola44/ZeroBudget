from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models import Account, Category, CategoryGroup, Transaction
from app.schemas.transaction import TransactionCreate, TransactionResponse, TransactionUpdate
from app.services.budget_calc import month_start, next_month_start, parse_month

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


async def _owned_transaction(db, user_id: int, txn_id: int) -> Transaction:
    txn = await db.get(Transaction, txn_id)
    if txn is None or txn.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    return txn


async def _owned_account(db, user_id: int, account_id: int) -> Account:
    account = await db.get(Account, account_id)
    if account is None or account.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid account")
    return account


async def _owned_category(db, user_id: int, category_id: int) -> Category:
    category = await db.get(Category, category_id)
    if category is None or category.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid category")
    return category


async def _enforce_scope_match(
    db, user_id: int, account_id: int, category_id: int | None
) -> None:
    """Reject transactions whose account scope doesn't match the category's
    group scope. Cross-scope movement must go through transfers (Phase 2).
    Inflows / unassigned transactions (``category_id is None``) are exempt.
    """
    if category_id is None:
        return
    account = await _owned_account(db, user_id, account_id)
    category = await _owned_category(db, user_id, category_id)
    group = await db.get(CategoryGroup, category.group_id)
    if group is None or group.scope != account.scope:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Category scope ({group.scope if group else '?'}) does not match "
                f"account scope ({account.scope}). Use a transfer instead."
            ),
        )


@router.get("", response_model=list[TransactionResponse])
async def list_transactions(
    db: DbSession,
    current_user: CurrentUser,
    account_id: int | None = Query(default=None),
    month: str | None = Query(default=None, description="YYYY-MM"),
) -> list[TransactionResponse]:
    stmt = select(Transaction).where(Transaction.user_id == current_user.id)
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    if month is not None:
        start = month_start(parse_month(month))
        end = next_month_start(start)
        stmt = stmt.where(Transaction.date >= start, Transaction.date < end)
    stmt = stmt.order_by(Transaction.date.desc(), Transaction.id.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [TransactionResponse.model_validate(r) for r in rows]


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    payload: TransactionCreate, db: DbSession, current_user: CurrentUser
) -> TransactionResponse:
    await _owned_account(db, current_user.id, payload.account_id)
    if payload.category_id is not None:
        await _owned_category(db, current_user.id, payload.category_id)
    await _enforce_scope_match(
        db, current_user.id, payload.account_id, payload.category_id
    )
    txn = Transaction(
        user_id=current_user.id,
        account_id=payload.account_id,
        category_id=payload.category_id,
        date=payload.date,
        payee=payload.payee,
        memo=payload.memo,
        amount_cents=payload.amount_cents,
    )
    db.add(txn)
    await db.commit()
    await db.refresh(txn)
    return TransactionResponse.model_validate(txn)


@router.patch("/{txn_id}", response_model=TransactionResponse)
async def update_transaction(
    txn_id: int,
    payload: TransactionUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> TransactionResponse:
    txn = await _owned_transaction(db, current_user.id, txn_id)
    if payload.account_id is not None:
        await _owned_account(db, current_user.id, payload.account_id)
        txn.account_id = payload.account_id
    if "category_id" in payload.model_fields_set:
        if payload.category_id is not None:
            await _owned_category(db, current_user.id, payload.category_id)
        txn.category_id = payload.category_id
    # Re-check scope match against the merged (account_id, category_id) pair.
    await _enforce_scope_match(db, current_user.id, txn.account_id, txn.category_id)
    if payload.date is not None:
        txn.date = payload.date
    if payload.payee is not None:
        txn.payee = payload.payee
    if payload.memo is not None:
        txn.memo = payload.memo
    if payload.amount_cents is not None:
        txn.amount_cents = payload.amount_cents
    await db.commit()
    await db.refresh(txn)
    return TransactionResponse.model_validate(txn)


@router.delete("/{txn_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    txn_id: int, db: DbSession, current_user: CurrentUser
) -> None:
    txn = await _owned_transaction(db, current_user.id, txn_id)
    await db.delete(txn)
    await db.commit()
