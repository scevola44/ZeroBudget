from datetime import date
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models import Account, Category, CategoryGroup, Transaction
from app.schemas.transaction import (
    TransactionCreate,
    TransactionImportRequest,
    TransactionImportResponse,
    TransactionResponse,
    TransactionUpdate,
    TransferCreate,
    TransferResponse,
)
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
    group scope. Cross-scope movement must go through a transfer.
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
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> list[TransactionResponse]:
    stmt = select(Transaction).where(Transaction.user_id == current_user.id)
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    if month is not None:
        start = month_start(parse_month(month))
        end = next_month_start(start)
        stmt = stmt.where(Transaction.date >= start, Transaction.date < end)
    if start_date is not None:
        stmt = stmt.where(Transaction.date >= start_date)
    if end_date is not None:
        stmt = stmt.where(Transaction.date <= end_date)
    stmt = stmt.order_by(Transaction.date.desc(), Transaction.id.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return [TransactionResponse.model_validate(r) for r in rows]


@router.post("/import-ynab", response_model=TransactionImportResponse)
async def import_transactions_from_ynab(
    payload: TransactionImportRequest, db: DbSession, current_user: CurrentUser
) -> TransactionImportResponse:
    accounts_result = await db.execute(
        select(Account).where(Account.user_id == current_user.id)
    )
    accounts_by_id: dict[int, Account] = {a.id: a for a in accounts_result.scalars().all()}

    cats_result = await db.execute(
        select(Category, CategoryGroup)
        .join(CategoryGroup, Category.group_id == CategoryGroup.id)
        .where(Category.user_id == current_user.id)
    )
    cats_by_id: dict[int, tuple[Category, CategoryGroup]] = {
        cat.id: (cat, grp) for cat, grp in cats_result.all()
    }

    transactions: list[Transaction] = []
    for row in payload.rows:
        account = accounts_by_id.get(row.account_id)
        if account is None:
            continue

        category_id = row.category_id
        if category_id is not None:
            cat_entry = cats_by_id.get(category_id)
            if cat_entry is None or cat_entry[1].scope != account.scope:
                category_id = None

        transactions.append(
            Transaction(
                user_id=current_user.id,
                account_id=row.account_id,
                category_id=category_id,
                date=row.date,
                payee=row.payee,
                memo=row.memo,
                amount_cents=row.amount_cents,
            )
        )

    db.add_all(transactions)
    await db.commit()
    return TransactionImportResponse(imported=len(transactions))


@router.post(
    "/transfer", response_model=TransferResponse, status_code=status.HTTP_201_CREATED
)
async def create_transfer(
    payload: TransferCreate, db: DbSession, current_user: CurrentUser
) -> TransferResponse:
    """Create both legs of a transfer atomically, linked to each other.

    Legs are always uncategorized: a transfer isn't spending. Whether it moves
    Ready to Assign depends on the two accounts' scopes — see
    ``budget_calc.feeds_ready_to_assign``.
    """
    if payload.from_account_id == payload.to_account_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A transfer needs two different accounts.",
        )
    await _owned_account(db, current_user.id, payload.from_account_id)
    await _owned_account(db, current_user.id, payload.to_account_id)

    def _leg(account_id: int, amount_cents: int) -> Transaction:
        return Transaction(
            user_id=current_user.id,
            account_id=account_id,
            category_id=None,
            date=payload.date,
            payee=payload.payee,
            memo=payload.memo,
            amount_cents=amount_cents,
        )

    outflow = _leg(payload.from_account_id, -payload.amount_cents)
    inflow = _leg(payload.to_account_id, payload.amount_cents)
    # Two flushes: each leg needs the other's primary key, and neither exists
    # until it is flushed.
    db.add(outflow)
    await db.flush()
    inflow.transfer_peer_id = outflow.id
    db.add(inflow)
    await db.flush()
    outflow.transfer_peer_id = inflow.id
    await db.commit()
    await db.refresh(outflow)
    await db.refresh(inflow)

    return TransferResponse(
        from_transaction=TransactionResponse.model_validate(outflow),
        to_transaction=TransactionResponse.model_validate(inflow),
    )


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
    peer = (
        await db.get(Transaction, txn.transfer_peer_id)
        if txn.transfer_peer_id is not None
        else None
    )

    if peer is not None and payload.category_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A transfer leg cannot be categorized. Delete the transfer instead.",
        )

    if payload.account_id is not None:
        await _owned_account(db, current_user.id, payload.account_id)
        if peer is not None and payload.account_id == peer.account_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Both legs of a transfer cannot sit in the same account.",
            )
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

    if peer is not None:
        # Date and amount define the transfer itself and must agree across the
        # pair; payee and memo are per-leg annotations and stay where typed.
        if payload.date is not None:
            peer.date = payload.date
        if payload.amount_cents is not None:
            peer.amount_cents = -payload.amount_cents

    await db.commit()
    await db.refresh(txn)
    return TransactionResponse.model_validate(txn)


@router.delete("/{txn_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    txn_id: int, db: DbSession, current_user: CurrentUser
) -> None:
    txn = await _owned_transaction(db, current_user.id, txn_id)
    if txn.transfer_peer_id is not None:
        # Half a transfer is never a meaningful record: drop the pair. Break the
        # links first so neither delete trips the other's foreign key.
        peer = await db.get(Transaction, txn.transfer_peer_id)
        txn.transfer_peer_id = None
        if peer is not None:
            peer.transfer_peer_id = None
            await db.flush()
            await db.delete(peer)
    await db.delete(txn)
    await db.commit()
