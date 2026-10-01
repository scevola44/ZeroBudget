from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.models import Scope, User
from app.models.scope import DEFAULT_SCOPE_NAMES
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.security import hash_password, verify_password
from app.services.refresh_tokens import issue_session, revoke_session, rotate_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: DbSession) -> TokenResponse:
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    db.add(user)
    await db.flush()  # assigns user.id, which the scopes reference

    # A user with no scopes could not create an account or a category group, so
    # the seed commits with the user rather than as a separate step.
    db.add_all(
        Scope(user_id=user.id, name=name, sort_order=sort_order)
        for sort_order, name in enumerate(DEFAULT_SCOPE_NAMES)
    )
    await db.commit()
    await db.refresh(user)
    return await issue_session(db, user.id)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = await db.scalar(select(User).where(User.email == payload.email))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    return await issue_session(db, user.id)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: DbSession) -> TokenResponse:
    tokens = await rotate_session(db, payload.refresh_token)
    if tokens is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token"
        )
    return tokens


# Authenticated by the refresh token itself: logging out must work after the
# short-lived access token has already expired.
@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(payload: RefreshRequest, db: DbSession) -> Response:
    await revoke_session(db, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)
