"""Batch analysis: one job per (image, model) pair with per-item idempotency keys."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import append_audit
from app.core.errors import AppError
from app.core.ids import new_id, utcnow_iso
from app.core.schema import AnalysisBatch, Case, Image, Job, User
from app.modules.cases.service import can_access_case
from app.modules.inference import service as inference_service
from app.modules.inference.schemas import BatchAnalysisRequest
from app.modules.routing.service import (
    bucket_for,
    entry_covers,
    resolve_model_for_image,
)
from app.modules.settings.service import get_system_settings


def _job_dict(job: Job) -> dict:
    return {
        "job_id": job.id,
        "image_id": job.image_id,
        "state": job.state,
        "progress": job.progress,
        "model_id": job.model_id,
        "model_version": job.model_version,
        "error": (
            {"code": job.error_code, "detail": job.error_detail} if job.error_code else None
        ),
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def batch_dict(session: Session, batch: AnalysisBatch) -> dict:
    jobs = (
        session.execute(select(Job).where(Job.batch_id == batch.id).order_by(Job.created_at))
        .scalars()
        .all()
    )
    states: dict[str, int] = {}
    for job in jobs:
        states[job.state] = states.get(job.state, 0) + 1
    return {
        "batch_id": batch.id,
        "case_id": batch.case_id,
        "model_id": batch.model_id,
        "model_version": batch.model_version,
        "state": batch.state,
        "total": len(jobs),
        "counts": states,
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
        "items": [_job_dict(job) for job in jobs],
    }


def submit_batch(session: Session, user: User, payload: BatchAnalysisRequest) -> tuple[AnalysisBatch, list[str]]:
    case = session.get(Case, payload.case_id)
    if case is None or not can_access_case(user, case):
        raise AppError(404, "case_not_found", "Case not found")
    statement = select(Image).where(Image.case_id == case.id).order_by(Image.created_at)
    if payload.image_ids:
        statement = statement.where(Image.id.in_(payload.image_ids))
    images = session.execute(statement).scalars().all()
    if not images:
        raise AppError(422, "no_images", "This case has no images to analyse")
    if payload.image_ids and len(images) != len(set(payload.image_ids)):
        raise AppError(422, "image_not_in_case", "One or more images do not belong to this case")

    limit = get_system_settings(session).max_batch_images
    if len(images) > limit:
        raise AppError(422, "batch_too_large", f"At most {limit} images per batch")

    for image in images:
        bucket = bucket_for(image.body_part, image.modality)
        if bucket in {"unsupported", "unrecognised"}:
            raise AppError(
                409,
                "analysis_not_supported",
                "Analysis is not available for this study",
                f"capability: {bucket}",
            )

    choices = payload.models
    if choices:
        entries = [
            inference_service.select_model(
                choice.model_id,
                choice.model_version,
                session,
            )
            for choice in choices
        ]
        plan: list[tuple[Image, dict]] = []
        for image in images:
            bucket = bucket_for(image.body_part, image.modality)
            for entry in entries:
                if not entry_covers(entry, image, bucket):
                    raise AppError(
                        409,
                        "model_scope_mismatch",
                        "A requested model does not cover this study",
                        f"capability: {bucket}",
                    )
                plan.append((image, entry))
    else:
        plan = [
            (image, resolve_model_for_image(session, image)[0])
            for image in images
        ]

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
            idempotency_key=f"batch:{batch.id}:{image.id}:{entry['model_id']}:{entry['version']}",
            batch_id=batch.id,
            model_id=entry["model_id"],
            model_version=entry["version"],
            params_json=json.dumps(
                inference_service.params_for(entry, payload.params), sort_keys=True
            ),
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
            "images": len(images),
            "models": model_ids,
            "jobs": len(job_ids),
        },
    )
    return batch, job_ids


def list_batches(session: Session, user: User, limit: int = 25) -> list[dict]:
    batches = (
        session.execute(
            select(AnalysisBatch).order_by(AnalysisBatch.created_at.desc()).limit(200)
        )
        .scalars()
        .all()
    )
    cases: dict[str, Case | None] = {}
    visible: list[dict] = []
    for batch in batches:
        if batch.requested_by != user.id:
            if batch.case_id not in cases:
                cases[batch.case_id] = session.get(Case, batch.case_id)
            case = cases[batch.case_id]
            if case is None or not can_access_case(user, case):
                continue
        visible.append(batch_dict(session, batch))
        if len(visible) >= limit:
            break
    return visible


def get_batch(session: Session, user: User, batch_id: str) -> dict:
    batch = session.get(AnalysisBatch, batch_id)
    if batch is None:
        raise AppError(404, "batch_not_found", "Batch not found")
    if batch.requested_by != user.id:
        case = session.get(Case, batch.case_id)
        if case is None or not can_access_case(user, case):
            raise AppError(404, "batch_not_found", "Batch not found")
    return batch_dict(session, batch)
