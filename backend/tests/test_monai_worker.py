"""End-to-end check of the MONAI density engine on a synthetic mammogram view.

Skipped when the weights are not installed. The test approves the model in the
database only for its duration so it does not perturb the approval-history
assertions in ``test_registry_metadata.py``.
"""

from __future__ import annotations

import time
import uuid

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.schema import ModelVersion
from tests.conftest import API, FIXTURES

WEIGHTS = get_settings().model_dir / "monai_density_model.pt"

pytestmark = pytest.mark.skipif(
    not WEIGHTS.exists(), reason="MONAI density weights are not installed"
)


def _wait(client, headers, job_id: str, timeout: float = 120.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"{API}/analyses/{job_id}", headers=headers).json()
        if body["state"] in {"completed", "failed"}:
            return body
        time.sleep(0.2)
    raise AssertionError(f"job {job_id} did not finish")


def test_monai_density_runs_end_to_end(client, auth, new_case, upload):
    from app.core.db import SessionLocal

    assert SessionLocal is not None
    with SessionLocal() as session:
        row = session.execute(
            select(ModelVersion).where(
                ModelVersion.model_id == "monai_density", ModelVersion.version == "0.1"
            )
        ).scalar_one()
        saved = (row.state, row.state_source)
        row.state = "approved"
        row.state_source = "approval"
        session.commit()

    try:
        case_id = new_case()
        uploaded = upload(case_id, FIXTURES / "mammo_four_view" / "LCC.dcm")
        assert uploaded.status_code == 201, uploaded.text
        image_id = uploaded.json()["image"]["id"]

        submitted = client.post(
            f"{API}/analyses",
            json={"case_id": case_id, "image_id": image_id, "model_id": "monai_density"},
            headers={**auth("clinician"), "Idempotency-Key": uuid.uuid4().hex},
        )
        assert submitted.status_code == 202, submitted.text
        job_id = submitted.json()["job_id"]
        finished = _wait(client, auth("clinician"), job_id)
        assert finished["state"] == "completed", finished

        result = client.get(
            f"{API}/analyses/{job_id}/result", headers=auth("clinician")
        ).json()
        assert result["document_version"] == 2
        assert result["density"] in {"A", "B", "C", "D"}
        assert {finding["label"] for finding in result["findings"]} == {"A", "B", "C", "D"}
        assert result["degraded"] is False
        assert result["heatmap"]["shape"] == [299, 299]

        provenance = client.get(
            f"{API}/analyses/{job_id}/provenance", headers=auth("clinician")
        ).json()
        assert provenance["parameters"]["profile"] == "monai_density_299"
        assert provenance["parameters"]["input_size"] == 299
        assert provenance["parameters"]["channels"] == 3
        assert provenance["parameters"]["capability"] == "mammogram_density"
        assert provenance["parameters"]["gradcam_layer"] == "Mixed_7c"

        summary = client.get(
            f"{API}/cases/{case_id}/exam-summary", headers=auth("clinician")
        ).json()
        assert summary["views"]["LCC"]["result_id"]
        assert summary["breasts"]["L"]["density"] == result["density"]
        assert summary["breasts"]["L"]["single_view"] is True
    finally:
        with SessionLocal() as session:
            row = session.execute(
                select(ModelVersion).where(
                    ModelVersion.model_id == "monai_density", ModelVersion.version == "0.1"
                )
            ).scalar_one()
            row.state, row.state_source = saved
            session.commit()
