from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header
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
from app.modules.inference import service as inference_service
from app.modules.inference.schemas import AnalysisRequest
from app.modules.inference.worker import runner
from app.modules.results.service import provenance_for, result_or_409
from app.modules.routing.service import capability_for

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

    if image.modality != "xray":
        raise AppError(
            409,
            "analysis_not_supported",
            "Analysis is not available for this modality",
            "Mammogram AI analysis is out of scope; four-view viewing is supported.",
        )
    if not capability_for(image.body_part or "unrecognised")["supported"]:
        raise AppError(
            409,
            "analysis_not_supported",
            "Analysis is not available for this body region",
            f"Region: {image.body_part}. This cycle supports chest X-ray.",
        )

    existing = session.execute(select(Job).where(Job.idempotency_key == idempotency_key)).scalar_one_or_none()
    if existing is not None:
        if existing.case_id != payload.case_id or existing.image_id != payload.image_id:
            raise AppError(
                422,
                "idempotency_conflict",
                "This Idempotency-Key was used for a different analysis",
            )
        return JSONResponse(_job_dict(existing), status_code=202)

    entry = inference_service.select_model(payload.model_id, payload.model_version)
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
    return json.loads(result.document_json)


@router.get("/analyses/{job_id}/provenance")
def get_provenance(
    job_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician", "researcher")),
) -> dict:
    job, _case = _load_job(session, user, job_id)
    result = result_or_409(session, job)
    return provenance_for(session, result)


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
