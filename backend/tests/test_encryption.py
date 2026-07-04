"""Round-trip tests for the Fernet encryption wrapper."""

import pytest

from app.services.encryption import EncryptionKeyMissing, decrypt, encrypt

STABLE_TEST_KEY = "UTxtCGAy-teDR0N8K2tUap0l6aguAg1OtH_rDulrel0="


def test_roundtrip():
    plaintext = "eb-session-abc123-very-secret"
    assert decrypt(encrypt(plaintext)) == plaintext


def test_ciphertexts_are_different_each_call():
    # Fernet includes a random IV, so two encryptions of the same plaintext
    # must produce different ciphertexts (otherwise our key would leak info).
    assert encrypt("same") != encrypt("same")


def test_missing_key_raises(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("BANK_ENCRYPTION_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(EncryptionKeyMissing):
            encrypt("anything")
    finally:
        monkeypatch.setenv("BANK_ENCRYPTION_KEY", STABLE_TEST_KEY)
        get_settings.cache_clear()


def test_malformed_key_raises(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("BANK_ENCRYPTION_KEY", "not-a-valid-fernet-key")
    get_settings.cache_clear()
    try:
        with pytest.raises(EncryptionKeyMissing):
            encrypt("anything")
    finally:
        monkeypatch.setenv("BANK_ENCRYPTION_KEY", STABLE_TEST_KEY)
        get_settings.cache_clear()
