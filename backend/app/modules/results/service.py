from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import append_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.ids import new_id, utcnow_iso
from app.core.schema import Image, Job, Provenance, Result, ResultHeatmap
from app.core.storage import relative
from app.modules.results.schemas import ResultDocument


def _derived_dir(case_id: str, image_id: str) -> Path:
    directory = get_settings().derived_dir / case_id / image_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_heatmap(cam: np.ndarray, case_id: str, image_id: str, *, suffix: str = "") -> dict:
    from PIL import Image as PILImage

    directory = _derived_dir(case_id, image_id)
    cam = np.asarray(cam, dtype=np.float32)
    cam = np.clip(cam, 0.0, 1.0)

    npy_path = directory / f"heatmap{suffix}.npy"
    npy_temp = directory / f".heatmap{suffix}.npy.tmp"
    with npy_temp.open("wb") as handle:
        np.save(handle, cam)
    os.replace(npy_temp, npy_path)

    rgba = np.zeros((*cam.shape, 4), dtype=np.uint8)
    rgba[..., 0] = 255
    rgba[..., 1] = (255 * (1.0 - cam)).astype(np.uint8)
    rgba[..., 3] = (200 * cam).astype(np.uint8)
    png_path = directory / f"heatmap{suffix}.png"
    png_temp = directory / f".heatmap{suffix}.png.tmp"
    PILImage.fromarray(rgba, mode="RGBA").save(png_temp, format="PNG")
    os.replace(png_temp, png_path)

    return {
        "format": "npy",
        "path": relative(npy_path),
        "overlay_png": relative(png_path),
        "shape": [int(cam.shape[0]), int(cam.shape[1])],
    }


def create_result(
    session: Session,
    *,
    job: Job,
    image: Image,
    document: ResultDocument,
    cam: np.ndarray | None,
    primary_index: int = 0,
    parameters: dict | None = None,
    heatmap_mapping: str = "centre",
) -> Result:
    result_id = new_id("result")
    # Results for the same image must not overwrite each other's maps.
    heatmap = (
        save_heatmap(cam, job.case_id, image.id, suffix=f"_{result_id}")
        if cam is not None
        else None
    )
    if heatmap is not None:
        heatmap["mapping"] = heatmap_mapping
    document_payload = document.model_dump()
    document_payload["heatmap"] = heatmap
    document_payload["primary_finding_index"] = primary_index

    provenance_id = new_id("provenance")
    document_payload["provenance_id"] = provenance_id

    record = build_provenance(
        result_id=None,
        provenance_id=provenance_id,
        job=job,
        image=image,
        document=document_payload,
        parameters=parameters,
    )
    created_at = utcnow_iso()

    result = Result(
        id=result_id,
        job_id=job.id,
        image_id=image.id,
        case_id=job.case_id,
        document_json=json.dumps(document_payload, sort_keys=True),
        heatmap_npy_path=heatmap["path"] if heatmap else None,
        heatmap_png_path=heatmap["overlay_png"] if heatmap else None,
        model_digest=(document.model.digest or None),
        created_at=created_at,
    )
    session.add(result)
    session.flush()

    if heatmap is not None:
        label = ""
        if 0 <= primary_index < len(document_payload.get("findings", [])):
            label = str(document_payload["findings"][primary_index].get("label", ""))
        session.add(
            ResultHeatmap(
                id=new_id("heatmap"),
                result_id=result.id,
                finding_index=primary_index,
                label=label,
                npy_path=heatmap["path"],
                png_path=heatmap["overlay_png"],
                shape_json=json.dumps(heatmap["shape"]),
                created_at=created_at,
            )
        )

    record["result_id"] = result.id
    session.add(
        Provenance(
            id=provenance_id,
            result_id=result.id,
            record_json=json.dumps(record, sort_keys=True),
            created_at=created_at,
        )
    )

    append_audit(
        session,
        actor_id=job.requested_by,
        action="result.created",
        resource_type="result",
        resource_id=result.id,
        detail={"job_id": job.id, "model": document.model.model_dump()},
    )
    return result


def build_provenance(
    *,
    result_id: str | None,
    provenance_id: str,
    job: Job,
    image: Image,
    document: dict,
    parameters: dict | None = None,
) -> dict:
    import platform
    import subprocess

    from app.core.config import REPO_ROOT

    try:
        code_commit = (
            subprocess.check_output(
                ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            or "uncommitted"
        )
    except Exception:
        code_commit = "uncommitted"

    heatmap = document.get("heatmap") or {}
    runtime_parameters = parameters or {
        "input_size": 224,
        "normalisation": "torchxrayvision.datasets.normalize(img, 255)",
        "threshold": 0.5,
        "gradcam_layer": "features.norm5",
    }
    runtime_parameters = dict(runtime_parameters)
    runtime_parameters["heatmap_shape"] = heatmap.get("shape")
    return {
        "record_id": provenance_id,
        "result_id": result_id,
        "job_id": job.id,
        "inputs": [
            {"role": "original_upload", "digest": image.original_digest, "retained": False},
            {"role": "deidentified_image", "digest": image.blob_digest, "retained": True},
        ],
        "model": document.get("model", {}),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "backend": "torch-cpu" if document.get("model", {}).get("demo") is False else "stub",
        },
        "parameters": runtime_parameters,
        "code_commit": code_commit,
        "seed": 0,
        "operator": job.requested_by,
        "created_at": utcnow_iso(),
    }


def latest_result_for_job(session: Session, job_id: str) -> Result | None:
    return session.execute(select(Result).where(Result.job_id == job_id)).scalar_one_or_none()


def result_or_409(session: Session, job: Job) -> Result:
    result = latest_result_for_job(session, job.id)
    if result is None or job.state != "completed":
        raise AppError(409, "job_not_complete", "Analysis has not completed", f"Current state: {job.state}")
    return result


def provenance_for(session: Session, result: Result) -> dict:
    record = session.execute(select(Provenance).where(Provenance.result_id == result.id)).scalar_one_or_none()
    if record is None:
        raise AppError(404, "provenance_not_found", "Provenance record not found")
    return json.loads(record.record_json)
