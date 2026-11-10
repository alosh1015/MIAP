from __future__ import annotations

import io

import pydicom
import pytest
from PIL import Image

from app.core.storage import read_blob
from tests.conftest import FIXTURES, API


@pytest.fixture(scope="module")
def deidentified(client, auth, new_case, upload):
    case_id = new_case()
    with (FIXTURES / "chest_pa.dcm").open("rb") as handle:
        response = client.post(
            f"{API}/cases/{case_id}/images",
            files={"file": ("chest_pa.dcm", handle, "application/octet-stream")},
            headers=auth("clinician"),
        )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["image"], body["deid_receipt"]


def _dataset(image: dict) -> pydicom.Dataset:
    from app.core.schema import Image as ImageModel
    from app.core.db import SessionLocal

    assert SessionLocal is not None
    with SessionLocal() as session:
        stored = session.get(ImageModel, image["id"])
        data = read_blob(stored.blob_digest)
    return pydicom.dcmread(io.BytesIO(data), force=False)


def test_identity_attributes_replaced(deidentified):
    image, _ = deidentified
    dataset = _dataset(image)
    assert dataset.PatientName == "ANON^MIAP"
    assert dataset.PatientIdentityRemoved == "YES"
    assert dataset.DeidentificationMethod.startswith("ps3.15")


def test_identifying_dates_and_demographics_removed(deidentified):
    image, _ = deidentified
    dataset = _dataset(image)
    for keyword in ("PatientBirthDate", "PatientSex", "PatientAge", "StudyDate", "SeriesDate"):
        assert keyword not in dataset, f"{keyword} survived de-identification"


def test_uids_remapped_to_25_prefix(deidentified):
    image, receipt = deidentified
    dataset = _dataset(image)
    assert str(dataset.StudyInstanceUID).startswith("2.25.")
    assert str(dataset.SeriesInstanceUID).startswith("2.25.")
    assert str(dataset.SOPInstanceUID).startswith("2.25.")
    assert str(dataset.file_meta.MediaStorageSOPInstanceUID) == str(dataset.SOPInstanceUID)
    assert receipt["uids_remapped"] >= 3
    assert receipt["reidentification_key_retained"] is False


def test_clinical_attributes_retained(deidentified):
    image, receipt = deidentified
    dataset = _dataset(image)
    assert dataset.Modality == "DX"
    assert dataset.BodyPartExamined == "CHEST"
    assert "Modality" in receipt["retained"]
    assert receipt["sha256_in"] != receipt["sha256_out"]


def test_private_tags_removed(deidentified):
    image, _ = deidentified
    dataset = _dataset(image)
    assert all(not elem.tag.is_private for elem in dataset.iterall())


def test_raster_exif_stripped(client, auth, new_case, upload):
    case_id = new_case()
    response = upload(case_id, FIXTURES / "chest.png")
    assert response.status_code == 201, response.text
    image = response.json()["image"]

    from app.core.db import SessionLocal
    from app.core.schema import Image as ImageModel

    assert SessionLocal is not None
    with SessionLocal() as session:
        data = read_blob(session.get(ImageModel, image["id"]).blob_digest)

    with Image.open(io.BytesIO(data)) as stored:
        assert not stored.getexif(), "EXIF survived the raster pipeline"
    assert "exif" in response.json()["deid_receipt"]["removed"]
