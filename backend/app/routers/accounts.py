from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.deps import CurrentUser, DbSession
from app.models import Account, BankConnection, Transaction
from app.schemas.account import AccountCreate, AccountResponse, AccountUpdate

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


async def _get_owned(db, user_id: int, account_id: int) -> Account:
    account = await db.get(Account, account_id)
    if account is None or account.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


def _to_response(
    account: Account, balance_cents: int, institution_name: str | None = None
) -> AccountResponse:
    return AccountResponse(
        id=account.id,
        name=account.name,
        type=account.type,
        scope=account.scope,
        balance_cents=balance_cents,
        bank_connection_id=account.bank_connection_id,
        bank_account_mask=account.bank_account_mask,
        institution_name=institution_name,
    )


@router.get("", response_model=list[AccountResponse])
async def list_accounts(db: DbSession, current_user: CurrentUser) -> list[AccountResponse]:
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

    connection_ids = {a.bank_connection_id for a in accounts if a.bank_connection_id is not None}
    connections_by_id: dict[int, BankConnection] = {}
    if connection_ids:
        connections_by_id = {
            c.id: c
            for c in (
                await db.execute(
                    select(BankConnection).where(BankConnection.id.in_(connection_ids))
                )
            ).scalars().all()
        }

    responses: list[AccountResponse] = []
    for a in accounts:
        institution_name = None
        if a.bank_connection_id is not None:
            connection = connections_by_id.get(a.bank_connection_id)
            if connection is not None:
                institution_name = connection.aspsp_name
        responses.append(
            AccountResponse(
                id=a.id,
                name=a.name,
                type=a.type,
                scope=a.scope,
                balance_cents=totals.get(a.id, 0),
                bank_connection_id=a.bank_connection_id,
                bank_account_mask=a.bank_account_mask,
                institution_name=institution_name,
            )
        )
    return responses


@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    payload: AccountCreate, db: DbSession, current_user: CurrentUser
) -> AccountResponse:
    account = Account(
        user_id=current_user.id,
        name=payload.name,
        type=payload.type,
        scope=payload.scope,
    )
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return _to_response(account, 0)


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
        # Manual users can change type freely; linked accounts shouldn't
        # have their bank-derived type overwritten.
        if account.bank_connection_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Linked account type is managed by the bank and cannot be changed.",
            )
        account.type = payload.type
    if payload.scope is not None and payload.scope != account.scope:
        # Categorized transactions on this account would land in the wrong
        # scope pool after the change (a personal-group category attached to
        # a now-shared account, or vice versa). Require the user to
        # uncategorize them first. Uncategorized inflows shift cleanly.
        categorized = await db.scalar(
            select(Transaction.id)
            .where(
                Transaction.account_id == account.id,
                Transaction.category_id.is_not(None),
            )
            .limit(1)
        )
        if categorized is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Cannot change scope on an account with categorized "
                    "transactions. Uncategorize them first."
                ),
            )
        account.scope = payload.scope
    await db.commit()
    await db.refresh(account)

    total = await db.scalar(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            Transaction.account_id == account.id
        )
    )
    institution_name: str | None = None
    if account.bank_connection_id is not None:
        connection = await db.get(BankConnection, account.bank_connection_id)
        if connection is not None:
            institution_name = connection.aspsp_name
    return _to_response(account, int(total or 0), institution_name)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(account_id: int, db: DbSession, current_user: CurrentUser) -> None:
    account = await _get_owned(db, current_user.id, account_id)
    if account.bank_connection_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Linked accounts must be unlinked via /api/banking/connections/{id}.",
        )
    await db.delete(account)
    await db.commit()
