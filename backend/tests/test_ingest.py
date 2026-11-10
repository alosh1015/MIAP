from __future__ import annotations

import json

import pytest

from tests.conftest import API, FIXTURES


@pytest.fixture(scope="module")
def uploaded(client, auth, new_case):
    case_id = new_case()
    images = {}
    for name in ("chest_pa.dcm", "chest.png", "chest.jpg"):
        with (FIXTURES / name).open("rb") as handle:
            response = client.post(
                f"{API}/cases/{case_id}/images",
                files={"file": (name, handle, "application/octet-stream")},
                headers=auth("clinician"),
            )
        assert response.status_code == 201, response.text
        images[name] = response.json()
    return case_id, images


def test_dicom_upload_reports_validation_and_receipt(uploaded):
    body = uploaded[1]["chest_pa.dcm"]
    image = body["image"]
    assert image["modality"] == "xray"
    assert image["body_part"] == "chest"
    assert image["mime"] == "application/dicom"
    assert image["rows"] > 0 and image["cols"] > 0

    validation = body["validation"]
    assert validation["modality"]["value"] == "xray"
    assert validation["region_or_view"]["value"] == "chest"
    assert validation["passed"] is True

    receipt = body["deid_receipt"]
    assert receipt["sha256_in"] and receipt["sha256_out"]
    assert receipt["sha256_in"] != receipt["sha256_out"]
    assert receipt["removed"] and receipt["replaced"]


def test_raster_upload_accepted(uploaded):
    for name in ("chest.png", "chest.jpg"):
        image = uploaded[1][name]["image"]
        assert image["mime"] in {"image/png", "image/jpeg"}
        assert image["modality"] == "xray"


def test_corrupt_file_rejected_with_problem_json(client, auth, new_case, upload):
    case_id = new_case()
    response = upload(case_id, FIXTURES / "corrupt.dcm")
    assert response.status_code in {415, 422}
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] in {415, 422}


def test_admin_cannot_read_image_bytes(client, auth, uploaded):
    image_id = uploaded[1]["chest_pa.dcm"]["image"]["id"]
    response = client.get(f"{API}/images/{image_id}/file", headers=auth("administrator"))
    assert response.status_code == 403
    assert response.json()["code"] == "images_forbidden"


def test_other_clinician_cannot_read_image(client, auth, make_user, uploaded):
    from app.core.db import SessionLocal
    from app.core.schema import User

    image_id = uploaded[1]["chest_pa.dcm"]["image"]["id"]
    # A second clinician account, not the case owner.
    from app.core.security import hash_password
    from app.core.ids import new_id, utcnow_iso

    assert SessionLocal is not None
    with SessionLocal() as session:
        email = f"other-{new_id('user')}@miap.test"
        session.add(
            User(
                id=new_id("user"),
                email=email,
                password_hash=hash_password("other-pw-1234"),
                display_name="Other clinician",
                role="clinician",
                is_active=True,
                created_at=utcnow_iso(),
            )
        )
        session.commit()
    token = client.post(f"{API}/auth/login", json={"email": email, "password": "other-pw-1234"}).json()
    headers = {"Authorization": f"Bearer {token['access_token']}"}
    assert client.get(f"{API}/images/{image_id}/file", headers=headers).status_code == 404


def test_image_file_streams_and_receipt_is_stored(client, auth, uploaded):
    image_id = uploaded[1]["chest_pa.dcm"]["image"]["id"]
    response = client.get(f"{API}/images/{image_id}/file", headers=auth("clinician"))
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/dicom"

    detail = client.get(f"{API}/images/{image_id}", headers=auth("clinician")).json()
    assert detail["deid_receipt"]["sha256_out"]
    assert json.dumps(detail["validation"])


def test_preview_renders_png(client, auth, uploaded):
    image_id = uploaded[1]["chest_pa.dcm"]["image"]["id"]
    response = client.get(f"{API}/images/{image_id}/preview.png", headers=auth("clinician"))
    assert response.status_code == 200
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"
