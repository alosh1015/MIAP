from __future__ import annotations

import json

from tests.conftest import FIXTURES

API = "/api/v1"


def test_dicom_pixels_return_full_depth_samples(client, auth, new_case, upload):
    case_id = new_case()
    response = upload(case_id, FIXTURES / "chest_pa.dcm")
    assert response.status_code == 201
    image_id = response.json()["image"]["id"]

    pixels = client.get(f"{API}/images/{image_id}/pixels", headers=auth("clinician"))
    assert pixels.status_code == 200
    meta = json.loads(pixels.headers["x-miap-meta"])
    assert meta["dtype"] in {"uint8", "uint16", "int16"}
    assert meta["rows"] * meta["cols"] * meta["samples_per_pixel"] * (
        2 if meta["dtype"] != "uint8" else 1
    ) == len(pixels.content)
    assert meta["photometric"].startswith("MONOCHROME")
    assert meta["max"] > meta["min"]


def test_raster_pixels_are_uint8(client, auth, new_case, upload):
    case_id = new_case()
    response = upload(case_id, FIXTURES / "chest.png", modality="xray", body_part="CHEST")
    assert response.status_code == 201
    image_id = response.json()["image"]["id"]

    pixels = client.get(f"{API}/images/{image_id}/pixels", headers=auth("clinician"))
    assert pixels.status_code == 200
    meta = json.loads(pixels.headers["x-miap-meta"])
    assert meta["dtype"] == "uint8"
    assert meta["samples_per_pixel"] == 1


def test_administrator_cannot_read_pixels(client, auth, new_case, upload):
    case_id = new_case()
    response = upload(case_id, FIXTURES / "chest_pa.dcm")
    image_id = response.json()["image"]["id"]

    denied = client.get(f"{API}/images/{image_id}/pixels", headers=auth("administrator"))
    assert denied.status_code == 403
