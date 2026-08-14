from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, delete, func, or_, select

from app.deps import CurrentUser, DbSession
from app.models import (
    Account,
    Category,
    CategoryGroup,
    DeletedExternalTransaction,
    Payee,
    PayeeCategoryRule,
    Scope,
    Transaction,
    TransactionSplit,
)
from app.schemas.transaction import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkSetCategoryRequest,
    BulkSetCategoryResponse,
    PayeeTransferSuggestion,
    TransactionCreate,
    TransactionImportRequest,
    TransactionImportResponse,
    TransactionPage,
    TransactionResponse,
    TransactionSplitInput,
    TransactionSplitResponse,
    TransactionUpdate,
    TransferCandidate,
    TransferCreate,
    TransferLinkRequest,
    TransferResponse,
    TransferSuggestion,
    UnassignedCountResponse,
)
from app.services.budget_calc import month_start, next_month_start, parse_month
from app.services.category_suggest import PayeeHistoryRow, suggest_categories
from app.services.payee_rules import CategoryRule, match_rule
from app.services.payees import resolve_payee
from app.services.transfer_match import (
    SUGGESTION_DEFAULT_DAYS,
    TRANSFER_MATCH_WINDOW_DAYS,
    AccountRef,
    MatchRow,
    find_candidates,
    suggest_pairs,
    suggest_payee_matched_transfers,
)
from app.services.txn_rows import (
    load_payee_names,
    load_peer_account_ids,
    load_splits_by_transaction_id,
)

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

# For rows that cannot be transfer legs, so ``_to_response`` has nothing to look up.
NO_PEER_ACCOUNTS: dict[int, int] = {}
# For call sites with no transactions to name (e.g. a freshly built peer leg
# that has no payee of its own yet).
NO_PAYEE_NAMES: dict[int, str] = {}
# For call sites that can never involve a split transaction (transfer legs,
# freshly created rows), so ``_to_response`` has nothing to look up.
NO_SPLITS: dict[int, list[TransactionSplit]] = {}


def _to_match_row(txn: Transaction, payee_names: dict[int, str]) -> MatchRow:
    return MatchRow(
        id=txn.id,
        account_id=txn.account_id,
        category_id=txn.category_id,
        date=txn.date,
        amount_cents=txn.amount_cents,
        payee=payee_names.get(txn.payee_id, "") if txn.payee_id is not None else "",
        transfer_peer_id=txn.transfer_peer_id,
    )


def _to_response(
    txn: Transaction,
    peer_accounts: dict[int, int],
    payee_names: dict[int, str],
    splits_by_txn_id: dict[int, list[TransactionSplit]] = NO_SPLITS,
) -> TransactionResponse:
    # Built field-by-field rather than TransactionResponse.model_validate(txn):
    # the ORM row no longer has a .payee attribute to auto-map (it carries
    # payee_id and needs the loaded name dict to become displayable text).
    return TransactionResponse(
        id=txn.id,
        account_id=txn.account_id,
        category_id=txn.category_id,
        is_ready_to_assign=txn.is_ready_to_assign,
        date=txn.date,
        payee=payee_names.get(txn.payee_id, "") if txn.payee_id is not None else "",
        payee_id=txn.payee_id,
        memo=txn.memo,
        amount_cents=txn.amount_cents,
        transfer_peer_id=txn.transfer_peer_id,
        transfer_peer_account_id=(
            peer_accounts.get(txn.transfer_peer_id)
            if txn.transfer_peer_id is not None
            else None
        ),
        splits=[
            TransactionSplitResponse.model_validate(s)
            for s in splits_by_txn_id.get(txn.id, [])
        ],
    )


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
    if group is None or group.scope_id != account.scope_id:
        # Names, not ids: this reaches the user. Loaded only on the failure
        # path, which is why it sits inside the branch.
        category_scope = await db.get(Scope, group.scope_id) if group else None
        account_scope = await db.get(Scope, account.scope_id)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Category scope ({category_scope.name if category_scope else '?'}) "
                f"does not match account scope ({account_scope.name}). "
                "Use a transfer instead."
            ),
        )


def _encode_cursor(txn_date: date, txn_id: int) -> str:
    return f"{txn_date.isoformat()}:{txn_id}"


def _decode_cursor(cursor: str) -> tuple[date, int]:
    try:
        date_part, id_part = cursor.split(":", 1)
        return date.fromisoformat(date_part), int(id_part)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed cursor."
        ) from exc


@router.get("", response_model=TransactionPage)
async def list_transactions(
    db: DbSession,
    current_user: CurrentUser,
    account_id: list[int] | None = Query(default=None),
    month: str | None = Query(default=None, description="YYYY-MM"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    category_id: int | None = Query(default=None),
    unassigned: bool = Query(default=False),
    ready_to_assign: bool = Query(default=False),
    q: str | None = Query(default=None, description="Free-text search over payee/memo"),
    limit: int | None = Query(default=None, ge=1, le=500),
    cursor: str | None = Query(default=None),
) -> TransactionPage:
    """List the user's transactions, newest first.

    Filters compose with AND. ``limit`` omitted returns every matching row
    unpaginated — the shape ``AccountDetailPage`` relies on, since it never
    sends ``limit``. Pagination is keyset on ``(date, id)`` (the query's own
    sort order), not offset: correct regardless of concurrent inserts, unlike
    offset paging on a list the user is actively editing.
    """
    stmt = select(Transaction).where(Transaction.user_id == current_user.id)
    if account_id:
        stmt = stmt.where(Transaction.account_id.in_(account_id))
    if month is not None:
        start = month_start(parse_month(month))
        end = next_month_start(start)
        stmt = stmt.where(Transaction.date >= start, Transaction.date < end)
    if start_date is not None:
        stmt = stmt.where(Transaction.date >= start_date)
    if end_date is not None:
        stmt = stmt.where(Transaction.date <= end_date)
    if category_id is not None:
        # A split parent's own category_id is always NULL, so matching only
        # that column would silently hide split transactions that have a
        # line in this category.
        has_split_category = (
            select(TransactionSplit.id)
            .where(
                TransactionSplit.transaction_id == Transaction.id,
                TransactionSplit.category_id == category_id,
            )
            .exists()
        )
        stmt = stmt.where(or_(Transaction.category_id == category_id, has_split_category))
    if unassigned:
        stmt = stmt.where(_needs_category_clause())
    if ready_to_assign:
        stmt = stmt.where(Transaction.is_ready_to_assign.is_(True))
    if q:
        stmt = stmt.outerjoin(Payee, Transaction.payee_id == Payee.id).where(
            or_(Payee.name.ilike(f"%{q}%"), Transaction.memo.ilike(f"%{q}%"))
        )
    if cursor is not None:
        cursor_date, cursor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Transaction.date < cursor_date,
                and_(Transaction.date == cursor_date, Transaction.id < cursor_id),
            )
        )
    stmt = stmt.order_by(Transaction.date.desc(), Transaction.id.desc())
    if limit is not None:
        # One extra row, never returned, just to know whether a next page exists.
        stmt = stmt.limit(limit + 1)

    rows = list((await db.execute(stmt)).scalars().all())

    next_cursor = None
    if limit is not None and len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = _encode_cursor(last.date, last.id)

    peer_accounts = await load_peer_account_ids(db, rows)
    payee_names = await load_payee_names(db, rows)
    splits_by_txn_id = await load_splits_by_transaction_id(db, rows)
    items = [_to_response(r, peer_accounts, payee_names, splits_by_txn_id) for r in rows]
    return TransactionPage(items=items, next_cursor=next_cursor)


def _needs_category_clause():
    """A transaction "needs a category" when its parent has none and it isn't
    split, or when it's split and at least one line has none — a split
    parent's own ``category_id`` is always NULL by design, so checking that
    alone would wrongly flag a fully-categorized split transaction."""
    has_any_split = (
        select(TransactionSplit.id)
        .where(TransactionSplit.transaction_id == Transaction.id)
        .exists()
    )
    has_null_split = (
        select(TransactionSplit.id)
        .where(
            TransactionSplit.transaction_id == Transaction.id,
            TransactionSplit.category_id.is_(None),
        )
        .exists()
    )
    return or_(
        and_(Transaction.category_id.is_(None), ~has_any_split),
        has_null_split,
    )


@router.get("/unassigned-count", response_model=UnassignedCountResponse)
async def count_unassigned_transactions(
    db: DbSession,
    current_user: CurrentUser,
) -> UnassignedCountResponse:
    # All-time, unlike list_transactions: a transaction left uncategorized
    # from a past month should still be flagged today.
    stmt = (
        select(func.count())
        .select_from(Transaction)
        .where(
            Transaction.user_id == current_user.id,
            _needs_category_clause(),
            Transaction.transfer_peer_id.is_(None),
            Transaction.is_ready_to_assign.is_(False),
        )
    )
    count = await db.scalar(stmt) or 0
    return UnassignedCountResponse(count=count)


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
        select(Category.id, CategoryGroup.scope_id)
        .join(CategoryGroup, Category.group_id == CategoryGroup.id)
        .where(Category.user_id == current_user.id)
    )
    scope_id_by_category_id = dict(cats_result.all())

    history_result = await db.execute(
        select(Transaction.id, Payee.name, Transaction.category_id, Transaction.date)
        .join(Payee, Transaction.payee_id == Payee.id)
        .where(
            Transaction.user_id == current_user.id,
            Transaction.category_id.is_not(None),
        )
    )
    rows = [
        PayeeHistoryRow(id=row.id, payee=row.name, category_id=row.category_id, date=row.date)
        for row in history_result.all()
        if scope_id_by_category_id.get(row.category_id) == account.scope_id
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
    category_scope_id = {cid: grp.scope_id for cid, (_cat, grp) in cats_by_id.items()}

    rules_result = await db.execute(
        select(PayeeCategoryRule)
        .where(PayeeCategoryRule.user_id == current_user.id)
        .order_by(PayeeCategoryRule.sort_order, PayeeCategoryRule.id)
    )
    rules = [
        CategoryRule(id=r.id, category_id=r.category_id, contains_text=r.contains_text)
        for r in rules_result.scalars().all()
    ]

    transactions: list[Transaction] = []
    for row in payload.rows:
        account = accounts_by_id.get(row.account_id)
        if account is None:
            continue

        category_id = row.category_id
        if category_id is not None:
            cat_entry = cats_by_id.get(category_id)
            if cat_entry is None or cat_entry[1].scope_id != account.scope_id:
                category_id = None

        # A rule only ever fills in a category the row arrived without —
        # never overrides one the import file already set.
        if category_id is None and rules:
            matched = match_rule(row.payee, rules)
            if matched is not None and category_scope_id.get(matched) == account.scope_id:
                category_id = matched

        payee = await resolve_payee(db, current_user.id, row.payee)

        transactions.append(
            Transaction(
                user_id=current_user.id,
                account_id=row.account_id,
                category_id=category_id,
                date=row.date,
                payee_id=payee.id if payee is not None else None,
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
    payee = await resolve_payee(db, current_user.id, payload.payee)

    def _leg(account_id: int, amount_cents: int) -> Transaction:
        return Transaction(
            user_id=current_user.id,
            account_id=account_id,
            category_id=None,
            date=payload.date,
            payee_id=payee.id if payee is not None else None,
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
    payee_names = {payee.id: payee.name} if payee is not None else {}
    return TransferResponse(
        from_transaction=_to_response(outflow, peer_accounts, payee_names),
        to_transaction=_to_response(inflow, peer_accounts, payee_names),
    )


async def _linkable_rows_between(
    db, user_id: int, start_date: date, end_date: date
) -> list[Transaction]:
    """Unlinked, unsplit transactions in a date window, the raw material for
    matching.

    Narrowed in SQL only by ownership, date and split status — all cheap
    filters that are purely about not loading the whole ledger and not
    offering rows that could never legally become a transfer leg. Which of
    the rest actually pair is ``transfer_match``'s call alone, so the rule
    lives in exactly one place. A split transaction is excluded outright: it
    already has its category-free line-items, and letting it become a
    transfer would require reasoning about splits inside every transfer
    response shape.
    """
    has_splits = (
        select(TransactionSplit.id)
        .where(TransactionSplit.transaction_id == Transaction.id)
        .exists()
    )
    stmt = select(Transaction).where(
        Transaction.user_id == user_id,
        Transaction.transfer_peer_id.is_(None),
        Transaction.date >= start_date,
        Transaction.date <= end_date,
        ~has_splits,
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
    payee_names = await load_payee_names(db, [target, *rows])

    matches = find_candidates(
        _to_match_row(target, payee_names), [_to_match_row(r, payee_names) for r in rows]
    )
    # Candidates are unlinked by definition, so none of them has a peer account
    # to denormalize.
    return [
        TransferCandidate(
            transaction=_to_response(by_id[match.id], NO_PEER_ACCOUNTS, payee_names),
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
    payee_names = await load_payee_names(db, rows)

    pairs = suggest_pairs([_to_match_row(row, payee_names) for row in rows])
    return [
        TransferSuggestion(
            outflow=_to_response(by_id[pair.outflow_id], NO_PEER_ACCOUNTS, payee_names),
            inflow=_to_response(by_id[pair.inflow_id], NO_PEER_ACCOUNTS, payee_names),
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
    payee_names = await load_payee_names(db, rows)
    match_rows = [_to_match_row(row, payee_names) for row in rows]

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
            transaction=_to_response(by_id[s.transaction_id], NO_PEER_ACCOUNTS, payee_names),
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
    payee_names = await load_payee_names(db, [outflow, inflow])
    return TransferResponse(
        from_transaction=_to_response(outflow, peer_accounts, payee_names),
        to_transaction=_to_response(inflow, peer_accounts, payee_names),
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


async def _validate_splits(
    db,
    user_id: int,
    account_id: int,
    amount_cents: int,
    splits: list[TransactionSplitInput],
) -> None:
    """Split-only invariants: at least two lines, and they sum to the parent
    amount. Each line's category (when set) goes through the same
    ownership + scope check a top-level category_id gets."""
    if len(splits) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A split needs at least two lines.",
        )
    if sum(s.amount_cents for s in splits) != amount_cents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Split amounts must sum to the transaction amount.",
        )
    for split in splits:
        await _enforce_scope_match(db, user_id, account_id, split.category_id)


async def _persist_splits(
    db, txn_id: int, splits: list[TransactionSplitInput]
) -> None:
    db.add_all(
        [
            TransactionSplit(
                transaction_id=txn_id,
                category_id=s.category_id,
                amount_cents=s.amount_cents,
                memo=s.memo,
            )
            for s in splits
        ]
    )


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    payload: TransactionCreate, db: DbSession, current_user: CurrentUser
) -> TransactionResponse:
    if payload.category_id is not None and payload.is_ready_to_assign:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A transaction cannot be both categorized and marked Ready to Assign.",
        )
    if payload.splits and payload.category_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A split transaction cannot also have a top-level category.",
        )
    if payload.splits and payload.is_ready_to_assign:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A split transaction cannot be marked Ready to Assign.",
        )
    await _owned_account(db, current_user.id, payload.account_id)
    if payload.category_id is not None:
        await _owned_category(db, current_user.id, payload.category_id)
    await _enforce_scope_match(
        db, current_user.id, payload.account_id, payload.category_id
    )
    if payload.splits:
        await _validate_splits(
            db, current_user.id, payload.account_id, payload.amount_cents, payload.splits
        )
    payee = await resolve_payee(db, current_user.id, payload.payee)
    txn = Transaction(
        user_id=current_user.id,
        account_id=payload.account_id,
        category_id=payload.category_id,
        is_ready_to_assign=payload.is_ready_to_assign,
        date=payload.date,
        payee_id=payee.id if payee is not None else None,
        memo=payload.memo,
        amount_cents=payload.amount_cents,
    )
    db.add(txn)
    if payload.splits:
        await db.flush()  # txn.id, needed by the split rows
        await _persist_splits(db, txn.id, payload.splits)
    await db.commit()
    await db.refresh(txn)
    payee_names = {payee.id: payee.name} if payee is not None else {}
    splits_by_txn_id = await load_splits_by_transaction_id(db, [txn]) if payload.splits else NO_SPLITS
    return _to_response(txn, NO_PEER_ACCOUNTS, payee_names, splits_by_txn_id)


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
    if peer is not None and payload.splits is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A transfer leg cannot be split. Delete the transfer instead.",
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
        payee = await resolve_payee(db, current_user.id, payload.payee)
        txn.payee_id = payee.id if payee is not None else None
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

    # Validated against the *finalized* account/category/amount above, since a
    # PATCH may change any of those in the same request that also touches
    # splits. [] clears splits back to a plain category; a non-empty list
    # replaces the set wholesale — split counts are small, so no diffing.
    if payload.splits is not None:
        if payload.splits:
            if txn.category_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="A split transaction cannot also have a top-level category.",
                )
            if txn.is_ready_to_assign:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="A split transaction cannot be marked Ready to Assign.",
                )
            await _validate_splits(
                db, current_user.id, txn.account_id, txn.amount_cents, payload.splits
            )
        await db.execute(
            delete(TransactionSplit).where(TransactionSplit.transaction_id == txn.id)
        )
        if payload.splits:
            await _persist_splits(db, txn.id, payload.splits)

    await db.commit()
    await db.refresh(txn)
    return _to_response(
        txn,
        await load_peer_account_ids(db, [txn]),
        await load_payee_names(db, [txn]),
        await load_splits_by_transaction_id(db, [txn]),
    )


async def _delete_transactions_cascading(
    db, user_id: int, txns: list[Transaction]
) -> list[Transaction]:
    """Expands the given owned transactions to include any transfer peers not
    already in the set, tombstones bank-imported legs, and deletes
    everything. Returns every leg actually deleted. Caller commits."""
    legs_by_id: dict[int, Transaction] = {txn.id: txn for txn in txns}
    for txn in txns:
        # Half a transfer is never a meaningful record: drop the pair.
        if txn.transfer_peer_id is not None and txn.transfer_peer_id not in legs_by_id:
            peer = await db.get(Transaction, txn.transfer_peer_id)
            if peer is not None:
                legs_by_id[peer.id] = peer
    legs = list(legs_by_id.values())

    # Break the links first so neither delete trips the other's foreign key.
    for leg in legs:
        leg.transfer_peer_id = None
    if legs:
        await db.flush()

    # Tombstone bank-imported rows so the next sync doesn't mistake "the user
    # deleted this" for "never imported" and bring it right back — see
    # DeletedExternalTransaction.
    for leg in legs:
        if leg.external_transaction_id is not None:
            db.add(
                DeletedExternalTransaction(
                    user_id=user_id,
                    external_transaction_id=leg.external_transaction_id,
                )
            )
    for leg in legs:
        await db.delete(leg)
    return legs


@router.post("/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_transactions(
    payload: BulkDeleteRequest, db: DbSession, current_user: CurrentUser
) -> BulkDeleteResponse:
    result = await db.execute(
        select(Transaction).where(
            Transaction.id.in_(set(payload.ids)),
            Transaction.user_id == current_user.id,
        )
    )
    txns = list(result.scalars().all())
    legs = await _delete_transactions_cascading(db, current_user.id, txns)
    await db.commit()
    return BulkDeleteResponse(deleted=len(legs))


@router.post("/bulk-set-category", response_model=BulkSetCategoryResponse)
async def bulk_set_category(
    payload: BulkSetCategoryRequest, db: DbSession, current_user: CurrentUser
) -> BulkSetCategoryResponse:
    """Set (or clear) one category across many transactions at once.

    Silently skips, rather than erroring, any row that can't take the new
    category: a transfer leg, a split transaction (setting one category
    across all its lines would destroy the split), or one whose account's
    scope doesn't match the target category — mirroring ``bulk-delete``'s
    existing permissive philosophy (its own count can already exceed
    ``len(ids)`` via peer cascade, with no per-row error reporting).
    """
    target_category: Category | None = None
    target_group: CategoryGroup | None = None
    if payload.category_id is not None:
        target_category = await _owned_category(db, current_user.id, payload.category_id)
        target_group = await db.get(CategoryGroup, target_category.group_id)

    result = await db.execute(
        select(Transaction).where(
            Transaction.id.in_(set(payload.ids)),
            Transaction.user_id == current_user.id,
        )
    )
    txns = list(result.scalars().all())

    accounts_result = await db.execute(
        select(Account).where(Account.id.in_({t.account_id for t in txns}))
    )
    account_scope_id = {a.id: a.scope_id for a in accounts_result.scalars().all()}
    splits_by_txn_id = await load_splits_by_transaction_id(db, txns)

    updated = 0
    for txn in txns:
        if txn.transfer_peer_id is not None:
            continue
        if splits_by_txn_id.get(txn.id):
            continue
        if target_group is not None and target_group.scope_id != account_scope_id.get(
            txn.account_id
        ):
            continue
        txn.category_id = payload.category_id
        # Categorizing a row that was flagged Ready to Assign un-flags it —
        # the two are mutually exclusive, same as a single-transaction PATCH.
        if payload.category_id is not None:
            txn.is_ready_to_assign = False
        updated += 1

    await db.commit()
    return BulkSetCategoryResponse(updated=updated)


@router.delete("/{txn_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    txn_id: int, db: DbSession, current_user: CurrentUser
) -> None:
    txn = await _owned_transaction(db, current_user.id, txn_id)
    await _delete_transactions_cascading(db, current_user.id, [txn])
    await db.commit()
