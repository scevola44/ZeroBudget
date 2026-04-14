from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.deps import CurrentUser, DbSession
from app.models import Account, Transaction
from app.schemas.account import AccountCreate, AccountResponse, AccountUpdate

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


async def _get_owned(db, user_id: int, account_id: int) -> Account:
    account = await db.get(Account, account_id)
    if account is None or account.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


@router.get("", response_model=list[AccountResponse])
async def list_accounts(db: DbSession, current_user: CurrentUser) -> list[AccountResponse]:
    # Sum transactions per account in one query to compute balances.
    totals_stmt = (
        select(Transaction.account_id, func.coalesce(func.sum(Transaction.amount_cents), 0))
        .where(Transaction.user_id == current_user.id)
        .group_by(Transaction.account_id)
    )
    totals = {row[0]: int(row[1]) for row in (await db.execute(totals_stmt)).all()}

    accounts_stmt = (
        select(Account).where(Account.user_id == current_user.id).order_by(Account.id)
    )
    accounts = (await db.execute(accounts_stmt)).scalars().all()
    return [
        AccountResponse(
            id=a.id,
            name=a.name,
            type=a.type,
            balance_cents=totals.get(a.id, 0),
        )
        for a in accounts
    ]


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate, db: DbSession, current_user: CurrentUser
) -> AccountResponse:
    account = Account(user_id=current_user.id, name=payload.name, type=payload.type)
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return AccountResponse(id=account.id, name=account.name, type=account.type, balance_cents=0)


@router.patch("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: int,
    payload: AccountUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> AccountResponse:
    account = await _get_owned(db, current_user.id, account_id)
    if payload.name is not None:
        account.name = payload.name
    if payload.type is not None:
        account.type = payload.type
    await db.commit()
    await db.refresh(account)

    total = await db.scalar(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            Transaction.account_id == account.id
        )
    )
    return AccountResponse(
        id=account.id, name=account.name, type=account.type, balance_cents=int(total or 0)
    )


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(account_id: int, db: DbSession, current_user: CurrentUser) -> None:
    account = await _get_owned(db, current_user.id, account_id)
    await db.delete(account)
    await db.commit()
