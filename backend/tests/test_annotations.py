from __future__ import annotations

import io
import time
import uuid

from pypdf import PdfReader

from tests.conftest import API, FIXTURES

POLYGON = [[0.3, 0.3], [0.6, 0.3], [0.6, 0.6], [0.3, 0.6]]


def _image(client, auth, new_case, upload, role: str = "clinician") -> tuple[str, str]:
    case_id = new_case(role)
    response = upload(case_id, FIXTURES / "chest_pa.dcm", role=role)
    assert response.status_code == 201, response.text
    return case_id, response.json()["image"]["id"]


def test_annotations_round_trip_and_are_audited(client, auth, new_case, upload):
    case_id, image_id = _image(client, auth, new_case, upload)
    base = f"{API}/cases/{case_id}/images/{image_id}/annotations"

    created = client.post(base, json={"points": POLYGON}, headers=auth("clinician"))
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["image_id"] == image_id
    assert body["points"] == POLYGON

    listed = client.get(base, headers=auth("clinician"))
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [body["id"]]

    from app.core.db import SessionLocal
    from app.core.schema import AuditEvent

    with SessionLocal() as session:
        events = (
            session.query(AuditEvent)
            .filter_by(action="annotation.created", resource_id=image_id)
            .all()
        )
    assert len(events) == 1

    cleared = client.delete(base, headers=auth("clinician"))
    assert cleared.status_code == 200
    assert cleared.json() == {"removed": 1}
    assert client.get(base, headers=auth("clinician")).json() == []


def test_annotation_points_must_sit_inside_the_image(client, auth, new_case, upload):
    case_id, image_id = _image(client, auth, new_case, upload)
    base = f"{API}/cases/{case_id}/images/{image_id}/annotations"

    outside = client.post(base, json={"points": [[0.2, 0.2], [1.4, 0.2], [0.5, 0.5]]}, headers=auth("clinician"))
    assert outside.status_code == 422

    too_short = client.post(base, json={"points": [[0.2, 0.2], [0.4, 0.4]]}, headers=auth("clinician"))
    assert too_short.status_code == 422


def test_annotations_are_scoped_to_the_case_owner(client, auth, new_case, upload):
    case_id, image_id = _image(client, auth, new_case, upload)
    base = f"{API}/cases/{case_id}/images/{image_id}/annotations"

    researcher = client.get(base, headers=auth("researcher"))
    assert researcher.status_code == 200

    administrator = client.get(base, headers=auth("administrator"))
    assert administrator.status_code == 403


def test_unknown_image_is_not_found(client, auth, new_case):
    case_id = new_case()
    response = client.get(
        f"{API}/cases/{case_id}/images/img_missing/annotations",
        headers=auth("clinician"),
    )
    assert response.status_code == 404


def test_report_notes_reviewer_highlights(client, auth, new_case, upload):
    case_id, image_id = _image(client, auth, new_case, upload)
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

    created = client.post(
        f"{API}/cases/{case_id}/images/{image_id}/annotations",
        json={"points": POLYGON},
        headers=auth("clinician"),
    )
    assert created.status_code == 201, created.text

    report = client.post(
        f"{API}/reports/{case_id}",
        params={"job_id": job_id},
        headers=auth("clinician"),
    )
    assert report.status_code == 201, report.text
    pdf = client.get(report.json()["url"], headers=auth("clinician"))
    assert pdf.status_code == 200
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf.content)).pages)
    assert "outlines were added by the reviewer" in text
