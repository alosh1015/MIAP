from __future__ import annotations

import io
import time
import uuid

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from app.core.schema import AuditEvent, Result
from tests.conftest import API, FIXTURES

PATIENT_NAME = "Amina Nakato"
REVIEW_NOTE = "Left lower zone opacity, correlate clinically."


def _pdf_text(response) -> str:
    assert response.status_code == 200, response.text
    assert response.content[:5] == b"%PDF-"
    text = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(response.content)).pages
    )
    return " ".join(text.split())


@pytest.fixture(scope="module")
def reported(client, auth, new_case, upload):
    created = client.post(
        f"{API}/patients",
        json={
            "name": PATIENT_NAME,
            "hospital_number": f"H-{uuid.uuid4().hex[:8]}",
            "sex": "female",
            "dob": "1979-04-12",
        },
        headers=auth("clinician"),
    )
    assert created.status_code == 201, created.text
    patient = created.json()

    case = client.post(
        f"{API}/cases",
        json={
            "pseudonym": f"PT-{uuid.uuid4().hex[:8]}",
            "consent": "research",
            "patient_id": patient["id"],
        },
        headers=auth("clinician"),
    )
    assert case.status_code == 201, case.text
    case_id = case.json()["id"]

    uploaded = upload(case_id, FIXTURES / "chest_pa.dcm")
    assert uploaded.status_code == 201, uploaded.text
    image_id = uploaded.json()["image"]["id"]

    submitted = client.post(
        f"{API}/analyses",
        json={"case_id": case_id, "image_id": image_id},
        headers={**auth("clinician"), "Idempotency-Key": uuid.uuid4().hex},
    )
    assert submitted.status_code == 202, submitted.text
    job_id = submitted.json()["job_id"]

    deadline = time.time() + 60
    while time.time() < deadline:
        state = client.get(f"{API}/analyses/{job_id}", headers=auth("clinician")).json()["state"]
        if state in {"completed", "failed"}:
            break
        time.sleep(0.1)
    assert state == "completed"

    from app.core.db import SessionLocal

    assert SessionLocal is not None
    with SessionLocal() as session:
        result_id = session.execute(
            select(Result).where(Result.job_id == job_id)
        ).scalar_one().id

    reviewed = client.post(
        f"{API}/results/{result_id}/findings/1/review",
        json={"decision": "confirmed", "note": REVIEW_NOTE},
        headers=auth("clinician"),
    )
    assert reviewed.status_code == 200, reviewed.text
    return {
        "case_id": case_id,
        "job_id": job_id,
        "patient": patient,
        "result_id": result_id,
    }


def _create(client, auth, reported, role: str = "clinician", **params):
    return client.post(
        f"{API}/reports/{reported['case_id']}",
        params=params,
        headers=auth(role),
    )


def test_clinician_report_has_identity_when_requested(client, auth, reported):
    response = _create(
        client, auth, reported, job_id=reported["job_id"], include_identity="true"
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["audience"] == "clinician"
    assert body["kind"] == "case"
    assert body["template_version"] == "4.0"
    assert len(body["sha256"]) == 64

    text = _pdf_text(client.get(body["url"], headers=auth("clinician")))
    assert PATIENT_NAME in text
    assert reported["patient"]["hospital_number"] in text
    assert "Findings to review" in text
    assert REVIEW_NOTE in text
    assert "1 of 1 flagged findings reviewed" in text
    assert "does not screen for tuberculosis" in text.lower()


def test_clinician_report_is_deidentified_by_default(client, auth, reported):
    response = _create(client, auth, reported, job_id=reported["job_id"])
    assert response.status_code == 201, response.text
    text = _pdf_text(client.get(response.json()["url"], headers=auth("clinician")))
    assert PATIENT_NAME not in text
    assert reported["patient"]["hospital_number"] not in text
    assert "De-identified report" in text
    assert "Findings to review" in text
    assert "does not screen for tuberculosis" in text.lower()


def test_researcher_report_is_pseudonymised_and_withholds_notes(client, auth, reported):
    response = _create(client, auth, reported, job_id=reported["job_id"], audience="researcher")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["audience"] == "researcher"

    text = _pdf_text(client.get(body["url"], headers=auth("researcher")))
    assert PATIENT_NAME not in text
    assert reported["patient"]["hospital_number"] not in text
    assert REVIEW_NOTE not in text
    assert "Pseudonym" in text
    assert "Threshold" in text
    assert "Local clinician agreement" in text
    assert "Provenance" in text


def test_researcher_cannot_request_the_clinician_audience(client, auth, reported):
    response = _create(
        client, auth, reported, role="researcher", job_id=reported["job_id"], audience="clinician"
    )
    assert response.status_code == 403
    assert response.json()["code"] == "forbidden"


def test_administrator_cannot_create_or_download_case_reports(client, auth, reported):
    created = _create(client, auth, reported, job_id=reported["job_id"])
    assert created.status_code == 201

    blocked = client.post(
        f"{API}/reports/{reported['case_id']}",
        params={"job_id": reported["job_id"]},
        headers=auth("administrator"),
    )
    assert blocked.status_code == 403

    download = client.get(created.json()["url"], headers=auth("administrator"))
    assert download.status_code == 403


def test_researcher_cannot_download_a_clinician_report(client, auth, reported):
    created = _create(client, auth, reported, job_id=reported["job_id"])
    assert created.status_code == 201
    response = client.get(created.json()["url"], headers=auth("researcher"))
    assert response.status_code == 404


def test_governance_report_has_no_patients_or_findings(client, auth, reported):
    created = client.post(
        f"{API}/governance/reports",
        params={"days": 30},
        headers=auth("administrator"),
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["audience"] == "governance"
    assert body["kind"] == "governance"
    assert body["case_id"] is None

    text = _pdf_text(client.get(body["url"], headers=auth("administrator")))
    assert "Governance report" in text
    assert "Audit chain" in text
    assert "Model approvals" in text
    assert PATIENT_NAME not in text
    assert reported["patient"]["hospital_number"] not in text
    assert REVIEW_NOTE not in text


def test_governance_report_is_admin_only(client, auth):
    for role in ("clinician", "researcher"):
        response = client.post(f"{API}/governance/reports", headers=auth(role))
        assert response.status_code == 403


def test_download_is_audited_with_the_audience(client, auth, reported):
    created = _create(client, auth, reported, job_id=reported["job_id"]).json()
    assert client.get(created["url"], headers=auth("clinician")).status_code == 200

    from app.core.db import SessionLocal

    assert SessionLocal is not None
    with SessionLocal() as session:
        event = session.execute(
            select(AuditEvent)
            .where(
                AuditEvent.action == "report.downloaded",
                AuditEvent.resource_id == created["report_id"],
            )
            .order_by(AuditEvent.seq.desc())
        ).scalars().first()
    assert event is not None
    assert '"audience":"clinician"' in event.detail_json
    assert reported["patient"]["id"] not in event.detail_json
