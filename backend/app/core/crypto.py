"""Envelope encryption for patient identity and review notes.

Identity lives in its own record, linked to a case by id, and is never derived
from or embedded in image pixels. Everything that identifies a person is sealed
in one AES-256-GCM envelope with associated data that binds the record id, so a
ciphertext cannot be moved to another patient without failing authentication.

The hospital-number blind index is an HMAC under a separate key: it supports
exact-match lookup without storing the number or a reversible hash.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

IDENTITY_FIELDS = ("name", "hospital_number", "sex", "dob")
_NONCE_BYTES = 12


class CryptoConfigError(RuntimeError):
    """Raised at startup when the key material is missing or malformed."""


class DecryptionError(RuntimeError):
    """Raised when a sealed payload cannot be authenticated or parsed."""


def _decode_key(encoded: str, name: str) -> bytes:
    try:
        key = base64.b64decode(encoded, validate=True)
    except Exception as exc:  # noqa: BLE001 - never echo the value
        raise CryptoConfigError(f"{name} is not valid base64") from exc
    if len(key) != 32:
        raise CryptoConfigError(f"{name} must decode to 32 bytes")
    return key


def keyring() -> dict[int, bytes]:
    """Return {key_version: key}. Fails closed when the current key is absent."""
    settings = get_settings()
    if not settings.pii_key:
        raise CryptoConfigError("MIAP_PII_KEY is not configured")
    versions: dict[int, bytes] = {
        settings.pii_key_version: _decode_key(settings.pii_key, "MIAP_PII_KEY")
    }
    if settings.pii_keys and settings.pii_keys.strip() not in ("", "{}"):
        try:
            extra = json.loads(settings.pii_keys)
        except json.JSONDecodeError as exc:
            raise CryptoConfigError("MIAP_PII_KEYS must be a JSON object") from exc
        for version, encoded in extra.items():
            versions[int(version)] = _decode_key(str(encoded), f"MIAP_PII_KEYS[{version}]")
    return versions


def index_key() -> bytes:
    settings = get_settings()
    if not settings.pii_index_key:
        raise CryptoConfigError("MIAP_PII_INDEX_KEY is not configured")
    return _decode_key(settings.pii_index_key, "MIAP_PII_INDEX_KEY")


def validate_crypto_config() -> None:
    """Startup check: raises CryptoConfigError rather than serving unencrypted data."""
    keyring()
    index_key()


def _aad(record: str) -> bytes:
    return record.encode("utf-8")


def _identity_aad(patient_id: str, version: int) -> bytes:
    return _aad(f"patient:{patient_id}:v{version}")


def _note_aad(review_id: str) -> bytes:
    return _aad(f"review:{review_id}")


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _seal(plaintext: bytes, aad: bytes, version: int, ring: dict[int, bytes]) -> tuple[bytes, bytes, int]:
    key = ring[version]
    nonce = os.urandom(_NONCE_BYTES)
    return AESGCM(key).encrypt(nonce, plaintext, aad), nonce, version


def _open(ciphertext: bytes, nonce: bytes, aad: bytes, version: int, ring: dict[int, bytes]) -> bytes:
    key = ring.get(version)
    if key is None:
        raise DecryptionError("key version is not available")
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, aad)
    except (InvalidTag, ValueError) as exc:
        raise DecryptionError("payload could not be decrypted") from exc


def encrypt_identity(patient_id: str, identity: dict[str, Any]) -> tuple[bytes, bytes, int]:
    """Seal {name, hospital_number, sex, dob}; unknown fields are ignored."""
    payload = {field: identity.get(field) for field in IDENTITY_FIELDS}
    version = get_settings().pii_key_version
    return _seal(_canonical(payload), _identity_aad(patient_id, version), version, keyring())


def decrypt_identity(
    patient_id: str, ciphertext: bytes, nonce: bytes, key_version: int
) -> dict[str, Any]:
    raw = _open(ciphertext, nonce, _identity_aad(patient_id, key_version), key_version, keyring())
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DecryptionError("payload is not valid JSON") from exc
    return {field: payload.get(field) for field in IDENTITY_FIELDS}


def encrypt_note(review_id: str, note: str) -> tuple[bytes, bytes, int]:
    version = get_settings().pii_key_version
    return _seal(note.encode("utf-8"), _note_aad(review_id), version, keyring())


def decrypt_note(review_id: str, ciphertext: bytes, nonce: bytes, key_version: int) -> str:
    return _open(ciphertext, nonce, _note_aad(review_id), key_version, keyring()).decode("utf-8")


def normalise_hospital_number(value: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9]", "", value.upper())
    if not cleaned:
        raise ValueError("Hospital number is empty after normalisation")
    return cleaned


def hospital_index(hospital_number: str) -> str:
    """Deterministic blind index for exact-match lookup."""
    subkey = hmac.new(index_key(), b"hospital-index", hashlib.sha256).digest()
    return hmac.new(
        subkey, normalise_hospital_number(hospital_number).encode("utf-8"), hashlib.sha256
    ).hexdigest()
