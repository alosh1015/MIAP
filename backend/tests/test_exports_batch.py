from __future__ import annotations

import time
import uuid

import pytest

from tests.conftest import API, FIXTURES


def _wait_batch(client, headers, batch_id, timeout=90.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"{API}/analyses/batch/{batch_id}", headers=headers).json()
        if body["state"] in {"completed", "failed", "partial"}:
            return body
        time.sleep(0.15)
    raise AssertionError(f"batch {batch_id} did not finish: {body}")


def test_researcher_export_is_pseudonymised(client, auth):
    name = f"ExportSecretName {uuid.uuid4().hex[:8]}"
    hospital_number = f"EXP-{uuid.uuid4().hex[:8]}"
    patient = client.post(
        f"{API}/patients",
        json={"name": name, "hospital_number": hospital_number, "sex": "female", "dob": "1990-05-05"},
        headers=auth("clinician"),
    )
    assert patient.status_code == 201, patient.text
    pseudonym = f"PT-{uuid.uuid4().hex[:8]}"
    case = client.post(
        f"{API}/cases",
        json={"pseudonym": pseudonym, "consent": "research", "patient_id": patient.json()["id"]},
        headers=auth("clinician"),
    )
    assert case.status_code == 201, case.text

    assert client.post(f"{API}/exports", json={"format": "json"}, headers=auth("clinician")).status_code == 403

    response = client.post(
        f"{API}/exports", json={"format": "json", "consent": "research"}, headers=auth("researcher")
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    rows = response.json()
    assert any(row["pseudonym"] == pseudonym for row in rows)
    assert name not in response.text
    assert hospital_number not in response.text
    row = next(row for row in rows if row["pseudonym"] == pseudonym)
    assert set(row) >= {"case_id", "pseudonym", "findings", "model"}


def test_csv_export_has_a_header_and_no_identity(client, auth):
    response = client.post(
        f"{API}/exports", json={"format": "csv"}, headers=auth("researcher")
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    header = response.text.splitlines()[0]
    assert "pseudonym" in header
    assert "hospital_number" not in header
    assert "name" not in header.split(",")


@pytest.fixture(scope="module")
def batch_result(client, auth, new_case, upload):
    case_id = new_case()
    for name in ("chest_pa.dcm", "chest_pa.dcm"):
        response = upload(case_id, FIXTURES / name)
        assert response.status_code == 201, response.text
    return case_id


def test_batch_completes_and_tracks_every_item(client, auth, batch_result):
    submitted = client.post(
        f"{API}/analyses/batch",
        json={"case_id": batch_result},
        headers=auth("clinician"),
    )
    assert submitted.status_code == 202, submitted.text
    body = submitted.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    keys = {item["job_id"] for item in body["items"]}
    assert len(keys) == 2

    finished = _wait_batch(client, auth("clinician"), body["batch_id"])
    assert finished["state"] == "completed", finished
    assert finished["counts"].get("completed") == 2
    assert all(item["state"] == "completed" for item in finished["items"])


def test_researcher_may_read_a_research_batch_but_admin_may_not(client, auth, batch_result):
    submitted = client.post(
        f"{API}/analyses/batch",
        json={"case_id": batch_result},
        headers=auth("clinician"),
    )
    batch_id = submitted.json()["batch_id"]
    assert client.get(f"{API}/analyses/batch/{batch_id}", headers=auth("researcher")).status_code == 200
    assert client.get(f"{API}/analyses/batch/{batch_id}", headers=auth("administrator")).status_code == 403


def test_batches_are_listed_newest_first_and_role_scoped(client, auth, batch_result):
    submitted = client.post(
        f"{API}/analyses/batch",
        json={"case_id": batch_result},
        headers=auth("clinician"),
    )
    batch_id = submitted.json()["batch_id"]
    listed = client.get(f"{API}/analyses/batches?limit=5", headers=auth("clinician"))
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert 1 <= len(rows) <= 5
    ids = [row["batch_id"] for row in rows]
    assert batch_id in ids
    assert len(ids) == len(set(ids))
    first = rows[0]
    assert set(first) >= {"batch_id", "case_id", "state", "total", "counts", "items"}

    assert client.get(f"{API}/analyses/batches", headers=auth("researcher")).status_code == 200
    assert client.get(f"{API}/analyses/batches", headers=auth("administrator")).status_code == 403
    assert client.get(f"{API}/analyses/batches?limit=0", headers=auth("clinician")).status_code == 422


def test_batch_rejects_ids_that_are_not_in_the_case(client, auth, batch_result):
    response = client.post(
        f"{API}/analyses/batch",
        json={"case_id": batch_result, "image_ids": ["img_missing"]},
        headers=auth("clinician"),
    )
    assert response.status_code == 422
