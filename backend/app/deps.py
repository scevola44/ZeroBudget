from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Scope, User
from app.security import decode_access_token

# tokenUrl is cosmetic — we provide a JSON /api/auth/login, not form-based OAuth.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    db: DbSession,
    token: Annotated[str | None, Depends(oauth2_scheme)],
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        user_id = decode_access_token(token)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def owned_scope(db: AsyncSession, user_id: int, scope_id: int) -> Scope:
    """Load ``scope_id``, rejecting ids that belong to somebody else.

    Scope ids arrive from the client on every account, category-group and bank
    link, so this is a system boundary: without it a caller could attach their
    rows to another user's pool. 404 rather than 403 so the response never
    confirms that another user's id exists.
    """
    scope = await db.get(Scope, scope_id)
    if scope is None or scope.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scope not found")
    return scope
