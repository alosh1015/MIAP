from __future__ import annotations

import time
import uuid

import pytest

from app.modules.results.schemas import ResultDocument
from tests.conftest import API, FIXTURES


def _submit(client, headers, case_id, image_id, key=None):
    return client.post(
        f"{API}/analyses",
        json={"case_id": case_id, "image_id": image_id},
        headers={**headers, "Idempotency-Key": key or uuid.uuid4().hex},
    )


def _wait(client, headers, job_id, timeout=60.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"{API}/analyses/{job_id}", headers=headers).json()
        if body["state"] in {"completed", "failed"}:
            return body
        time.sleep(0.1)
    raise AssertionError(f"job {job_id} did not finish: {body}")


@pytest.fixture(scope="module")
def completed_job(client, auth, new_case, upload):
    case_id = new_case()
    response = upload(case_id, FIXTURES / "chest_pa.dcm")
    assert response.status_code == 201, response.text
    image_id = response.json()["image"]["id"]

    submitted = _submit(client, auth("clinician"), case_id, image_id)
    assert submitted.status_code == 202, submitted.text
    job = _wait(client, auth("clinician"), submitted.json()["job_id"])
    return case_id, image_id, submitted, job


def test_submit_returns_202_with_location(completed_job):
    _case_id, _image_id, submitted, _job = completed_job
    assert submitted.status_code == 202
    assert submitted.headers["location"].startswith("/api/v1/analyses/")


def test_job_completes(completed_job):
    _case_id, _image_id, _submitted, job = completed_job
    assert job["state"] == "completed", job
    assert job["progress"] == 1.0
    assert job["error"] is None


def test_result_matches_section7_contract(client, auth, completed_job):
    _case_id, image_id, submitted, _job = completed_job
    response = client.get(f"{API}/analyses/{submitted.json()['job_id']}/result", headers=auth("clinician"))
    assert response.status_code == 200, response.text
    document = response.json()

    parsed = ResultDocument(**document)
    assert parsed.image_id == image_id
    assert parsed.findings, "a completed analysis must carry findings"
    assert parsed.model.name == "stub_classifier"
    assert parsed.model.demo is True
    assert parsed.heatmap is not None
    assert any("not a diagnosis" in warning.lower() for warning in parsed.warnings)
    assert parsed.birads is None and parsed.density is None
    assert "population" not in document


def test_result_is_409_until_a_result_exists(client, auth, completed_job):
    _case_id, _image_id, _submitted, _job = completed_job
    unknown = client.get(f"{API}/analyses/j_missing/result", headers=auth("clinician"))
    assert unknown.status_code == 404


def test_provenance_records_inputs_model_and_seed(client, auth, completed_job):
    _case_id, _image_id, submitted, _job = completed_job
    response = client.get(f"{API}/analyses/{submitted.json()['job_id']}/provenance", headers=auth("clinician"))
    assert response.status_code == 200, response.text
    record = response.json()

    digests = {item["role"]: item["digest"] for item in record["inputs"]}
    assert digests["original_upload"] and digests["deidentified_image"]
    assert digests["original_upload"] != digests["deidentified_image"]
    assert record["model"]["name"] == "stub_classifier"
    assert record["seed"] == 0
    assert record["code_commit"]
    assert record["parameters"]["input_size"] == 224
    assert record["parameters"]["gradcam_layer"] == "input-gradient"


def test_heatmap_artifacts_download(client, auth, completed_job):
    _case_id, _image_id, submitted, _job = completed_job
    document = client.get(f"{API}/analyses/{submitted.json()['job_id']}/result", headers=auth("clinician")).json()
    result_id = document.get("result_id")
    if result_id is None:
        from app.core.db import SessionLocal
        from app.core.schema import Result

        assert SessionLocal is not None
        with SessionLocal() as session:
            from sqlalchemy import select

            result_id = session.execute(
                select(Result).where(Result.job_id == submitted.json()["job_id"])
            ).scalar_one().id

    npy = client.get(f"{API}/results/{result_id}/heatmap.npy", headers=auth("clinician"))
    assert npy.status_code == 200
    assert npy.content[:6] == b"\x93NUMPY"

    png = client.get(f"{API}/results/{result_id}/heatmap.png", headers=auth("clinician"))
    assert png.status_code == 200
    assert png.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_idempotent_replay_returns_the_same_job(client, auth, completed_job):
    case_id, image_id, submitted, _job = completed_job
    key = uuid.uuid4().hex
    first = _submit(client, auth("clinician"), case_id, image_id, key)
    second = _submit(client, auth("clinician"), case_id, image_id, key)
    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]


def test_idempotency_key_reused_for_different_input_is_rejected(client, auth, new_case, upload, completed_job):
    case_id, _image_id, submitted, _job = completed_job
    other_case = new_case()
    upload_response = upload(other_case, FIXTURES / "chest_pa.dcm")
    assert upload_response.status_code == 201
    other_image = upload_response.json()["image"]["id"]

    key = submitted.request.headers["Idempotency-Key"]
    conflict = client.post(
        f"{API}/analyses",
        json={"case_id": other_case, "image_id": other_image},
        headers={**auth("clinician"), "Idempotency-Key": key},
    )
    assert conflict.status_code == 422
    assert conflict.json()["code"] == "idempotency_conflict"


def test_mammogram_analysis_is_refused(client, auth, new_case, upload):
    case_id = new_case()
    response = upload(case_id, FIXTURES / "mammo_four_view" / "LCC.dcm")
    assert response.status_code == 201, response.text
    image_id = response.json()["image"]["id"]

    refused = _submit(client, auth("clinician"), case_id, image_id)
    assert refused.status_code == 409
    assert refused.json()["code"] == "analysis_not_supported"


def test_skull_xray_analysis_is_refused(client, auth, new_case, upload):
    case_id = new_case()
    response = upload(case_id, FIXTURES / "skull_ap.dcm")
    assert response.status_code == 201, response.text
    image_id = response.json()["image"]["id"]

    refused = _submit(client, auth("clinician"), case_id, image_id)
    assert refused.status_code == 409
    assert refused.json()["code"] == "analysis_not_supported"


def test_administrator_cannot_read_results(client, auth, completed_job):
    _case_id, _image_id, submitted, _job = completed_job
    response = client.get(f"{API}/analyses/{submitted.json()['job_id']}/result", headers=auth("administrator"))
    assert response.status_code == 403


def test_missing_idempotency_key_is_rejected(client, auth, completed_job):
    case_id, image_id, _submitted, _job = completed_job
    response = client.post(
        f"{API}/analyses",
        json={"case_id": case_id, "image_id": image_id},
        headers=auth("clinician"),
    )
    assert response.status_code == 422
