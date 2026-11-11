"""Per-finding heatmaps, computed lazily and cached.

The worker stores the CAM for the top finding synchronously. Every other finding
in the result gets its own CAM the first time it is requested and is then cached
in ``result_heatmaps``, so a scan by the viewer does not slow the first result.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import append_audit
from app.core.errors import AppError
from app.core.ids import new_id, utcnow_iso
from app.core.schema import Case, Image, Provenance, Result, ResultHeatmap, User
from app.core.storage import read_blob, resolve_relative
from app.modules.cases.service import can_access_case
from app.modules.inference import service as inference_service
from app.modules.inference.engine import engine_lock, get_engine
from app.modules.preprocessing.profiles import heatmap_mapping
from app.modules.preprocessing.service import load_pixels, to_model_input
from app.modules.results.presenter import band_for, is_flagged
from app.modules.results.service import save_heatmap

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(result_id: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(result_id, threading.Lock())


def result_for(session: Session, user: User, result_id: str) -> tuple[Result, Case]:
    result = session.get(Result, result_id)
    if result is None:
        raise AppError(404, "result_not_found", "Result not found")
    case = session.get(Case, result.case_id)
    if case is None or not can_access_case(user, case):
        raise AppError(404, "result_not_found", "Result not found")
    return result, case


def mapping_for_document(document: dict) -> str:
    """Where the model input sits on the stored image (centre crop or full frame)."""
    stored = (document.get("heatmap") or {}).get("mapping")
    if stored in {"centre", "full"}:
        return stored
    model = document.get("model") or {}
    try:
        entry = inference_service.registry_entry(model.get("name") or "", model.get("version"))
    except AppError:
        entry = {}
    return heatmap_mapping(entry.get("preprocess_profile"))


def _stored_parameters(session: Session, result_id: str) -> dict:
    record = session.execute(
        select(Provenance).where(Provenance.result_id == result_id)
    ).scalar_one_or_none()
    if record is None:
        return {}
    try:
        return json.loads(record.record_json).get("parameters") or {}
    except ValueError:
        return {}


def cam_is_current(session: Session, result: Result, document: dict) -> bool:
    """A cached map from an older CAM layer or method must not be shown as current."""
    parameters = _stored_parameters(session, result.id)
    model = document.get("model") or {}
    try:
        engine = get_engine(model.get("name") or "", model.get("version"))
    except AppError:
        return True
    stored_layer = parameters.get("gradcam_layer")
    if stored_layer and str(stored_layer) != str(engine.cam_layer):
        return False
    stored_method = parameters.get("cam_method")
    if stored_method and str(stored_method) != str(engine.cam_method):
        return False
    return True


def _ref(row: ResultHeatmap, mapping: str = "centre") -> dict:
    return {
        "format": "npy",
        "path": row.npy_path,
        "overlay_png": row.png_path,
        "shape": json.loads(row.shape_json or "[]"),
        "mapping": mapping,
    }


def _existing(session: Session, result_id: str, finding_index: int) -> ResultHeatmap | None:
    return session.execute(
        select(ResultHeatmap).where(
            ResultHeatmap.result_id == result_id, ResultHeatmap.finding_index == finding_index
        )
    ).scalar_one_or_none()


def _primary_index(document: dict) -> int:
    """Position in ``findings`` of the top class, not the model's class index.

    Older documents stored the raw classifier index here, which only coincides
    with the sorted position for some models.
    """
    findings = document.get("findings") or []
    top = str((document.get("classification") or {}).get("label") or "")
    for index, finding in enumerate(findings):
        if str(finding.get("label", "")) == top:
            return index
    if findings:
        return max(range(len(findings)), key=lambda i: float(findings[i].get("probability", 0.0)))
    return 0


def _cached_matches_finding(result: Result, document: dict, row: ResultHeatmap) -> bool:
    """The stored primary CAM was computed for the top class, not for a position."""
    if not result.heatmap_npy_path or row.npy_path != result.heatmap_npy_path:
        return True
    top = str((document.get("classification") or {}).get("label") or "")
    return row.label == top


def _record_primary(
    session: Session, result: Result, finding_index: int, label: str, shape: list[int]
) -> ResultHeatmap:
    row = ResultHeatmap(
        id=new_id("heatmap"),
        result_id=result.id,
        finding_index=finding_index,
        label=label,
        npy_path=result.heatmap_npy_path or "",
        png_path=result.heatmap_png_path or "",
        shape_json=json.dumps(shape),
        created_at=utcnow_iso(),
    )
    session.add(row)
    session.flush()
    return row


def heatmap_ref(session: Session, user: User, result_id: str, finding_index: int) -> dict:
    result, _case = result_for(session, user, result_id)
    document = json.loads(result.document_json or "{}")
    findings = document.get("findings") or []
    if finding_index < 0 or finding_index >= len(findings):
        raise AppError(404, "finding_not_found", "Finding not found")
    finding = findings[finding_index]
    band = band_for(float(finding.get("probability", 0.0)), finding.get("threshold"))
    if not is_flagged({**finding, "band": band}):
        raise AppError(
            404,
            "heatmap_unavailable",
            "No region highlighted for this finding",
        )
    mapping = mapping_for_document(document)
    current = cam_is_current(session, result, document)

    cached = _existing(session, result_id, finding_index)
    if current and cached is not None and _cached_matches_finding(result, document, cached):
        return _ref(cached, mapping)

    with _lock_for(result_id):
        cached = _existing(session, result_id, finding_index)
        if cached is not None:
            if current and _cached_matches_finding(result, document, cached):
                return _ref(cached, mapping)
            session.delete(cached)
            session.commit()
        label = str(findings[finding_index].get("label", cache_label(document)))
        if (
            current
            and finding_index == _primary_index(document)
            and result.heatmap_npy_path
            and result.heatmap_png_path
        ):
            shape = (document.get("heatmap") or {}).get("shape") or []
            row = _record_primary(session, result, finding_index, label, shape)
            append_audit(
                session,
                actor_id=user.id,
                action="heatmap.registered",
                resource_type="result",
                resource_id=result.id,
                detail={"finding_index": finding_index, "label": label},
            )
            session.commit()
            return _ref(row, mapping)

        row = _compute(session, user, result, document, findings[finding_index], finding_index)
        return _ref(row, mapping)


def cache_label(document: dict) -> str:
    classification = document.get("classification") or {}
    return str(classification.get("label", "finding"))


def _compute(
    session: Session,
    user: User,
    result: Result,
    document: dict,
    finding: dict,
    finding_index: int,
) -> ResultHeatmap:
    image = session.get(Image, result.image_id)
    if image is None:
        raise AppError(404, "image_not_found", "Image for this result is no longer available")
    model = document.get("model") or {}
    model_id = model.get("name") or "chest_densenet121"
    engine = get_engine(model_id, model.get("version"))
    if model.get("version") and model.get("version") != engine.version:
        raise AppError(
            409,
            "model_version_unavailable",
            "The model version that produced this result is not available",
        )
    try:
        entry = inference_service.registry_entry(model_id, model.get("version"))
    except AppError:
        entry = {}
    profile = entry.get("preprocess_profile") or engine.preprocess_profile
    label = str(finding.get("label", cache_label(document)))
    array, meta = load_pixels(image.mime, read_blob(image.blob_digest))
    model_input, _stats = to_model_input(
        array, photometric=meta.get("photometric", ""), profile=profile
    )
    with engine_lock(model_id, engine.version):
        cam = engine.gradcam(model_input, target_index=engine.target_index(label))
    values = np.asarray(cam)
    if values.size == 0 or float(values.max()) <= float(values.min()):
        raise AppError(
            404,
            "heatmap_unavailable",
            "The model produced no usable attention for this finding",
        )
    saved = save_heatmap(
        cam, result.case_id, image.id, suffix=f"_{result.id}_{finding_index}"
    )

    row = ResultHeatmap(
        id=new_id("heatmap"),
        result_id=result.id,
        finding_index=finding_index,
        label=label,
        npy_path=saved["path"],
        png_path=saved["overlay_png"],
        shape_json=json.dumps(saved["shape"]),
        created_at=utcnow_iso(),
    )
    session.add(row)
    append_audit(
        session,
        actor_id=user.id,
        action="heatmap.created",
        resource_type="result",
        resource_id=result.id,
        detail={"finding_index": finding_index, "label": label},
    )
    session.commit()
    return row


def heatmaps_for_result(session: Session, result_id: str) -> dict[int, dict]:
    rows = (
        session.execute(select(ResultHeatmap).where(ResultHeatmap.result_id == result_id))
        .scalars()
        .all()
    )
    result = session.get(Result, result_id)
    mapping = "centre"
    if result is not None:
        document = json.loads(result.document_json or "{}")
        mapping = mapping_for_document(document)
        if not cam_is_current(session, result, document):
            return {}
    return {row.finding_index: _ref(row, mapping) for row in rows}


def file_path(ref: dict, fmt: str) -> Path:
    key = "overlay_png" if fmt == "png" else "path"
    relative_path = ref.get(key)
    if not relative_path:
        raise AppError(404, "heatmap_not_found", "Heatmap not available")
    return resolve_relative(relative_path)
