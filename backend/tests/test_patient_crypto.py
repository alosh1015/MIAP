from __future__ import annotations

import base64
import logging

import pytest

from app.core import crypto


def test_identity_round_trip_preserves_fields():
    identity = {
        "name": "Amina K.",
        "hospital_number": "MR-2026-0042",
        "sex": "F",
        "dob": "1989-04-12",
        "unexpected": "ignored",
    }
    ciphertext, nonce, version = crypto.encrypt_identity("pt_1", identity)
    assert version == 1
    assert b"Amina" not in ciphertext
    assert crypto.decrypt_identity("pt_1", ciphertext, nonce, version) == {
        "name": "Amina K.",
        "hospital_number": "MR-2026-0042",
        "sex": "F",
        "dob": "1989-04-12",
    }


def test_ciphertext_cannot_be_moved_to_another_patient():
    ciphertext, nonce, version = crypto.encrypt_identity(
        "pt_a", {"name": "A", "hospital_number": "H1", "sex": "F", "dob": "1990-01-01"}
    )
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_identity("pt_b", ciphertext, nonce, version)


def test_tampered_ciphertext_is_rejected():
    ciphertext, nonce, version = crypto.encrypt_identity(
        "pt_a", {"name": "A", "hospital_number": "H1", "sex": "F", "dob": "1990-01-01"}
    )
    damaged = bytearray(ciphertext)
    damaged[0] ^= 0xFF
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_identity("pt_a", bytes(damaged), nonce, version)


def test_unknown_key_version_fails_closed():
    ciphertext, nonce, _ = crypto.encrypt_identity(
        "pt_a", {"name": "A", "hospital_number": "H1", "sex": "F", "dob": "1990-01-01"}
    )
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_identity("pt_a", ciphertext, nonce, 99)


def test_review_note_round_trip_and_aad_binding():
    ciphertext, nonce, version = crypto.encrypt_note("rv_1", "Nodule confirmed on review.")
    assert crypto.decrypt_note("rv_1", ciphertext, nonce, version) == "Nodule confirmed on review."
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt_note("rv_2", ciphertext, nonce, version)


def test_blind_index_is_stable_and_normalises_whitespace():
    first = crypto.hospital_index("mr 2026 0042")
    second = crypto.hospital_index("MR-2026-0042")
    assert first == second
    assert first != crypto.hospital_index("MR-2026-0043")
    assert len(first) == 64
    assert "2026" not in first


def test_missing_key_fails_fast(monkeypatch):
    settings = crypto.get_settings().model_copy(update={"pii_key": ""})
    monkeypatch.setattr(crypto, "get_settings", lambda: settings)
    with pytest.raises(crypto.CryptoConfigError, match="MIAP_PII_KEY"):
        crypto.validate_crypto_config()


def test_malformed_key_is_rejected(monkeypatch):
    settings = crypto.get_settings().model_copy(
        update={"pii_key": base64.b64encode(b"too-short").decode()}
    )
    monkeypatch.setattr(crypto, "get_settings", lambda: settings)
    with pytest.raises(crypto.CryptoConfigError, match="32 bytes"):
        crypto.validate_crypto_config()


def test_plaintext_never_reaches_logs(caplog):
    secret = "Sensitive Patient Name"
    with caplog.at_level(logging.DEBUG):
        ciphertext, _, _ = crypto.encrypt_identity(
            "pt_log",
            {"name": secret, "hospital_number": "H-777", "sex": "M", "dob": "1970-07-07"},
        )
    assert secret not in caplog.text
    assert "H-777" not in caplog.text
    assert secret.encode() not in ciphertext
