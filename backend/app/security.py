import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_settings

settings = get_settings()

# bcrypt caps the input at 72 bytes; we enforce that by truncating, which is
# the same guidance the `bcrypt` package itself now gives. For the skeleton
# we don't pre-hash with SHA-256; we just reject/truncate oversize passwords
# at the edge (min length is enforced by Pydantic, max length 72 bytes in
# register/login flows).
_BCRYPT_MAX_BYTES = 72
REFRESH_TOKEN_BYTES = 32


def _encode_password(plain: str) -> bytes:
    raw = plain.encode("utf-8")
    return raw[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    hashed = bcrypt.hashpw(_encode_password(plain), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_encode_password(plain), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.jwt_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def access_token_lifetime_seconds() -> int:
    return settings.jwt_expire_minutes * 60


def refresh_token_lifetime() -> timedelta:
    return timedelta(days=settings.refresh_token_expire_days)


def generate_refresh_token() -> str:
    # Opaque rather than a JWT: it is only ever looked up by hash, so it cannot
    # be mistaken for an access token and needs no signature.
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def hash_refresh_token(token: str) -> str:
    # Plain SHA-256 (not bcrypt): the token is 256 bits of randomness, so there
    # is nothing to brute-force, and it is hashed on every refresh request.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_access_token(token: str) -> int:
    """Return the user id encoded in the token, or raise jwt.InvalidTokenError."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    sub = payload.get("sub")
    if sub is None:
        raise jwt.InvalidTokenError("missing sub")
    return int(sub)
