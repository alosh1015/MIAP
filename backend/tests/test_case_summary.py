from __future__ import annotations

import time
import uuid

import pytest

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
def analysed_case(client, auth, upload):
    name = f"Summary Patient {uuid.uuid4().hex[:8]}"
    hospital_number = f"SUM-{uuid.uuid4().hex[:8]}"
    patient = client.post(
        f"{API}/patients",
        json={"name": name, "hospital_number": hospital_number, "sex": "male", "dob": "1971-03-04"},
        headers=auth("clinician"),
    )
    assert patient.status_code == 201, patient.text
    pseudonym = f"PT-{uuid.uuid4().hex[:8]}"
    created = client.post(
        f"{API}/cases",
        json={"pseudonym": pseudonym, "consent": "research", "patient_id": patient.json()["id"]},
        headers=auth("clinician"),
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    uploaded = upload(case_id, FIXTURES / "chest_pa.dcm")
    assert uploaded.status_code == 201, uploaded.text
    image_id = uploaded.json()["image"]["id"]
    submitted = client.post(
        f"{API}/analyses",
        json={"case_id": case_id, "image_id": image_id},
        headers={**auth("clinician"), "Idempotency-Key": uuid.uuid4().hex},
    )
    assert submitted.status_code == 202, submitted.text
    assert _wait(client, auth("clinician"), submitted.json()["job_id"])["state"] == "completed"
    return {"case_id": case_id, "pseudonym": pseudonym, "name": name, "hospital_number": hospital_number}


def _summary(client, headers, case_id):
    rows = client.get(f"{API}/cases", params={"limit": 200}, headers=headers).json()
    return next(row for row in rows if row["id"] == case_id)


def test_owner_sees_identity_and_ai_state(client, auth, analysed_case):
    row = _summary(client, auth("clinician"), analysed_case["case_id"])
    assert row["identity_visible"] is True
    assert analysed_case["name"] in row["patient_display"]
    assert row["ai_flag"] in {"flagged", "clear"}
    assert row["findings_to_review"] >= 0
    assert row["reviewed"] <= row["findings_to_review"]
    assert row["latest_result_id"]
    assert row["last_job"]["state"] == "completed"
    assert row["image_count"] == 1


def test_researcher_and_admin_never_see_identity_in_the_worklist(client, auth, analysed_case):
    for role in ("researcher", "administrator"):
        row = _summary(client, auth(role), analysed_case["case_id"])
        assert row["identity_visible"] is False
        assert row["patient_id"] is None
        assert row["patient_display"] == row["pseudonym"] == analysed_case["pseudonym"]
        assert analysed_case["name"] not in row["patient_display"]
        assert analysed_case["hospital_number"] not in str(row)


def test_sort_and_filter_are_server_side(client, auth, analysed_case):
    ascending = client.get(
        f"{API}/cases", params={"sort": "pseudonym", "order": "asc", "limit": 200}, headers=auth("clinician")
    )
    assert ascending.status_code == 200
    pseudonyms = [row["pseudonym"] for row in ascending.json()]
    assert pseudonyms == sorted(pseudonyms, key=str.lower)

    flagged = client.get(
        f"{API}/cases", params={"ai_flag": "flagged", "limit": 200}, headers=auth("clinician")
    )
    assert flagged.status_code == 200
    assert all(row["ai_flag"] == "flagged" for row in flagged.json())

    searched = client.get(
        f"{API}/cases", params={"q": analysed_case["pseudonym"][:8], "limit": 200}, headers=auth("clinician")
    )
    assert any(row["id"] == analysed_case["case_id"] for row in searched.json())


def test_invalid_sort_and_flags_are_rejected(client, auth):
    assert client.get(f"{API}/cases?sort=bogus", headers=auth("clinician")).status_code == 422
    assert client.get(f"{API}/cases?order=sideways", headers=auth("clinician")).status_code == 422
    assert client.get(f"{API}/cases?ai_flag=maybe", headers=auth("clinician")).status_code == 422
