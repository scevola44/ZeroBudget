from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models import Account, Category, CategoryGroup, Transaction
from app.schemas.transaction import (
    PayeeTransferSuggestion,
    TransactionCreate,
    TransactionImportRequest,
    TransactionImportResponse,
    TransactionResponse,
    TransactionUpdate,
    TransferCandidate,
    TransferCreate,
    TransferLinkRequest,
    TransferResponse,
    TransferSuggestion,
)
from app.services.budget_calc import month_start, next_month_start, parse_month
from app.services.category_suggest import PayeeHistoryRow, suggest_categories
from app.services.transfer_match import (
    SUGGESTION_DEFAULT_DAYS,
    TRANSFER_MATCH_WINDOW_DAYS,
    AccountRef,
    MatchRow,
    find_candidates,
    suggest_pairs,
    suggest_payee_matched_transfers,
)
from app.services.txn_rows import load_peer_account_ids

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

# For rows that cannot be transfer legs, so ``_to_response`` has nothing to look up.
NO_PEER_ACCOUNTS: dict[int, int] = {}


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


def _to_response(txn: Transaction, peer_accounts: dict[int, int]) -> TransactionResponse:
    response = TransactionResponse.model_validate(txn)
    if txn.transfer_peer_id is not None:
        response.transfer_peer_account_id = peer_accounts.get(txn.transfer_peer_id)
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
    peer_accounts = await load_peer_account_ids(db, rows)
    return [_to_response(r, peer_accounts) for r in rows]


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


@router.get("/transfer-payee-suggestions", response_model=list[PayeeTransferSuggestion])
async def list_transfer_payee_suggestions(
    db: DbSession,
    current_user: CurrentUser,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
) -> list[PayeeTransferSuggestion]:
    """Rows whose payee names an account with nothing synced into it.

    A bank sync can only write both legs of a transfer when both accounts are
    connected — an unsynced account will never get its half, so
    ``transfer-suggestions`` (amount+date pairing) has nothing to find there.
    When the payee itself names that account, that's confirmation enough to
    offer creating the missing leg directly, one click, never automatically.
    """
    resolved_end = end_date or date.today()
    resolved_start = start_date or resolved_end - timedelta(days=SUGGESTION_DEFAULT_DAYS)
    rows = await _linkable_rows_between(db, current_user.id, resolved_start, resolved_end)
    by_id = {row.id: row for row in rows}
    match_rows = [_to_match_row(row) for row in rows]

    accounts_result = await db.execute(
        select(Account).where(Account.user_id == current_user.id, Account.closed.is_(False))
    )
    accounts = [
        AccountRef(id=a.id, name=a.name, is_unsynced=a.bank_connection_id is None)
        for a in accounts_result.scalars().all()
    ]
    account_names = {a.id: a.name for a in accounts}

    claimed_ids = {
        row_id
        for pair in suggest_pairs(match_rows)
        for row_id in (pair.outflow_id, pair.inflow_id)
    }
    suggestions = suggest_payee_matched_transfers(match_rows, accounts, claimed_ids)
    return [
        PayeeTransferSuggestion(
            transaction=_to_response(by_id[s.transaction_id], NO_PEER_ACCOUNTS),
            to_account_id=s.to_account_id,
            to_account_name=account_names[s.to_account_id],
        )
        for s in suggestions
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
    if (payload.peer_transaction_id is None) == (payload.to_account_id is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide exactly one of peer_transaction_id or to_account_id.",
        )
    if payload.peer_transaction_id is not None:
        peer = await _owned_transaction(db, current_user.id, payload.peer_transaction_id)
    else:
        target_account = await _owned_account(db, current_user.id, payload.to_account_id)
        peer = Transaction(
            user_id=current_user.id,
            account_id=target_account.id,
            category_id=None,
            date=txn.date,
            payee=txn.payee,
            memo=txn.memo,
            amount_cents=-txn.amount_cents,
        )
        db.add(peer)
        await db.flush()
    _reject_unlinkable_pair(txn, peer)

    # A transfer isn't spending, so neither leg keeps a category — the invariant
    # create_transfer starts from and update_transaction defends. Clearing one
    # here is the honest completion of "this was never an expense", which is
    # what the user just said. Same for is_ready_to_assign: a transfer leg
    # can't carry it either.
    txn.category_id = None
    txn.is_ready_to_assign = False
    peer.category_id = None
    peer.is_ready_to_assign = False
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
    if payload.category_id is not None and payload.is_ready_to_assign:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A transaction cannot be both categorized and marked Ready to Assign.",
        )
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
        is_ready_to_assign=payload.is_ready_to_assign,
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
    if peer is not None and payload.is_ready_to_assign:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A transfer leg cannot be marked Ready to Assign. Delete the transfer instead.",
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
    if payload.is_ready_to_assign is not None:
        txn.is_ready_to_assign = payload.is_ready_to_assign
    # Catches cross-field conflicts a single-field PATCH can't see on its own:
    # setting is_ready_to_assign on a row that already has a category, or
    # setting a category on a row that's already flagged. No implicit
    # auto-clearing either way — the caller must state its full intent.
    if txn.category_id is not None and txn.is_ready_to_assign:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A transaction cannot be both categorized and marked Ready to Assign.",
        )
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
    return _to_response(txn, await load_peer_account_ids(db, [txn]))


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
