from datetime import date

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.deps import CurrentUser, DbSession, owned_scope
from app.models import Account, BankConnection, Transaction
from app.schemas.account import AccountBalanceUpdate, AccountCreate, AccountResponse, AccountUpdate
from app.services.synthetic_payees import BALANCE_ADJUSTMENT_PAYEE

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


async def _get_owned(db, user_id: int, account_id: int) -> Account:
    account = await db.get(Account, account_id)
    if account is None or account.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    return account


async def _account_total(db, account_id: int) -> int:
    total = await db.scalar(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            Transaction.account_id == account_id
        )
    )
    return int(total or 0)


async def _institution_name(db, account: Account) -> str | None:
    if account.bank_connection_id is None:
        return None
    connection = await db.get(BankConnection, account.bank_connection_id)
    return connection.aspsp_name if connection is not None else None


def _to_response(
    account: Account, balance_cents: int, institution_name: str | None = None
) -> AccountResponse:
    return AccountResponse(
        id=account.id,
        name=account.name,
        type=account.type,
        scope_id=account.scope_id,
        balance_cents=balance_cents,
        closed=account.closed,
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
                scope_id=a.scope_id,
                balance_cents=totals.get(a.id, 0),
                closed=a.closed,
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
    await owned_scope(db, current_user.id, payload.scope_id)
    account = Account(
        user_id=current_user.id,
        name=payload.name,
        type=payload.type,
        scope_id=payload.scope_id,
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
    if payload.scope_id is not None and payload.scope_id != account.scope_id:
        # Categorized transactions on this account would land in the wrong
        # scope pool after the change (a category from one scope's group
        # attached to an account now in another). Require the user to
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
        await owned_scope(db, current_user.id, payload.scope_id)
        account.scope_id = payload.scope_id
    if payload.closed is not None:
        account.closed = payload.closed
    await db.commit()
    await db.refresh(account)

    total = await _account_total(db, account.id)
    institution_name = await _institution_name(db, account)
    return _to_response(account, total, institution_name)


@router.post("/{account_id}/balance", response_model=AccountResponse)
async def set_account_balance(
    account_id: int,
    payload: AccountBalanceUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> AccountResponse:
    """Reconcile the derived balance to a user-supplied figure.

    Balances are never stored directly — this inserts a single uncategorized
    transaction for the delta, the same mechanism a manual account's balance
    is normally set by. Works for linked accounts too: an account can drift
    from the bank between syncs and may need a manual nudge.
    """
    account = await _get_owned(db, current_user.id, account_id)
    current_total = await _account_total(db, account.id)
    delta = payload.balance_cents - current_total
    if delta != 0:
        db.add(
            Transaction(
                user_id=current_user.id,
                account_id=account.id,
                date=date.today(),
                payee=BALANCE_ADJUSTMENT_PAYEE,
                memo="Manual balance correction",
                amount_cents=delta,
            )
        )
        await db.commit()

    institution_name = await _institution_name(db, account)
    return _to_response(account, payload.balance_cents, institution_name)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(account_id: int, db: DbSession, current_user: CurrentUser) -> None:
    account = await _get_owned(db, current_user.id, account_id)
    if account.bank_connection_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Linked accounts must be unlinked via /api/banking/connections/{id}.",
        )
    # Deleting cascades to the account's transactions, silently rewriting every
    # budget month they appear in. Closing keeps the history and hides the row.
    has_transactions = await db.scalar(
        select(Transaction.id).where(Transaction.account_id == account.id).limit(1)
    )
    if has_transactions is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account has transactions. Close it instead of deleting it.",
        )
    await db.delete(account)
    await db.commit()
