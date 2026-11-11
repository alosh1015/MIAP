from __future__ import annotations

import time
import uuid

import pytest
from sqlalchemy import select

from app.core.schema import Result
from tests.conftest import API, FIXTURES


def _wait(client, headers, job_id, timeout=60.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"{API}/analyses/{job_id}", headers=headers).json()
        if body["state"] in {"completed", "failed"}:
            return body
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish")


@pytest.fixture(scope="module")
def result_id(client, auth, new_case, upload):
    case_id = new_case()
    uploaded = upload(case_id, FIXTURES / "chest_pa.dcm")
    assert uploaded.status_code == 201, uploaded.text
    image_id = uploaded.json()["image"]["id"]
    submitted = client.post(
        f"{API}/analyses",
        json={"case_id": case_id, "image_id": image_id},
        headers={**auth("clinician"), "Idempotency-Key": uuid.uuid4().hex},
    )
    assert submitted.status_code == 202, submitted.text
    job = _wait(client, auth("clinician"), submitted.json()["job_id"])
    assert job["state"] == "completed", job

    from app.core.db import SessionLocal

    assert SessionLocal is not None
    with SessionLocal() as session:
        return session.execute(
            select(Result).where(Result.job_id == submitted.json()["job_id"])
        ).scalar_one().id


def test_owner_reviews_a_finding_with_a_note(client, auth, result_id):
    response = client.post(
        f"{API}/results/{result_id}/findings/0/review",
        json={"decision": "confirmed", "note": "Left lower zone opacity, correlate clinically."},
        headers=auth("clinician"),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "confirmed"
    assert body["has_note"] is True
    assert body["note"] is None
    assert body["revision"] == 1


def test_owner_reads_notes_and_researcher_gets_aggregates(client, auth, result_id):
    owner = client.get(f"{API}/results/{result_id}/reviews", headers=auth("clinician")).json()
    assert owner["notes_visible"] is True
    assert owner["reviewed"] == 1
    assert owner["confirmed"] == 1
    assert owner["items"][0]["note"].startswith("Left lower zone")

    researcher = client.get(f"{API}/results/{result_id}/reviews", headers=auth("researcher")).json()
    assert researcher["notes_visible"] is False
    assert researcher["items"] == []
    assert researcher["reviewed"] == 1


def test_researcher_and_admin_cannot_review(client, auth, result_id):
    for role in ("researcher", "administrator"):
        response = client.post(
            f"{API}/results/{result_id}/findings/0/review",
            json={"decision": "dismissed"},
            headers=auth(role),
        )
        assert response.status_code == 403


def test_review_change_increments_revision_and_keeps_note(client, auth, result_id):
    changed = client.post(
        f"{API}/results/{result_id}/findings/0/review",
        json={"decision": "dismissed"},
        headers=auth("clinician"),
    )
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert body["decision"] == "dismissed"
    assert body["revision"] == 2
    assert body["has_note"] is True

    reviews = client.get(f"{API}/results/{result_id}/reviews", headers=auth("clinician")).json()
    assert reviews["dismissed"] == 1
    assert reviews["items"][0]["note"].startswith("Left lower zone")


def test_unknown_finding_index_is_rejected(client, auth, result_id):
    response = client.post(
        f"{API}/results/{result_id}/findings/999/review",
        json={"decision": "confirmed"},
        headers=auth("clinician"),
    )
    assert response.status_code == 404


def test_result_payload_embeds_review_and_plain_language(client, auth, result_id):
    from app.core.db import SessionLocal
    from app.core.schema import Result

    assert SessionLocal is not None
    with SessionLocal() as session:
        job_id = session.get(Result, result_id).job_id

    document = client.get(f"{API}/analyses/{job_id}/result", headers=auth("clinician")).json()
    assert document["document_version"] == 2
    assert document["findings"][0]["review"]["decision"] == "dismissed"
    assert document["findings"][0]["review"]["note"].startswith("Left lower zone")
    assert document["findings"][0]["band"] in {"above_threshold", "borderline", "below_threshold"}
    assert document["findings"][0]["plain_label"]
    assert document["plain_language_note"]

    researcher = client.get(f"{API}/analyses/{job_id}/result", headers=auth("researcher")).json()
    assert researcher["findings"][0]["review"]["note"] is None
