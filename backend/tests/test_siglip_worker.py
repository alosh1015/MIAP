"""End-to-end checks of the SigLIP 2 bone engine on synthetic limb radiographs."""

from __future__ import annotations

import time
import uuid

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.schema import ModelVersion
from tests.conftest import API, FIXTURES

WEIGHTS = get_settings().model_dir / "siglip2-base-patch16-224" / "model.safetensors"

pytestmark = pytest.mark.skipif(
    not WEIGHTS.exists(), reason="SigLIP bone weights are not installed"
)


def _wait(client, headers, job_id: str, timeout: float = 120.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"{API}/analyses/{job_id}", headers=headers).json()
        if body["state"] in {"completed", "failed"}:
            return body
        time.sleep(0.2)
    raise AssertionError(f"job {job_id} did not finish")


@pytest.fixture()
def approved_siglip():
    from app.core.db import SessionLocal

    assert SessionLocal is not None
    with SessionLocal() as session:
        row = session.execute(
            select(ModelVersion).where(
                ModelVersion.model_id == "siglip_bone", ModelVersion.version == "0.1"
            )
        ).scalar_one()
        saved = (row.state, row.state_source)
        row.state = "approved"
        row.state_source = "approval"
        session.commit()
    yield
    with SessionLocal() as session:
        row = session.execute(
            select(ModelVersion).where(
                ModelVersion.model_id == "siglip_bone", ModelVersion.version == "0.1"
            )
        ).scalar_one()
        row.state, row.state_source = saved
        session.commit()


def _analyse(client, auth, case_id: str, image_id: str) -> dict:
    submitted = client.post(
        f"{API}/analyses",
        json={"case_id": case_id, "image_id": image_id, "model_id": "siglip_bone"},
        headers={**auth("clinician"), "Idempotency-Key": uuid.uuid4().hex},
    )
    assert submitted.status_code == 202, submitted.text
    job_id = submitted.json()["job_id"]
    finished = _wait(client, auth("clinician"), job_id)
    assert finished["state"] == "completed", finished
    return client.get(f"{API}/analyses/{job_id}/result", headers=auth("clinician")).json()


def test_siglip_bone_runs_on_a_hand_radiograph(client, auth, new_case, upload, approved_siglip):
    case_id = new_case()
    uploaded = upload(case_id, FIXTURES / "hand_pa.dcm")
    assert uploaded.status_code == 201, uploaded.text

    result = _analyse(client, auth, case_id, uploaded.json()["image"]["id"])
    assert {finding["label"] for finding in result["findings"]} == {"normal", "abnormal"}
    assert result["degraded"] is False
    assert any("not been validated on local patients" in warning for warning in result["warnings"])
    top = result["classification"]["label"]
    if top == "normal":
        # The reference class has no region to point at, so no map is presented.
        assert result["heatmap"] is None
        assert result["primary_finding_index"] is None
    else:
        assert result["heatmap"]["shape"] == [224, 224]


def test_hip_radiograph_is_marked_experimental(client, auth, new_case, upload, approved_siglip):
    case_id = new_case()
    uploaded = upload(case_id, FIXTURES / "hip_ap.dcm")
    assert uploaded.status_code == 201, uploaded.text

    result = _analyse(client, auth, case_id, uploaded.json()["image"]["id"])
    assert result["degraded"] is True
    assert any("Experimental capability" in warning for warning in result["warnings"])


def test_maps_are_served_only_for_flagged_findings(client, auth, new_case, upload, approved_siglip):
    case_id = new_case()
    uploaded = upload(case_id, FIXTURES / "hand_pa.dcm")
    assert uploaded.status_code == 201, uploaded.text

    result = _analyse(client, auth, case_id, uploaded.json()["image"]["id"])
    findings = result["findings"]
    flagged = [
        finding["index"]
        for finding in findings
        if finding["band"] in {"above_threshold", "borderline"}
    ]
    expected_primary = (
        max(flagged, key=lambda index: findings[index]["probability"]) if flagged else None
    )
    assert result["primary_finding_index"] == expected_primary

    headers = auth("clinician")
    for index in range(len(findings)):
        response = client.get(
            f"{API}/results/{result['result_id']}/findings/{index}/heatmap.npy", headers=headers
        )
        if index in flagged:
            assert response.status_code == 200, response.text
        else:
            assert response.status_code == 404, response.text
            assert response.json()["code"] == "heatmap_unavailable"


def test_abnormal_cam_is_prompt_specific(approved_siglip):
    import numpy as np

    from app.modules.inference.engine import get_engine
    from app.modules.ingestion.pixels import read_pixel_data
    from app.modules.preprocessing.service import to_model_input

    data = (FIXTURES / "hand_pa.dcm").read_bytes()
    array, meta = read_pixel_data(
        type("ImageRef", (), {"mime": "application/dicom"})(), data
    )
    model_input, _stats = to_model_input(
        array, photometric=meta.get("photometric", ""), profile="siglip_bone_224"
    )

    engine = get_engine("siglip_bone", "0.1")
    abnormal = np.asarray(engine.gradcam(model_input, target_label="abnormal"))
    normal = np.asarray(engine.gradcam(model_input, target_label="normal"))

    assert abnormal.shape == (224, 224)
    assert np.isfinite(abnormal).all()
    assert 0.0 <= float(abnormal.min()) and float(abnormal.max()) <= 1.0
    assert float(abnormal.max()) > 0.2
    assert not np.allclose(abnormal, normal)
    if float(np.asarray(model_input)[0, :, :8, :8].mean()) < -0.8:
        assert float(abnormal[:8, :8].max()) < 0.1
