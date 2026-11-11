from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import append_audit
from app.core.db import get_session
from app.core.deps import require_image_reader, require_roles
from app.core.errors import AppError
from app.core.ids import new_id, utcnow_iso
from app.core.schema import Case, Image, Job, Result, User
from app.core.storage import resolve_relative
from app.modules.cases.service import can_access_case
from app.modules.inference import batch as batch_service
from app.modules.inference import exam as exam_service
from app.modules.inference import service as inference_service
from app.modules.inference.schemas import (
    AnalysisRequest,
    BatchAnalysisRequest,
    ExamAnalysisRequest,
)
from app.modules.inference.worker import runner
from app.modules.results import heatmaps as heatmap_service
from app.modules.results.presenter import present_document
from app.modules.results.service import provenance_for, result_or_409
from app.modules.reviews import service as review_service
from app.modules.routing.service import resolve_model_for_image

router = APIRouter(tags=["analyses"])


def _job_dict(job: Job) -> dict:
    error = None
    if job.error_code:
        error = {"code": job.error_code, "detail": job.error_detail}
    return {
        "job_id": job.id,
        "case_id": job.case_id,
        "image_id": job.image_id,
        "state": job.state,
        "progress": job.progress,
        "model_id": job.model_id,
        "model_version": job.model_version,
        "error": error,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def _load_job(session: Session, user: User, job_id: str) -> tuple[Job, Case]:
    job = session.get(Job, job_id)
    if job is None:
        raise AppError(404, "job_not_found", "Analysis job not found")
    case = session.get(Case, job.case_id)
    if user.role == "administrator":
        return job, case
    if job.requested_by == user.id:
        return job, case
    if user.role == "researcher" and case is not None and can_access_case(user, case):
        return job, case
    raise AppError(404, "job_not_found", "Analysis job not found")


@router.post("/analyses", status_code=202)
def submit_analysis(
    payload: AnalysisRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician", "researcher")),
) -> JSONResponse:
    case = session.get(Case, payload.case_id)
    if case is None or not can_access_case(user, case):
        raise AppError(404, "case_not_found", "Case not found")
    image = session.get(Image, payload.image_id)
    if image is None or image.case_id != case.id:
        raise AppError(422, "image_not_in_case", "Image does not belong to this case")

    existing = session.execute(select(Job).where(Job.idempotency_key == idempotency_key)).scalar_one_or_none()
    if existing is not None:
        if existing.case_id != payload.case_id or existing.image_id != payload.image_id:
            raise AppError(
                422,
                "idempotency_conflict",
                "This Idempotency-Key was used for a different analysis",
            )
        return JSONResponse(_job_dict(existing), status_code=202)

    entry, _bucket = resolve_model_for_image(
        session, image, payload.model_id, payload.model_version
    )
    now = utcnow_iso()
    job = Job(
        id=new_id("job"),
        case_id=case.id,
        image_id=image.id,
        state="queued",
        progress=0.0,
        idempotency_key=idempotency_key,
        model_id=entry["model_id"],
        model_version=entry["version"],
        params_json=json.dumps(inference_service.params_for(entry, payload.params), sort_keys=True),
        attempts=0,
        requested_by=user.id,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    append_audit(
        session,
        actor_id=user.id,
        action="job.submitted",
        resource_type="job",
        resource_id=job.id,
        detail={
            "case_id": case.id,
            "image_id": image.id,
            "model": {"id": entry["model_id"], "version": entry["version"]},
        },
    )
    session.commit()

    runner.submit(job.id)
    return JSONResponse(
        _job_dict(job),
        status_code=202,
        headers={"Location": f"/api/v1/analyses/{job.id}"},
    )


@router.post("/analyses/batch", status_code=202)
def submit_batch(
    payload: BatchAnalysisRequest,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician", "researcher")),
) -> JSONResponse:
    batch, job_ids = batch_service.submit_batch(session, user, payload)
    session.commit()
    for job_id in job_ids:
        runner.submit(job_id)
    return JSONResponse(
        batch_service.batch_dict(session, batch),
        status_code=202,
        headers={"Location": f"/api/v1/analyses/batch/{batch.id}"},
    )


@router.post("/analyses/exam", status_code=202)
def submit_exam(
    payload: ExamAnalysisRequest,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician", "researcher")),
) -> JSONResponse:
    case = session.get(Case, payload.case_id)
    if case is None or not can_access_case(user, case):
        raise AppError(404, "case_not_found", "Case not found")
    batch, job_ids = exam_service.submit_exam(session, user, case, payload.image_ids)
    session.commit()
    for job_id in job_ids:
        runner.submit(job_id)
    return JSONResponse(
        batch_service.batch_dict(session, batch),
        status_code=202,
        headers={"Location": f"/api/v1/analyses/batch/{batch.id}"},
    )


@router.get("/analyses/batches")
def list_batches(    limit: int = Query(default=25, ge=1, le=100),
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician", "researcher")),
) -> list[dict]:
    return batch_service.list_batches(session, user, limit=limit)


@router.get("/analyses/batch/{batch_id}")
def get_batch(
    batch_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician", "researcher")),
) -> dict:
    return batch_service.get_batch(session, user, batch_id)


@router.get("/analyses/{job_id}")
def get_analysis(
    job_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician", "researcher", "administrator")),
) -> dict:
    job, _case = _load_job(session, user, job_id)
    return _job_dict(job)


@router.get("/analyses/{job_id}/result")
def get_result(
    job_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician", "researcher")),
) -> dict:
    job, _case = _load_job(session, user, job_id)
    result = result_or_409(session, job)
    document = json.loads(result.document_json)
    case = session.get(Case, result.case_id)
    include_notes = user.role == "clinician" and case is not None and case.created_by == user.id
    reviews = review_service.review_map(session, user, result, include_notes=include_notes)
    payload = present_document(
        document,
        heatmaps=heatmap_service.heatmaps_for_result(session, result.id),
        reviews=reviews,
    )
    if not heatmap_service.cam_is_current(session, result, document):
        payload["heatmap"] = None
    payload["result_id"] = result.id
    payload["heatmap_mapping"] = heatmap_service.mapping_for_document(document)
    return payload


@router.get("/analyses/{job_id}/provenance")
def get_provenance(
    job_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician", "researcher")),
) -> dict:
    job, _case = _load_job(session, user, job_id)
    result = result_or_409(session, job)
    return provenance_for(session, result)


@router.get("/results/{result_id}/findings/{finding_index}/heatmap.npy")
def get_finding_heatmap_npy(
    result_id: str,
    finding_index: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_image_reader),
) -> FileResponse:
    ref = heatmap_service.heatmap_ref(session, user, result_id, finding_index)
    return FileResponse(
        heatmap_service.file_path(ref, "npy"), media_type="application/octet-stream"
    )


@router.get("/results/{result_id}/findings/{finding_index}/heatmap.png")
def get_finding_heatmap_png(
    result_id: str,
    finding_index: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_image_reader),
) -> FileResponse:
    ref = heatmap_service.heatmap_ref(session, user, result_id, finding_index)
    return FileResponse(heatmap_service.file_path(ref, "png"), media_type="image/png")


@router.get("/results/{result_id}/heatmap.npy")
def get_heatmap_npy(
    result_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_image_reader),
) -> FileResponse:
    result = session.get(Result, result_id)
    if result is None:
        raise AppError(404, "result_not_found", "Result not found")
    case = session.get(Case, result.case_id)
    if case is None or not can_access_case(user, case):
        raise AppError(404, "result_not_found", "Result not found")
    if not result.heatmap_npy_path:
        raise AppError(404, "heatmap_not_found", "No heatmap for this result")
    return FileResponse(resolve_relative(result.heatmap_npy_path), media_type="application/octet-stream")


@router.get("/results/{result_id}/heatmap.png")
def get_heatmap_png(
    result_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_image_reader),
) -> FileResponse:
    result = session.get(Result, result_id)
    if result is None:
        raise AppError(404, "result_not_found", "Result not found")
    case = session.get(Case, result.case_id)
    if case is None or not can_access_case(user, case):
        raise AppError(404, "result_not_found", "Result not found")
    if not result.heatmap_png_path:
        raise AppError(404, "heatmap_not_found", "No heatmap for this result")
    return FileResponse(resolve_relative(result.heatmap_png_path), media_type="image/png")
