from __future__ import annotations

import time
import uuid

import pytest
from sqlalchemy import select

from app.core.schema import Result, ResultHeatmap
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
def result_id(client, auth, new_case, upload):
    case_id = new_case()
    uploaded = upload(case_id, FIXTURES / "chest_pa.dcm")
    assert uploaded.status_code == 201, uploaded.text
    submitted = client.post(
        f"{API}/analyses",
        json={"case_id": case_id, "image_id": uploaded.json()["image"]["id"]},
        headers={**auth("clinician"), "Idempotency-Key": uuid.uuid4().hex},
    )
    assert submitted.status_code == 202, submitted.text
    assert _wait(client, auth("clinician"), submitted.json()["job_id"])["state"] == "completed"

    from app.core.db import SessionLocal

    assert SessionLocal is not None
    with SessionLocal() as session:
        return session.execute(
            select(Result).where(Result.job_id == submitted.json()["job_id"])
        ).scalar_one().id


def test_unflagged_finding_has_no_heatmap(client, auth, result_id):
    response = client.get(
        f"{API}/results/{result_id}/findings/0/heatmap.npy", headers=auth("clinician")
    )
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "heatmap_unavailable"


def test_flagged_finding_serves_the_cached_primary_cam(client, auth, result_id):
    first = client.get(
        f"{API}/results/{result_id}/findings/1/heatmap.npy", headers=auth("clinician")
    )
    assert first.status_code == 200, first.text
    assert first.content[:6] == b"\x93NUMPY"

    from app.core.db import SessionLocal

    assert SessionLocal is not None
    with SessionLocal() as session:
        rows = session.execute(
            select(ResultHeatmap).where(ResultHeatmap.result_id == result_id)
        ).scalars().all()
        by_index = {row.finding_index: row for row in rows}
        stored = session.get(Result, result_id)
    assert 1 in by_index
    assert by_index[1].npy_path == stored.heatmap_npy_path


def test_repeat_fetch_uses_the_cached_row(client, auth, result_id):
    from app.core.db import SessionLocal

    assert SessionLocal is not None
    with SessionLocal() as session:
        before = session.execute(
            select(ResultHeatmap).where(
                ResultHeatmap.result_id == result_id, ResultHeatmap.finding_index == 1
            )
        ).scalar_one().npy_path

    again = client.get(
        f"{API}/results/{result_id}/findings/1/heatmap.npy", headers=auth("clinician")
    )
    assert again.status_code == 200

    with SessionLocal() as session:
        rows = session.execute(
            select(ResultHeatmap).where(
                ResultHeatmap.result_id == result_id, ResultHeatmap.finding_index == 1
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].npy_path == before


def test_png_overlay_is_served(client, auth, result_id):
    response = client.get(
        f"{API}/results/{result_id}/findings/1/heatmap.png", headers=auth("clinician")
    )
    assert response.status_code == 200
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_unknown_finding_has_no_heatmap(client, auth, result_id):
    response = client.get(
        f"{API}/results/{result_id}/findings/42/heatmap.npy", headers=auth("clinician")
    )
    assert response.status_code == 404


def test_primary_index_is_the_sorted_position_not_the_class_index():
    from app.modules.results.heatmaps import _primary_index

    document = {
        "classification": {"label": "abnormal"},
        "primary_finding_index": 1,
        "findings": [
            {"label": "abnormal", "probability": 0.53},
            {"label": "normal", "probability": 0.47},
        ],
    }
    assert _primary_index(document) == 0


def test_stale_primary_row_is_not_reused_for_another_label():
    from app.core.schema import Result, ResultHeatmap
    from app.modules.results.heatmaps import _cached_matches_finding

    result = Result(heatmap_npy_path="derived/heatmap.npy")
    document = {"classification": {"label": "abnormal"}}
    stale = ResultHeatmap(label="normal", npy_path="derived/heatmap.npy")
    matching = ResultHeatmap(label="abnormal", npy_path="derived/heatmap.npy")
    own = ResultHeatmap(label="normal", npy_path="derived/heatmap_1.npy")
    assert _cached_matches_finding(result, document, stale) is False
    assert _cached_matches_finding(result, document, matching) is True
    assert _cached_matches_finding(result, document, own) is True


def test_administrator_is_denied_every_heatmap(client, auth, result_id):
    for suffix in ("heatmap.npy", "heatmap.png"):
        for prefix in (f"/results/{result_id}", f"/results/{result_id}/findings/1"):
            response = client.get(f"{API}{prefix}/{suffix}", headers=auth("administrator"))
            assert response.status_code == 403
