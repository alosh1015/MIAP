from __future__ import annotations

import pytest

from tests.conftest import API, FIXTURES


def test_create_case_returns_retention(client, auth, new_case):
    case_id = new_case()
    response = client.get(f"{API}/cases/{case_id}", headers=auth("clinician"))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "created"
    assert body["pseudonym"].startswith("PT-")


def test_administrator_cannot_create_cases(client, auth):
    response = client.post(
        f"{API}/cases",
        json={"pseudonym": "ADMIN-CASE", "consent": "research"},
        headers=auth("administrator"),
    )
    assert response.status_code == 403


def test_list_cases_returns_own_cases(client, auth, new_case):
    case_id = new_case("clinician")
    response = client.get(f"{API}/cases", headers=auth("clinician"))
    assert response.status_code == 200
    assert case_id in {case["id"] for case in response.json()}


def test_administrator_detail_has_no_images(client, auth, new_case, upload):
    case_id = new_case()
    assert upload(case_id, FIXTURES / "chest_pa.dcm").status_code == 201

    response = client.get(f"{API}/cases/{case_id}", headers=auth("administrator"))
    assert response.status_code == 200
    body = response.json()
    assert body["images"] == []
    assert body["exam"] is None
    assert body["image_count"] == 1


def test_xray_exam_lists_region_capability(client, auth, new_case, upload):
    case_id = new_case()
    assert upload(case_id, FIXTURES / "chest_pa.dcm").status_code == 201
    assert upload(case_id, FIXTURES / "skull_ap.dcm").status_code == 201

    body = client.get(f"{API}/cases/{case_id}", headers=auth("clinician")).json()
    assert body["exam"]["type"] == "xray"
    regions = {entry["region"]: entry["capability"]["supported"] for entry in body["exam"]["regions"]}
    assert regions["chest"] is True
    assert regions["unsupported"] is False
    raw = {entry["body_part"] for entry in body["exam"]["regions"]}
    assert {"CHEST", "SKULL"} <= raw


@pytest.mark.parametrize(
    "folder,expected_missing,expected_duplicates,complete",
    [
        ("mammo_four_view", [], [], True),
        ("mammo_three_view", ["RMLO"], [], False),
        ("mammo_duplicate", [], ["LCC"], False),
    ],
)
def test_mammogram_exams_group_into_four_views(
    client, auth, new_case, upload, folder, expected_missing, expected_duplicates, complete
):
    case_id = new_case()
    for path in sorted((FIXTURES / folder).glob("*.dcm")):
        response = upload(case_id, path)
        assert response.status_code == 201, response.text

    body = client.get(f"{API}/cases/{case_id}", headers=auth("clinician")).json()
    assert body["exam"]["type"] == "mammogram_four_view"
    assert body["exam"]["missing"] == expected_missing
    assert body["exam"]["duplicates"] == expected_duplicates
    assert body["exam"]["complete"] is complete
    layout = body["exam"]["layout"]
    if complete:
        assert all(slot is not None for slot in layout.values())
    if "RMLO" in expected_missing:
        assert layout["bottom_right"] is None


def test_limb_xray_reports_the_bone_capability(client, auth, new_case, upload):
    case_id = new_case()
    assert upload(case_id, FIXTURES / "hand_pa.dcm").status_code == 201

    body = client.get(f"{API}/cases/{case_id}", headers=auth("clinician")).json()
    regions = {entry["region"]: entry for entry in body["exam"]["regions"]}
    assert regions["bone_limb"]["capability"]["bucket"] == "bone_limb"
    assert regions["bone_limb"]["capability"]["supported"] is True


def test_mammogram_upload_reports_density_capability(client, auth, new_case, upload):
    case_id = new_case()
    response = upload(case_id, FIXTURES / "mammo_four_view" / "LCC.dcm")
    assert response.status_code == 201, response.text
    capability = response.json()["image"]["validation"]["capability"]
    assert capability["bucket"] == "mammogram_density"
    assert capability["supported"] is True


def test_archive_case_sets_status(client, auth, new_case):
    case_id = new_case()
    response = client.delete(f"{API}/cases/{case_id}", headers=auth("clinician"))
    assert response.status_code == 204
    body = client.get(f"{API}/cases/{case_id}", headers=auth("clinician")).json()
    assert body["status"] == "archived"
