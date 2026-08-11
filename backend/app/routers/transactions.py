from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.deps import CurrentUser, DbSession
from app.models import Account, Category, CategoryGroup, Transaction, TransactionSplit
from app.schemas.transaction import (
    BulkCategoryRequest,
    BulkCategoryResponse,
    BulkDeleteRequest,
    BulkDeleteResponse,
    TransactionCreate,
    TransactionImportRequest,
    TransactionImportResponse,
    TransactionListResponse,
    TransactionResponse,
    TransactionSplitInput,
    TransactionSplitResponse,
    TransactionUpdate,
    TransferCandidate,
    TransferCreate,
    TransferLinkRequest,
    TransferResponse,
    TransferSuggestion,
)
from app.services.budget_calc import month_start, next_month_start, parse_month
from app.services.category_suggest import PayeeHistoryRow, suggest_categories
from app.services.payees import resolve_payee
from app.services.transfer_match import (
    SUGGESTION_DEFAULT_DAYS,
    TRANSFER_MATCH_WINDOW_DAYS,
    MatchRow,
    find_candidates,
    suggest_pairs,
)
from app.services.txn_rows import load_peer_account_ids, load_splits_by_transaction_id

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

# For rows that cannot be transfer legs, so ``_to_response`` has nothing to look up.
NO_PEER_ACCOUNTS: dict[int, int] = {}
# For rows known to have no splits (transfer legs, new rows before their own
# splits are written), so ``_to_response`` has nothing to look up.
NO_SPLITS: dict[int, list[TransactionSplit]] = {}


def _to_match_row(txn: Transaction) -> MatchRow:
    return MatchRow(
        id=txn.id,
        account_id=txn.account_id,
        category_id=txn.category_id,
        date=txn.date,
        amount_cents=txn.amount_cents,
        payee=txn.payee,
        transfer_peer_id=txn.transfer_peer_id,
    )


def _splits_to_response(splits: list[TransactionSplit]) -> list[TransactionSplitResponse]:
    return [
        TransactionSplitResponse(
            id=s.id, category_id=s.category_id, amount_cents=s.amount_cents, memo=s.memo
        )
        for s in splits
    ]


def _to_response(
    txn: Transaction,
    peer_accounts: dict[int, int],
    splits_by_txn_id: dict[int, list[TransactionSplit]] = NO_SPLITS,
) -> TransactionResponse:
    response = TransactionResponse.model_validate(txn)
    if txn.transfer_peer_id is not None:
        response.transfer_peer_account_id = peer_accounts.get(txn.transfer_peer_id)
    response.splits = _splits_to_response(splits_by_txn_id.get(txn.id, []))
    return response


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


def _validate_splits(splits: list[TransactionSplitInput], final_amount_cents: int) -> None:
    """Enforce the shape a set of split lines must have, independent of ownership.

    A single-line "split" is just a categorized transaction, so two lines is
    the floor. Amounts must sum exactly to the parent — the budget treats a
    split transaction as its lines, not its total, so any mismatch would be
    money the math silently drops or invents.
    """
    if len(splits) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A split needs at least two lines.",
        )
    if any(s.amount_cents == 0 for s in splits):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Split lines cannot be zero.",
        )
    total = sum(s.amount_cents for s in splits)
    if total != final_amount_cents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Split lines must sum to the transaction amount "
                f"({final_amount_cents} cents), got {total}."
            ),
        )


async def _has_splits(db, txn_id: int) -> bool:
    return (
        await db.scalar(
            select(TransactionSplit.id).where(TransactionSplit.transaction_id == txn_id).limit(1)
        )
    ) is not None


DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500


@router.get("", response_model=TransactionListResponse)
async def list_transactions(
    db: DbSession,
    current_user: CurrentUser,
    account_id: list[int] | None = Query(
        default=None, description="Repeatable: ?account_id=1&account_id=2"
    ),
    category_id: int | None = Query(
        default=None, description="Matches a plain category_id or any split line's"
    ),
    uncategorized: bool = Query(
        default=False, description="Parent category_id is NULL and it has no splits"
    ),
    q: str | None = Query(default=None, description="Case-insensitive match on payee or memo"),
    month: str | None = Query(default=None, description="YYYY-MM"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
) -> TransactionListResponse:
    filters = [Transaction.user_id == current_user.id]
    if account_id:
        filters.append(Transaction.account_id.in_(account_id))
    if month is not None:
        start = month_start(parse_month(month))
        end = next_month_start(start)
        filters.append(Transaction.date >= start)
        filters.append(Transaction.date < end)
    if start_date is not None:
        filters.append(Transaction.date >= start_date)
    if end_date is not None:
        filters.append(Transaction.date <= end_date)

    has_splits = (
        select(TransactionSplit.id)
        .where(TransactionSplit.transaction_id == Transaction.id)
        .exists()
    )
    if uncategorized:
        filters.append(Transaction.category_id.is_(None))
        filters.append(~has_splits)
    elif category_id is not None:
        split_has_category = (
            select(TransactionSplit.id)
            .where(
                TransactionSplit.transaction_id == Transaction.id,
                TransactionSplit.category_id == category_id,
            )
            .exists()
        )
        filters.append(or_(Transaction.category_id == category_id, split_has_category))
    if q:
        pattern = f"%{q}%"
        filters.append(or_(Transaction.payee.ilike(pattern), Transaction.memo.ilike(pattern)))

    total = await db.scalar(select(func.count()).select_from(Transaction).where(*filters))
    stmt = (
        select(Transaction)
        .where(*filters)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).scalars().all()
    peer_accounts = await load_peer_account_ids(db, rows)
    splits_by_txn_id = await load_splits_by_transaction_id(db, rows)
    return TransactionListResponse(
        items=[_to_response(r, peer_accounts, splits_by_txn_id) for r in rows],
        total=total or 0,
    )


@router.get("/category-suggestions", response_model=list[int])
async def suggest_transaction_categories(
    db: DbSession,
    current_user: CurrentUser,
    payee: str = Query(...),
    account_id: int = Query(...),
) -> list[int]:
    """Category ids to propose for ``payee``, best guess first.

    History spans every account the user owns — a payee is the same
    real-world entity no matter which account paid it — but is narrowed to
    categories whose group scope matches ``account_id``'s scope, since a
    mismatched-scope category would be rejected by ``_enforce_scope_match``
    anyway.
    """
    account = await _owned_account(db, current_user.id, account_id)
    if not payee.strip():
        return []

    cats_result = await db.execute(
        select(Category.id, CategoryGroup.scope)
        .join(CategoryGroup, Category.group_id == CategoryGroup.id)
        .where(Category.user_id == current_user.id)
    )
    scope_by_category_id = dict(cats_result.all())

    history_result = await db.execute(
        select(Transaction.id, Transaction.payee, Transaction.category_id, Transaction.date)
        .where(
            Transaction.user_id == current_user.id,
            Transaction.category_id.is_not(None),
        )
    )
    rows = [
        PayeeHistoryRow(id=row.id, payee=row.payee, category_id=row.category_id, date=row.date)
        for row in history_result.all()
        if scope_by_category_id.get(row.category_id) == account.scope
    ]

    return suggest_categories(payee, rows)


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
                payee_id=await resolve_payee(db, current_user.id, row.payee),
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
    payee_id = await resolve_payee(db, current_user.id, payload.payee)

    def _leg(account_id: int, amount_cents: int) -> Transaction:
        return Transaction(
            user_id=current_user.id,
            account_id=account_id,
            category_id=None,
            date=payload.date,
            payee=payload.payee,
            payee_id=payee_id,
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

    peer_accounts = {outflow.id: outflow.account_id, inflow.id: inflow.account_id}
    return TransferResponse(
        from_transaction=_to_response(outflow, peer_accounts),
        to_transaction=_to_response(inflow, peer_accounts),
    )


async def _linkable_rows_between(
    db, user_id: int, start_date: date, end_date: date
) -> list[Transaction]:
    """Unlinked transactions in a date window, the raw material for matching.

    Narrowed in SQL only by ownership and date — both indexed, and both purely
    about not loading the whole ledger. Which of these rows actually pair is
    ``transfer_match``'s call alone, so the rule lives in exactly one place.
    """
    stmt = select(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.transfer_peer_id.is_(None),
        Transaction.date >= start_date,
        Transaction.date <= end_date,
    )
    return list((await db.execute(stmt)).scalars().all())


@router.get("/transfer-candidates", response_model=list[TransferCandidate])
async def list_transfer_candidates(
    db: DbSession,
    current_user: CurrentUser,
    transaction_id: int = Query(..., description="The leg being linked"),
    account_id: int | None = Query(
        default=None, description="Restrict to the other leg's account"
    ),
) -> list[TransferCandidate]:
    """Transactions that could be ``transaction_id``'s other leg, best first."""
    target = await _owned_transaction(db, current_user.id, transaction_id)
    window = timedelta(days=TRANSFER_MATCH_WINDOW_DAYS)
    rows = await _linkable_rows_between(
        db, current_user.id, target.date - window, target.date + window
    )
    by_id = {row.id: row for row in rows}
    if account_id is not None:
        rows = [row for row in rows if row.account_id == account_id]

    matches = find_candidates(_to_match_row(target), [_to_match_row(r) for r in rows])
    # Candidates are unlinked by definition, so none of them has a peer account
    # to denormalize.
    return [
        TransferCandidate(
            transaction=_to_response(by_id[match.id], NO_PEER_ACCOUNTS),
            date_offset_days=(match.date - target.date).days,
        )
        for match in matches
    ]


@router.get("/transfer-suggestions", response_model=list[TransferSuggestion])
async def list_transfer_suggestions(
    db: DbSession,
    current_user: CurrentUser,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> list[TransferSuggestion]:
    """Pairs of imported rows that look like the two halves of one transfer.

    Only ever a suggestion: a sync writes each account's side independently and
    can't know they belong together, and neither can this — so the user confirms
    each pair. See ``transfer_match.suggest_pairs`` for what "look like" means.
    """
    resolved_end = end_date or date.today()
    resolved_start = start_date or resolved_end - timedelta(days=SUGGESTION_DEFAULT_DAYS)
    rows = await _linkable_rows_between(
        db, current_user.id, resolved_start, resolved_end
    )
    by_id = {row.id: row for row in rows}

    pairs = suggest_pairs([_to_match_row(row) for row in rows])
    return [
        TransferSuggestion(
            outflow=_to_response(by_id[pair.outflow_id], NO_PEER_ACCOUNTS),
            inflow=_to_response(by_id[pair.inflow_id], NO_PEER_ACCOUNTS),
        )
        for pair in pairs
    ]


def _reject_unlinkable_pair(txn: Transaction, peer: Transaction) -> None:
    """Guard the invariants a linked pair must satisfy for the budget to add up.

    Only the hard ones: the softer rules in ``transfer_match.is_linkable`` keep
    the *suggestion* list quiet, but linking is an explicit instruction and the
    user is allowed to overrule what the matcher would have volunteered.
    """
    if txn.id == peer.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A transfer needs two different transactions.",
        )
    if txn.account_id == peer.account_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Both legs of a transfer cannot sit in the same account.",
        )
    for leg in (txn, peer):
        if leg.transfer_peer_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That transaction is already part of a transfer.",
            )
    if txn.amount_cents == 0 or txn.amount_cents != -peer.amount_cents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "A transfer's two legs must be equal and opposite, but these are "
                f"{txn.amount_cents} and {peer.amount_cents} cents."
            ),
        )


@router.post("/{txn_id}/transfer-link", response_model=TransferResponse)
async def link_transfer(
    txn_id: int,
    payload: TransferLinkRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> TransferResponse:
    """Mark ``txn_id`` as one leg of a transfer, with the other leg either
    already existing or created here.

    This is the imported case. A bank sync fetches each account separately, so a
    real transfer lands as two unrelated rows; ``create_transfer`` is no help
    because it makes *two new* legs, and deleting the imported row to retype it
    by hand throws away the bank's own reference and invites the next sync to
    re-import it. ``peer_transaction_id`` links to that other imported row when
    it exists. ``to_account_id`` covers the account that will never have one —
    an account with no bank connection has nothing for a sync to write there,
    so the missing leg is created instead of searched for.
    """
    txn = await _owned_transaction(db, current_user.id, txn_id)
    if await _has_splits(db, txn.id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A split transaction cannot be linked as a transfer leg.",
        )
    if (payload.peer_transaction_id is None) == (payload.to_account_id is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide exactly one of peer_transaction_id or to_account_id.",
        )
    if payload.peer_transaction_id is not None:
        peer = await _owned_transaction(db, current_user.id, payload.peer_transaction_id)
        if await _has_splits(db, peer.id):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A split transaction cannot be linked as a transfer leg.",
            )
    else:
        target_account = await _owned_account(db, current_user.id, payload.to_account_id)
        peer = Transaction(
            user_id=current_user.id,
            account_id=target_account.id,
            category_id=None,
            date=txn.date,
            payee=txn.payee,
            payee_id=txn.payee_id,
            memo=txn.memo,
            amount_cents=-txn.amount_cents,
        )
        db.add(peer)
        await db.flush()
    _reject_unlinkable_pair(txn, peer)

    # A transfer isn't spending, so neither leg keeps a category — the invariant
    # create_transfer starts from and update_transaction defends. Clearing one
    # here is the honest completion of "this was never an expense", which is
    # what the user just said.
    txn.category_id = None
    peer.category_id = None
    txn.transfer_peer_id = peer.id
    peer.transfer_peer_id = txn.id
    await db.commit()
    await db.refresh(txn)
    await db.refresh(peer)

    outflow, inflow = (txn, peer) if txn.amount_cents < 0 else (peer, txn)
    peer_accounts = {outflow.id: outflow.account_id, inflow.id: inflow.account_id}
    return TransferResponse(
        from_transaction=_to_response(outflow, peer_accounts),
        to_transaction=_to_response(inflow, peer_accounts),
    )


@router.delete("/{txn_id}/transfer-link", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_transfer(
    txn_id: int, db: DbSession, current_user: CurrentUser
) -> None:
    """Break a transfer pair, keeping both transactions.

    ``DELETE /{txn_id}`` drops both legs, which is right for a transfer the user
    typed but wrong for two the bank imported — those are real records that the
    next sync would re-import anyway. Unlinking leaves two ordinary
    uncategorized rows behind.
    """
    txn = await _owned_transaction(db, current_user.id, txn_id)
    if txn.transfer_peer_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That transaction isn't part of a transfer.",
        )
    peer = await db.get(Transaction, txn.transfer_peer_id)
    txn.transfer_peer_id = None
    if peer is not None:
        peer.transfer_peer_id = None
    await db.commit()


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    payload: TransactionCreate, db: DbSession, current_user: CurrentUser
) -> TransactionResponse:
    await _owned_account(db, current_user.id, payload.account_id)
    has_splits = bool(payload.splits)
    if has_splits and payload.category_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot both categorize and split a transaction.",
        )
    if payload.category_id is not None:
        await _owned_category(db, current_user.id, payload.category_id)
    await _enforce_scope_match(
        db, current_user.id, payload.account_id, payload.category_id
    )
    if has_splits:
        _validate_splits(payload.splits, payload.amount_cents)
        for s in payload.splits:
            if s.category_id is not None:
                await _owned_category(db, current_user.id, s.category_id)
            await _enforce_scope_match(db, current_user.id, payload.account_id, s.category_id)

    txn = Transaction(
        user_id=current_user.id,
        account_id=payload.account_id,
        category_id=None if has_splits else payload.category_id,
        date=payload.date,
        payee=payload.payee,
        payee_id=await resolve_payee(db, current_user.id, payload.payee),
        memo=payload.memo,
        amount_cents=payload.amount_cents,
    )
    db.add(txn)
    await db.flush()

    new_splits: list[TransactionSplit] = []
    if has_splits:
        new_splits = [
            TransactionSplit(
                user_id=current_user.id,
                transaction_id=txn.id,
                category_id=s.category_id,
                amount_cents=s.amount_cents,
                memo=s.memo,
            )
            for s in payload.splits
        ]
        db.add_all(new_splits)
        await db.flush()

    await db.commit()
    await db.refresh(txn)
    response = TransactionResponse.model_validate(txn)
    response.splits = _splits_to_response(new_splits)
    return response


async def _delete_with_peer(db, txn: Transaction) -> int:
    """Delete ``txn``, and its transfer peer too if it has one.

    Shared by the single and bulk delete endpoints so transfer-pair
    consistency (half a transfer is never a meaningful record) can't drift
    between the two paths. Returns the number of rows actually removed (1 or
    2), so a bulk delete can report an accurate count.
    """
    removed = 1
    if txn.transfer_peer_id is not None:
        # Break the links first so neither delete trips the other's foreign key.
        peer = await db.get(Transaction, txn.transfer_peer_id)
        txn.transfer_peer_id = None
        if peer is not None:
            peer.transfer_peer_id = None
            await db.flush()
            await db.delete(peer)
            removed = 2
    await db.delete(txn)
    return removed


# Registered ahead of the "/{txn_id}" routes below: FastAPI matches routes in
# declaration order, and "bulk-category"/"bulk-delete" would otherwise be
# captured by "{txn_id}" first and fail int conversion instead of reaching
# these handlers.
@router.patch("/bulk-category", response_model=BulkCategoryResponse)
async def bulk_set_category(
    payload: BulkCategoryRequest, db: DbSession, current_user: CurrentUser
) -> BulkCategoryResponse:
    """Set the same category on many transactions at once, all-or-nothing.

    Ids that don't belong to the user are silently dropped (the UI never
    hands us one it didn't itself list); every id that *is* owned must pass
    every check before anything is written, so a bad row in the middle of a
    big selection can't leave the batch half-applied.
    """
    txns: list[Transaction] = []
    for txn_id in payload.transaction_ids:
        txn = await db.get(Transaction, txn_id)
        if txn is None or txn.user_id != current_user.id:
            continue
        txns.append(txn)

    if payload.category_id is not None:
        await _owned_category(db, current_user.id, payload.category_id)

    for txn in txns:
        if txn.transfer_peer_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Transaction {txn.id} is a transfer leg and cannot be categorized.",
            )
        if await _has_splits(db, txn.id):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Transaction {txn.id} is split and cannot be bulk-categorized.",
            )
        await _enforce_scope_match(db, current_user.id, txn.account_id, payload.category_id)

    for txn in txns:
        txn.category_id = payload.category_id

    await db.commit()
    return BulkCategoryResponse(updated=len(txns))


@router.post("/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_transactions(
    payload: BulkDeleteRequest, db: DbSession, current_user: CurrentUser
) -> BulkDeleteResponse:
    """Delete many transactions at once. Ids that don't belong to the user
    are silently dropped. Deleting one leg of a transfer pair drops both, same
    as the single-delete endpoint — ``deleted`` counts actual rows removed, so
    a pair counts as 2 even if only one leg's id was in the request."""
    deleted = 0
    already_deleted: set[int] = set()
    for txn_id in payload.transaction_ids:
        if txn_id in already_deleted:
            continue
        txn = await db.get(Transaction, txn_id)
        if txn is None or txn.user_id != current_user.id:
            continue
        peer_id = txn.transfer_peer_id
        deleted += await _delete_with_peer(db, txn)
        already_deleted.add(txn_id)
        if peer_id is not None:
            already_deleted.add(peer_id)
    await db.commit()
    return BulkDeleteResponse(deleted=deleted)


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

    splits_touched = "splits" in payload.model_fields_set
    new_split_inputs = (payload.splits or []) if splits_touched else []
    has_new_splits = splits_touched and len(new_split_inputs) > 0

    if has_new_splits and peer is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A transfer leg cannot be split.",
        )
    if has_new_splits and payload.category_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot both categorize and split a transaction.",
        )
    if (
        payload.category_id is not None
        and not splits_touched
        and await _has_splits(db, txn.id)
    ):
        # Setting category_id without touching splits would otherwise leave a
        # split transaction with a non-null parent category — the invariant
        # every other write path defends. Clear or replace the splits first.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This transaction is split — clear its splits before setting a single category.",
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
    if has_new_splits:
        # Splits imply an uncategorized parent, regardless of what the
        # category_id field said (or didn't say) above.
        txn.category_id = None
    # Re-check scope match against the merged (account_id, category_id) pair.
    await _enforce_scope_match(db, current_user.id, txn.account_id, txn.category_id)
    if payload.date is not None:
        txn.date = payload.date
    if payload.payee is not None:
        txn.payee = payload.payee
        txn.payee_id = await resolve_payee(db, current_user.id, payload.payee)
    if payload.memo is not None:
        txn.memo = payload.memo
    if payload.amount_cents is not None:
        txn.amount_cents = payload.amount_cents

    new_splits: list[TransactionSplit] = []
    if splits_touched:
        existing_splits = (
            (
                await db.execute(
                    select(TransactionSplit).where(TransactionSplit.transaction_id == txn.id)
                )
            )
            .scalars()
            .all()
        )
        for old in existing_splits:
            await db.delete(old)
        if has_new_splits:
            _validate_splits(new_split_inputs, txn.amount_cents)
            for s in new_split_inputs:
                if s.category_id is not None:
                    await _owned_category(db, current_user.id, s.category_id)
                await _enforce_scope_match(db, current_user.id, txn.account_id, s.category_id)
            new_splits = [
                TransactionSplit(
                    user_id=current_user.id,
                    transaction_id=txn.id,
                    category_id=s.category_id,
                    amount_cents=s.amount_cents,
                    memo=s.memo,
                )
                for s in new_split_inputs
            ]
            db.add_all(new_splits)
            await db.flush()
    else:
        # Not touched by this request, but the response must still reflect
        # whatever the row already has.
        new_splits = (
            (
                await db.execute(
                    select(TransactionSplit).where(TransactionSplit.transaction_id == txn.id)
                )
            )
            .scalars()
            .all()
        )

    # Amount is the one field that defines the transfer itself: the legs must
    # stay equal and opposite or the budget math, which excludes both rather
    # than summing them, starts inventing money.
    #
    # Date is deliberately *not* mirrored. Two legs linked from bank imports each
    # carry their own bank's booking date — money leaves on the 31st and lands on
    # the 2nd — and the edit modal submits every field on every save, so
    # mirroring would overwrite the peer's real date on an unrelated memo edit.
    # Payee and memo are per-leg for the same reason.
    if peer is not None and payload.amount_cents is not None:
        peer.amount_cents = -payload.amount_cents

    await db.commit()
    await db.refresh(txn)
    response = _to_response(txn, await load_peer_account_ids(db, [txn]))
    response.splits = _splits_to_response(new_splits)
    return response


@router.delete("/{txn_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    txn_id: int, db: DbSession, current_user: CurrentUser
) -> None:
    txn = await _owned_transaction(db, current_user.id, txn_id)
    await _delete_with_peer(db, txn)
    await db.commit()
