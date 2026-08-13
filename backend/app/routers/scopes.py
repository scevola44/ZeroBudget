from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import CurrentUser, DbSession, owned_scope
from app.models import Account, BankAuthRequest, CategoryGroup, Scope
from app.routers.banking import AUTH_REQUEST_TTL
from app.schemas.scope import ScopeCreate, ScopeResponse, ScopeUpdate

router = APIRouter(prefix="/api/scopes", tags=["scopes"])


async def _reject_duplicate_name(
    db: AsyncSession, user_id: int, name: str, *, excluding_id: int | None = None
) -> None:
    query = select(Scope.id).where(Scope.user_id == user_id, Scope.name == name)
    if excluding_id is not None:
        query = query.where(Scope.id != excluding_id)
    if await db.scalar(query.limit(1)) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'A scope called "{name}" already exists.',
        )


async def _describe_blockers(db: AsyncSession, scope: Scope) -> str | None:
    """Human-readable list of what still references ``scope``, or None if free.

    Expired bank authorization requests are ignored: they are transient rows
    from an abandoned bank link that the user cannot see or clear, and blocking
    on one would look like a bug.
    """
    live_auth_request_cutoff = datetime.now(timezone.utc) - AUTH_REQUEST_TTL
    counts = (
        ("account", await db.scalar(
            select(func.count()).select_from(Account).where(Account.scope_id == scope.id)
        )),
        ("category group", await db.scalar(
            select(func.count()).select_from(CategoryGroup).where(
                CategoryGroup.scope_id == scope.id
            )
        )),
        ("pending bank connection", await db.scalar(
            select(func.count()).select_from(BankAuthRequest).where(
                BankAuthRequest.scope_id == scope.id,
                BankAuthRequest.created_at >= live_auth_request_cutoff,
            )
        )),
    )
    blockers = [
        f"{count} {noun}{'s' if count != 1 else ''}" for noun, count in counts if count
    ]
    if not blockers:
        return None
    if len(blockers) == 1:
        return blockers[0]
    return f"{', '.join(blockers[:-1])} and {blockers[-1]}"


@router.get("", response_model=list[ScopeResponse])
async def list_scopes(db: DbSession, current_user: CurrentUser) -> list[Scope]:
    result = await db.execute(
        select(Scope)
        .where(Scope.user_id == current_user.id)
        .order_by(Scope.sort_order, Scope.id)
    )
    return list(result.scalars().all())


@router.post("", response_model=ScopeResponse, status_code=status.HTTP_201_CREATED)
async def create_scope(
    payload: ScopeCreate, db: DbSession, current_user: CurrentUser
) -> Scope:
    name = payload.name.strip()
    await _reject_duplicate_name(db, current_user.id, name)

    # Append rather than reuse a gap left by a deletion: sort_order is also the
    # palette slot, so reusing one would repaint an existing scope's colour.
    highest = await db.scalar(
        select(func.max(Scope.sort_order)).where(Scope.user_id == current_user.id)
    )
    scope = Scope(
        user_id=current_user.id,
        name=name,
        sort_order=0 if highest is None else highest + 1,
    )
    db.add(scope)
    await db.commit()
    await db.refresh(scope)
    return scope


@router.patch("/{scope_id}", response_model=ScopeResponse)
async def rename_scope(
    scope_id: int, payload: ScopeUpdate, db: DbSession, current_user: CurrentUser
) -> Scope:
    scope = await owned_scope(db, current_user.id, scope_id)
    name = payload.name.strip()
    await _reject_duplicate_name(db, current_user.id, name, excluding_id=scope.id)

    # Nothing stores the name — accounts and groups reference the row — so a
    # rename is display-only and touches no budget data.
    scope.name = name
    await db.commit()
    await db.refresh(scope)
    return scope


@router.delete("/{scope_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scope(scope_id: int, db: DbSession, current_user: CurrentUser) -> None:
    scope = await owned_scope(db, current_user.id, scope_id)

    remaining = await db.scalar(
        select(func.count()).select_from(Scope).where(Scope.user_id == current_user.id)
    )
    if remaining <= 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Your last scope can't be deleted — a budget needs at least one pool.",
        )

    blockers = await _describe_blockers(db, scope)
    if blockers is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f'"{scope.name}" is still used by {blockers}. '
                "Move or delete them first."
            ),
        )

    await db.delete(scope)
    await db.commit()
