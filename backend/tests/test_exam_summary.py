from __future__ import annotations

import json
import uuid

import pytest

from app.core.ids import new_id, utcnow_iso
from app.core.schema import Job, Result
from tests.conftest import API, FIXTURES

VIEWS = [("L", "CC", "LCC"), ("R", "CC", "RCC"), ("L", "MLO", "LMLO"), ("R", "MLO", "RMLO")]


@pytest.fixture()
def mammo_case(client, auth, new_case, upload):
    case_id = new_case()
    image_ids: dict[str, str] = {}
    for laterality, view, key in VIEWS:
        response = upload(case_id, FIXTURES / "mammo_four_view" / f"{laterality}{view}.dcm")
        assert response.status_code == 201, response.text
        image_ids[key] = response.json()["image"]["id"]
    return case_id, image_ids


def _record(session, case_id: str, image_id: str, user_id: str, density: str) -> None:
    now = utcnow_iso()
    job = Job(
        id=new_id("job"),
        case_id=case_id,
        image_id=image_id,
        state="completed",
        progress=1.0,
        idempotency_key=f"test:{uuid.uuid4().hex}",
        model_id="monai_density",
        model_version="0.1",
        params_json="{}",
        attempts=1,
        requested_by=user_id,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    session.flush()
    document = {
        "model": {"name": "monai_density", "version": "0.1", "digest": "test"},
        "classification": {"label": density, "probability": 0.7},
        "density": density,
        "findings": [],
    }
    session.add(
        Result(
            id=new_id("result"),
            job_id=job.id,
            image_id=image_id,
            case_id=case_id,
            document_json=json.dumps(document),
            created_at=now,
        )
    )
    session.commit()


def test_pending_exam_lists_every_view(client, auth, mammo_case):
    case_id, image_ids = mammo_case
    body = client.get(f"{API}/cases/{case_id}/exam-summary", headers=auth("clinician")).json()

    assert body["complete"] is True
    assert body["missing"] == []
    assert body["any_result"] is False
    assert set(body["views"]) == set(image_ids)
    assert all(entry["result_id"] is None for entry in body["views"].values())
    assert body["breasts"]["L"]["density"] is None
    assert set(body["breasts"]["L"]["views_pending"]) == {"LCC", "LMLO"}
    assert "not been calibrated" in body["caveat"]


def test_exam_summary_takes_the_highest_density_per_breast(
    client, auth, mammo_case, make_user
):
    case_id, image_ids = mammo_case
    user_id = make_user("clinician")

    from app.core.db import SessionLocal

    assert SessionLocal is not None
    with SessionLocal() as session:
        _record(session, case_id, image_ids["LCC"], user_id, "B")
        _record(session, case_id, image_ids["LMLO"], user_id, "C")

    body = client.get(f"{API}/cases/{case_id}/exam-summary", headers=auth("clinician")).json()

    left = body["breasts"]["L"]
    assert left["density"] == "C"
    assert left["density_text"] == "heterogeneously dense tissue"
    assert left["views_evaluated"] == ["LCC", "LMLO"]
    assert left["single_view"] is False
    assert body["breasts"]["R"]["density"] is None
    assert set(body["breasts"]["R"]["views_pending"]) == {"RCC", "RMLO"}
    assert body["views"]["LCC"]["result_id"]
    assert body["any_result"] is True


def test_one_evaluated_view_is_flagged_as_single_view(client, auth, mammo_case, make_user):
    case_id, image_ids = mammo_case
    user_id = make_user("clinician")

    from app.core.db import SessionLocal

    assert SessionLocal is not None
    with SessionLocal() as session:
        _record(session, case_id, image_ids["RCC"], user_id, "D")

    body = client.get(f"{API}/cases/{case_id}/exam-summary", headers=auth("clinician")).json()
    right = body["breasts"]["R"]
    assert right["density"] == "D"
    assert right["views_evaluated"] == ["RCC"]
    assert right["single_view"] is True


def test_administrator_cannot_read_an_exam_summary(client, auth, mammo_case):
    case_id, _image_ids = mammo_case
    response = client.get(f"{API}/cases/{case_id}/exam-summary", headers=auth("administrator"))
    assert response.status_code == 403


def test_researcher_cannot_read_a_clinical_exam_summary(client, auth, upload):
    created = client.post(
        f"{API}/cases",
        json={"pseudonym": f"PT-{uuid.uuid4().hex[:8]}", "consent": "clinical"},
        headers=auth("clinician"),
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    uploaded = upload(case_id, FIXTURES / "mammo_four_view" / "LCC.dcm")
    assert uploaded.status_code == 201, uploaded.text

    response = client.get(f"{API}/cases/{case_id}/exam-summary", headers=auth("researcher"))
    assert response.status_code == 404


def test_submit_exam_queues_one_job_per_view(client, auth, mammo_case, monkeypatch):
    case_id, image_ids = mammo_case
    monkeypatch.setattr(
        "app.modules.inference.exam.resolve_model_for_image",
        lambda session, image: ({"model_id": "stub_classifier", "version": "0.1"}, "mammogram_density"),
    )
    monkeypatch.setattr("app.modules.inference.router.runner.submit", lambda job_id: None)

    response = client.post(
        f"{API}/analyses/exam", json={"case_id": case_id}, headers=auth("clinician")
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["total"] == 4
    assert body["counts"] == {"queued": 4}
    assert {item["image_id"] for item in body["items"]} == set(image_ids.values())
    assert all(item["model_id"] == "stub_classifier" for item in body["items"])


def test_submit_exam_rejects_images_outside_the_exam(client, auth, mammo_case, upload):
    case_id, _image_ids = mammo_case
    chest = upload(case_id, FIXTURES / "chest_pa.dcm")
    assert chest.status_code == 201, chest.text

    response = client.post(
        f"{API}/analyses/exam",
        json={"case_id": case_id, "image_ids": [chest.json()["image"]["id"]]},
        headers=auth("clinician"),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "image_not_in_case"


def test_submit_exam_refuses_without_an_approved_mammography_model(client, auth, mammo_case):
    case_id, _image_ids = mammo_case
    response = client.post(
        f"{API}/analyses/exam", json={"case_id": case_id}, headers=auth("clinician")
    )
    assert response.status_code == 409
    assert response.json()["code"] == "analysis_not_supported"
    assert "mammogram_density" in response.json()["detail"]


def test_administrator_cannot_submit_an_exam(client, auth, mammo_case):
    case_id, _image_ids = mammo_case
    response = client.post(
        f"{API}/analyses/exam", json={"case_id": case_id}, headers=auth("administrator")
    )
    assert response.status_code == 403
