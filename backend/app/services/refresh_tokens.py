"""Issue, rotate and revoke refresh tokens.

Rotation is strict: a refresh token works exactly once. Presenting one that was
already rotated revokes its whole family, because the legitimate client only
ever holds the newest token. The cost is that a response lost in flight (flaky
mobile network) forces a fresh login; that is accepted over a replay window.
"""

import secrets
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RefreshToken
from app.models.refresh_token import FAMILY_ID_LENGTH
from app.schemas.auth import TokenResponse
from app.security import (
    access_token_lifetime_seconds,
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_lifetime,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(moment: datetime) -> datetime:
    # SQLite returns timezone-aware columns as naive datetimes; everything stored
    # here is UTC, so re-attaching the zone is lossless.
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


async def _insert_token(db: AsyncSession, user_id: int, family_id: str) -> str:
    raw_token = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(raw_token),
            family_id=family_id,
            expires_at=_now() + refresh_token_lifetime(),
        )
    )
    return raw_token


def _token_response(user_id: int, refresh_token: str) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=refresh_token,
        expires_in=access_token_lifetime_seconds(),
    )


async def issue_session(db: AsyncSession, user_id: int) -> TokenResponse:
    """Start a new token family (a login or registration) and commit."""
    # No scheduler exists to prune, so each login clears this user's dead rows.
    await db.execute(
        delete(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.expires_at < _now()
        )
    )
    family_id = secrets.token_hex(FAMILY_ID_LENGTH // 2)
    refresh_token = await _insert_token(db, user_id, family_id)
    await db.commit()
    return _token_response(user_id, refresh_token)


async def rotate_session(db: AsyncSession, presented_token: str) -> TokenResponse | None:
    """Exchange a refresh token for a new pair; None if it is not redeemable."""
    stored = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(presented_token))
    )
    if stored is None:
        return None
    if stored.revoked_at is not None:
        await _revoke_family(db, stored.family_id)
        await db.commit()
        return None
    if _as_utc(stored.expires_at) <= _now():
        return None

    stored.revoked_at = _now()
    refresh_token = await _insert_token(db, stored.user_id, stored.family_id)
    await db.commit()
    return _token_response(stored.user_id, refresh_token)


async def revoke_session(db: AsyncSession, presented_token: str) -> None:
    """Revoke the family of a refresh token; unknown tokens are ignored."""
    stored = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(presented_token))
    )
    if stored is None:
        return
    await _revoke_family(db, stored.family_id)
    await db.commit()


async def _revoke_family(db: AsyncSession, family_id: str) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
