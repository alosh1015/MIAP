from __future__ import annotations

import json
import uuid

from sqlalchemy import select

from app.core.config import get_settings
from app.core.schema import AuditEvent, Patient
from tests.conftest import API


def _create(client, headers, name, hospital_number=None):
    payload = {
        "name": name,
        "hospital_number": hospital_number or f"H-{uuid.uuid4().hex[:8]}",
        "sex": "male",
        "dob": "1966-02-03",
    }
    response = client.post(f"{API}/patients", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _actions(client, auth):
    exported = client.get(f"{API}/audit/export", headers=auth("administrator"))
    assert exported.status_code == 200
    return [json.loads(line)["action"] for line in exported.text.splitlines() if line.strip()]


def test_identity_reads_are_audited_and_chain_verifies(client, auth):
    token = uuid.uuid4().hex[:8]
    name = f"Zzyzx Audit {token}"
    patient = _create(client, auth("clinician"), name)

    client.get(f"{API}/patients/{patient['id']}", headers=auth("clinician"))
    client.get(f"{API}/patients", headers=auth("clinician"))
    client.get(
        f"{API}/patients/lookup",
        params={"hospital_number": patient["hospital_number"]},
        headers=auth("clinician"),
    )

    actions = _actions(client, auth)
    for action in ("patient.created", "patient.identity_viewed", "patient.list_viewed", "patient.lookup"):
        assert action in actions

    verified = client.get(f"{API}/audit/verify", headers=auth("administrator")).json()
    assert verified["ok"] is True


def test_identity_values_are_absent_from_audit_detail_and_db_bytes(client, auth):
    token = uuid.uuid4().hex[:10]
    name = f"ZzyzxSecretName{token}"
    hospital_number = f"ZZY-{token}"
    patient = _create(client, auth("clinician"), name, hospital_number)
    client.get(f"{API}/patients/{patient['id']}", headers=auth("clinician"))

    from app.core.db import SessionLocal

    assert SessionLocal is not None
    with SessionLocal() as session:
        events = session.execute(select(AuditEvent)).scalars().all()
        stored = session.get(Patient, patient["id"])
        ciphertext = stored.identity_ciphertext

    for event in events:
        detail = event.detail_json
        assert name not in detail
        assert hospital_number not in detail
    assert name.encode() not in ciphertext
    assert hospital_number.lower().encode() not in ciphertext

    settings = get_settings()
    db_path = settings.database_path
    haystack = b""
    for suffix in ("", "-wal"):
        candidate = db_path.with_name(db_path.name + suffix)
        if candidate.exists():
            haystack += candidate.read_bytes()
    assert name.encode() not in haystack
    assert hospital_number.lower().encode() not in haystack


def test_swapped_ciphertext_fails_closed_without_detail(client, auth):
    first = _create(client, auth("clinician"), f"First {uuid.uuid4().hex[:6]}")
    second = _create(client, auth("clinician"), f"Second {uuid.uuid4().hex[:6]}")

    from app.core.db import SessionLocal

    assert SessionLocal is not None
    with SessionLocal() as session:
        a = session.get(Patient, first["id"])
        b = session.get(Patient, second["id"])
        original = (a.identity_ciphertext, a.identity_nonce, b.identity_ciphertext, b.identity_nonce)
        a.identity_ciphertext, a.identity_nonce = b.identity_ciphertext, b.identity_nonce
        session.commit()

    try:
        response = client.get(f"{API}/patients/{first['id']}", headers=auth("clinician"))
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "identity_decrypt_failed"
        assert first["name"] not in response.text and second["name"] not in response.text
    finally:
        with SessionLocal() as session:
            a = session.get(Patient, first["id"])
            b = session.get(Patient, second["id"])
            a.identity_ciphertext, a.identity_nonce, b.identity_ciphertext, b.identity_nonce = original
            session.commit()

    actions = _actions(client, auth)
    assert "identity.decrypt_failed" in actions
