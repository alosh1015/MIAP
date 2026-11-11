"""Mammography exam analysis: one job per view, plus a deterministic summary.

Views are never stitched into a mosaic for the model. Each view is scored on its
own and the summary takes the highest density category per breast, which is the
screening convention, with an explicit caveat.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import append_audit
from app.core.errors import AppError
from app.core.ids import new_id, utcnow_iso
from app.core.schema import AnalysisBatch, Case, Image, Job, Result, User
from app.modules.cases.service import can_access_case
from app.modules.inference import service as inference_service
from app.modules.routing.service import (
    group_mammogram_views,
    normalise_laterality,
    normalise_view,
    resolve_model_for_image,
)

DENSITY_RANK = {"A": 0, "B": 1, "C": 2, "D": 3}
DENSITY_TEXT = {
    "A": "mostly fatty tissue",
    "B": "scattered dense tissue",
    "C": "heterogeneously dense tissue",
    "D": "extremely dense tissue",
}
CAVEAT = (
    "Breast density is a qualitative BI-RADS-style category from a model that has "
    "not been calibrated on local patients. It is not a cancer screen and does not "
    "replace radiologist assessment."
)


def _mammograms(session: Session, case_id: str) -> list[Image]:
    return (
        session.execute(
            select(Image)
            .where(Image.case_id == case_id, Image.modality == "mammogram")
            .order_by(Image.created_at)
        )
        .scalars()
        .all()
    )


def submit_exam(
    session: Session, user: User, case: Case, image_ids: list[str] | None = None
) -> tuple[AnalysisBatch, list[str]]:
    images = _mammograms(session, case.id)
    if image_ids:
        wanted = set(image_ids)
        images = [image for image in images if image.id in wanted]
        if len(images) != len(wanted):
            raise AppError(422, "image_not_in_case", "One or more images are not mammograms in this case")
    if not images:
        raise AppError(422, "no_images", "This case has no mammogram images to analyse")

    plan: list[tuple[Image, dict[str, Any]]] = []
    for image in images:
        entry, _bucket = resolve_model_for_image(session, image)
        plan.append((image, entry))

    now = utcnow_iso()
    model_ids = sorted({entry["model_id"] for _image, entry in plan})
    versions = {entry["version"] for _image, entry in plan}
    batch = AnalysisBatch(
        id=new_id("batch"),
        case_id=case.id,
        requested_by=user.id,
        model_id="+".join(model_ids),
        model_version=versions.pop() if len(versions) == 1 else None,
        state="queued",
        total=len(plan),
        completed=0,
        failed=0,
        created_at=now,
        updated_at=now,
    )
    session.add(batch)
    session.flush()

    job_ids: list[str] = []
    for image, entry in plan:
        job = Job(
            id=new_id("job"),
            case_id=case.id,
            image_id=image.id,
            state="queued",
            progress=0.0,
            idempotency_key=f"exam:{batch.id}:{image.id}",
            batch_id=batch.id,
            model_id=entry["model_id"],
            model_version=entry["version"],
            params_json=json.dumps(inference_service.params_for(entry, {}), sort_keys=True),
            attempts=0,
            requested_by=user.id,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        job_ids.append(job.id)

    append_audit(
        session,
        actor_id=user.id,
        action="batch.submitted",
        resource_type="analysis_batch",
        resource_id=batch.id,
        detail={
            "case_id": case.id,
            "kind": "mammogram_exam",
            "images": len(images),
            "models": model_ids,
            "jobs": len(job_ids),
        },
    )
    return batch, job_ids


def _latest_completed(session: Session, case_id: str, image_id: str) -> tuple[Job, Result] | None:
    row = session.execute(
        select(Job, Result)
        .join(Result, Result.job_id == Job.id)
        .where(Job.case_id == case_id, Job.image_id == image_id, Job.state == "completed")
        .order_by(Job.created_at.desc())
    ).first()
    return (row[0], row[1]) if row else None


def _density_of(document: dict[str, Any]) -> str | None:
    value = document.get("density")
    if not value:
        classification = document.get("classification") or {}
        value = classification.get("label")
    token = str(value or "").strip().upper()
    return token if token in DENSITY_RANK else None


def exam_summary(session: Session, user: User, case_id: str) -> dict[str, Any]:
    case = session.get(Case, case_id)
    if case is None or not can_access_case(user, case):
        raise AppError(404, "case_not_found", "Case not found")

    images = _mammograms(session, case.id)
    grouped = group_mammogram_views(
        [
            {"id": image.id, "laterality": image.laterality, "view": image.view}
            for image in images
        ]
    )

    views: dict[str, dict[str, Any]] = {}
    for image in images:
        laterality = normalise_laterality(image.laterality)
        view = normalise_view(image.view)
        key = f"{laterality}{view}" if laterality and view else image.id
        outcome = _latest_completed(session, case.id, image.id)
        entry: dict[str, Any] = {
            "image_id": image.id,
            "view": key,
            "laterality": laterality,
            "position": view,
            "result_id": None,
            "job_id": None,
            "density": None,
            "density_text": None,
            "probability": None,
            "model": None,
            "degraded": False,
        }
        if outcome is not None:
            job, result = outcome
            document = json.loads(result.document_json or "{}")
            density = _density_of(document)
            entry.update(
                {
                    "result_id": result.id,
                    "job_id": job.id,
                    "density": density,
                    "density_text": DENSITY_TEXT.get(density or ""),
                    "probability": (document.get("classification") or {}).get("probability"),
                    "model": document.get("model"),
                    "degraded": bool(document.get("degraded")),
                }
            )
        views[key] = entry

    breasts: dict[str, dict[str, Any]] = {}
    for side in ("L", "R"):
        considered = [entry for entry in views.values() if entry["laterality"] == side]
        evaluated = [entry for entry in considered if entry["density"] in DENSITY_RANK]
        highest = max(evaluated, key=lambda entry: DENSITY_RANK[entry["density"]], default=None)
        breasts[side] = {
            "density": highest["density"] if highest else None,
            "density_text": DENSITY_TEXT.get(highest["density"]) if highest else None,
            "views_evaluated": [entry["view"] for entry in evaluated],
            "views_pending": [entry["view"] for entry in considered if entry["view"] not in {
                item["view"] for item in evaluated
            }],
            "single_view": len(evaluated) == 1,
        }

    return {
        "case_id": case.id,
        "exam": "mammogram_four_view",
        "complete": grouped["complete"],
        "missing": grouped["missing"],
        "duplicates": grouped["duplicates"],
        "unassigned": grouped["unassigned"],
        "views": views,
        "breasts": breasts,
        "any_result": any(entry["result_id"] for entry in views.values()),
        "caveat": CAVEAT,
    }
