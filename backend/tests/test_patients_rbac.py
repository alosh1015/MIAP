from __future__ import annotations

import uuid

import pytest

from tests.conftest import API


def create_patient(client, headers, **overrides):
    payload = {
        "name": overrides.pop("name", "Amina Nakato"),
        "hospital_number": overrides.pop("hospital_number", f"H-{uuid.uuid4().hex[:8]}"),
        "sex": "female",
        "dob": "1979-04-12",
        **overrides,
    }
    return client.post(f"{API}/patients", json=payload, headers=headers)


@pytest.fixture(scope="module")
def patient(client, auth):
    response = create_patient(client, auth("clinician"), name="Amina Nakato")
    assert response.status_code == 201, response.text
    return response.json()


def test_clinician_creates_patient_with_identity(client, patient):
    assert patient["name"] == "Amina Nakato"
    assert patient["hospital_number"].startswith("H-")
    assert patient["age"] is not None and patient["age"] > 0
    assert patient["case_count"] == 0


@pytest.mark.parametrize("role", ["researcher", "administrator"])
def test_non_clinicians_cannot_create_patients(client, auth, role):
    response = create_patient(client, auth(role))
    assert response.status_code == 403
    assert response.json()["code"] == "identity_forbidden"


@pytest.mark.parametrize("role", ["researcher", "administrator"])
def test_non_clinicians_cannot_list_or_read_identity(client, auth, patient, role):
    listing = client.get(f"{API}/patients", headers=auth(role))
    assert listing.status_code == 403
    detail = client.get(f"{API}/patients/{patient['id']}", headers=auth(role))
    assert detail.status_code == 403
    lookup = client.get(
        f"{API}/patients/lookup", params={"hospital_number": patient["hospital_number"]}, headers=auth(role)
    )
    assert lookup.status_code == 403


def test_lookup_by_hospital_number_is_owner_scoped(client, auth, patient):
    found = client.get(
        f"{API}/patients/lookup",
        params={"hospital_number": patient["hospital_number"].lower()},
        headers=auth("clinician"),
    )
    assert found.status_code == 200
    assert found.json()["found"] is True
    assert found.json()["patient"]["id"] == patient["id"]

    missing = client.get(
        f"{API}/patients/lookup",
        params={"hospital_number": f"UNKNOWN-{uuid.uuid4().hex[:6]}"},
        headers=auth("clinician"),
    )
    assert missing.status_code == 200
    assert missing.json()["found"] is False


def test_duplicate_hospital_number_is_rejected_for_same_owner(client, auth, patient):
    response = create_patient(client, auth("clinician"), hospital_number=patient["hospital_number"])
    assert response.status_code == 409
    assert response.json()["code"] == "patient_exists"


def test_case_identity_is_visible_only_to_owner(client, auth, new_case, patient):
    case_id = new_case()
    linked = client.post(
        f"{API}/cases/{case_id}/patient",
        json={"patient_id": patient["id"]},
        headers=auth("clinician"),
    )
    assert linked.status_code == 200, linked.text

    owner = client.get(f"{API}/cases/{case_id}", headers=auth("clinician")).json()
    assert owner["identity_visible"] is True
    assert owner["patient"]["name"] == "Amina Nakato"

    researcher = client.get(f"{API}/cases/{case_id}", headers=auth("researcher")).json()
    assert researcher["identity_visible"] is False
    assert researcher["patient"] is None
    assert "Amina" not in researcher["patient_display"]
    assert researcher["patient_display"] == researcher["pseudonym"]


def test_linked_patient_can_create_case_in_one_call(client, auth, patient):
    response = client.post(
        f"{API}/cases",
        json={"pseudonym": f"PT-{uuid.uuid4().hex[:8]}", "consent": "clinical", "patient_id": patient["id"]},
        headers=auth("clinician"),
    )
    assert response.status_code == 201, response.text
    case_id = response.json()["id"]
    detail = client.get(f"{API}/cases/{case_id}", headers=auth("clinician")).json()
    assert detail["patient"]["id"] == patient["id"]


def test_researcher_cannot_link_a_patient(client, auth, new_case):
    case_id = new_case("researcher")
    response = client.post(
        f"{API}/cases/{case_id}/patient",
        json={"patient_id": "pt_anything"},
        headers=auth("researcher"),
    )
    assert response.status_code == 403
