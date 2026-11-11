from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.core.schema import Case, ModelVersion, User
from tests.conftest import API, FIXTURES


def test_user_management_is_administrator_only(client, auth):
    assert client.get(f"{API}/users", headers=auth("clinician")).status_code == 403
    response = client.post(
        f"{API}/users",
        json={
            "email": f"new-{uuid.uuid4().hex[:8]}@miap.test",
            "display_name": "New Clinician",
            "password": "a-long-test-password",
            "role": "clinician",
        },
        headers=auth("clinician"),
    )
    assert response.status_code == 403


def test_admin_creates_user_without_exposing_secrets(client, auth):
    email = f"new-{uuid.uuid4().hex[:8]}@miap.test"
    created = client.post(
        f"{API}/users",
        json={
            "email": email,
            "display_name": "New Clinician",
            "password": "a-long-test-password",
            "role": "clinician",
        },
        headers=auth("administrator"),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["email"] == email
    assert set(body) == {"id", "email", "display_name", "role", "is_active", "created_at"}
    assert "password" not in created.text

    deactivated = client.patch(
        f"{API}/users/{body['id']}", json={"is_active": False}, headers=auth("administrator")
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False


def test_admin_cannot_lock_themselves_out(client, auth):
    from app.core.db import SessionLocal

    assert SessionLocal is not None
    with SessionLocal() as session:
        admin = session.execute(select(User).where(User.role == "administrator")).scalar_one()
        admin_id = admin.id

    response = client.patch(
        f"{API}/users/{admin_id}", json={"is_active": False}, headers=auth("administrator")
    )
    assert response.status_code == 422
    assert response.json()["code"] == "self_lockout"


def test_retention_preview_and_confirmed_run(client, auth, upload):
    from app.core.db import SessionLocal

    case_id = client.post(
        f"{API}/cases",
        json={"pseudonym": f"RET-{uuid.uuid4().hex[:8]}", "consent": "clinical", "retention_days": 1},
        headers=auth("clinician"),
    ).json()["id"]
    assert upload(case_id, FIXTURES / "chest_pa.dcm").status_code == 201

    assert SessionLocal is not None
    with SessionLocal() as session:
        case = session.get(Case, case_id)
        case.retention_until = "2000-01-01T00:00:00Z"
        session.commit()

    assert client.get(f"{API}/retention/preview", headers=auth("clinician")).status_code == 403
    preview = client.get(f"{API}/retention/preview", headers=auth("administrator")).json()
    assert preview["due_cases"] >= 1
    assert preview["bytes_total"] >= 0

    missing_confirm = client.post(
        f"{API}/retention/run", json={"confirm": False}, headers=auth("administrator")
    )
    assert missing_confirm.status_code == 422
    assert missing_confirm.json()["code"] == "confirmation_required"

    run = client.post(f"{API}/retention/run", json={"confirm": True}, headers=auth("administrator"))
    assert run.status_code == 200
    assert run.json()["archived"] >= 1

    with SessionLocal() as session:
        assert session.get(Case, case_id).status == "archived"


def test_model_approval_is_audited_and_survives_reseeding(client, auth):
    from app.core.db import SessionLocal
    from app.modules.models.router import seed_models

    assert SessionLocal is not None
    with SessionLocal() as session:
        original = session.get(ModelVersion, ("stub_classifier", "0.1"))
        saved = (original.state, original.state_source, original.approved_by, original.approved_at)

    assert client.get(f"{API}/models/approvals", headers=auth("clinician")).status_code == 403

    revoked = client.post(
        f"{API}/models/stub_classifier/0.1/revoke",
        json={"note": "Test revoke", "benchmark_digest": "abc123"},
        headers=auth("administrator"),
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["state"] == "revoked"

    try:
        history = client.get(f"{API}/models/approvals", headers=auth("administrator")).json()
        assert any(item["decision"] == "revoked" for item in history)

        with SessionLocal() as session:
            seed_models(session)
            model = session.get(ModelVersion, ("stub_classifier", "0.1"))
            assert model.state == "revoked"
            assert model.state_source == "approval"
    finally:
        with SessionLocal() as session:
            model = session.get(ModelVersion, ("stub_classifier", "0.1"))
            model.state, model.state_source, model.approved_by, model.approved_at = saved
            session.commit()


def test_system_health_is_administrator_only_and_has_no_clinical_content(client, auth):
    assert client.get(f"{API}/system/health", headers=auth("researcher")).status_code == 403
    health = client.get(f"{API}/system/health", headers=auth("administrator"))
    assert health.status_code == 200
    body = health.json()
    assert body["audit"]["ok"] is True
    assert body["database"]["schema_version"] >= 4
    text = health.text.lower()
    for forbidden in ("pseudonym", "patient", "finding"):
        assert forbidden not in text
