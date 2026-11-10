from __future__ import annotations

import io
import time
import uuid

import pytest
from pypdf import PdfReader

from tests.conftest import API, FIXTURES


@pytest.fixture(scope="module")
def reported_case(client, auth, new_case, upload):
    case_id = new_case()
    response = upload(case_id, FIXTURES / "chest_pa.dcm")
    assert response.status_code == 201, response.text
    image_id = response.json()["image"]["id"]

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
    return case_id, job_id


def test_report_is_created_from_the_stored_result(client, auth, reported_case):
    case_id, job_id = reported_case
    response = client.post(
        f"{API}/reports/{case_id}",
        params={"job_id": job_id},
        headers=auth("clinician"),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["url"].endswith(".pdf")
    assert body["case_id"] == case_id


def test_report_pdf_carries_model_limitations_and_disclaimer(client, auth, reported_case):
    case_id, job_id = reported_case
    created = client.post(
        f"{API}/reports/{case_id}",
        params={"job_id": job_id},
        headers=auth("clinician"),
    ).json()

    response = client.get(created["url"], headers=auth("clinician"))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:5] == b"%PDF-"

    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(response.content)).pages)
    assert "not a diagnosis" in text
    assert "stub_classifier" in text
    assert "Model limitations" in text
    assert "Provenance" in text


def test_report_requires_a_completed_analysis(client, auth, new_case):
    case_id = new_case()
    response = client.post(f"{API}/reports/{case_id}", headers=auth("clinician"))
    assert response.status_code == 409
    assert response.json()["code"] == "no_results"


def test_administrator_cannot_download_reports(client, auth, reported_case):
    case_id, job_id = reported_case
    created = client.post(
        f"{API}/reports/{case_id}",
        params={"job_id": job_id},
        headers=auth("clinician"),
    ).json()
    assert client.get(created["url"], headers=auth("administrator")).status_code == 403
