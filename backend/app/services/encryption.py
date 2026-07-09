"""Symmetric encryption for secrets at rest (Enable Banking session ids).

Thin wrapper around Fernet so callers get helpful errors when the key is
missing or malformed, instead of a confusing cryptography stack trace.
"""

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class EncryptionKeyMissing(RuntimeError):
    """Raised when a banking flow needs encryption but BANK_ENCRYPTION_KEY is unset."""


def _fernet() -> Fernet:
    key = get_settings().bank_encryption_key
    if not key:
        raise EncryptionKeyMissing(
            "BANK_ENCRYPTION_KEY is not set. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(key.encode())
    except ValueError as exc:
        raise EncryptionKeyMissing(f"BANK_ENCRYPTION_KEY is not a valid Fernet key: {exc}") from exc


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise EncryptionKeyMissing(
            "Could not decrypt stored bank session — BANK_ENCRYPTION_KEY has likely changed"
        ) from exc
