from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import append_audit, write_audit_now
from app.core.errors import AppError
from app.core.ids import new_id, utcnow, utcnow_iso
from app.core.schema import Case, FindingReview, Image, Job, Patient, Result, User
from app.modules.cases.schemas import CaseCreate, ImageSummary, retention_until
from app.modules.patients import service as patient_service
from app.modules.patients.schemas import PatientSummary
from app.modules.results.presenter import band_for
from app.modules.routing.service import capability_for, group_mammogram_views, normalise_laterality, normalise_view

IMAGE_ROLES = {"clinician", "researcher"}
SORT_KEYS = {
    "created_at",
    "patient",
    "pseudonym",
    "status",
    "modality",
    "image_count",
    "ai_flag",
    "findings_to_review",
    "reviewed",
}
AI_FLAGS = {"flagged", "clear", "pending", "failed", "none"}


def _case_filter(user: User):
    if user.role == "administrator":
        return None
    if user.role == "researcher":
        return (Case.created_by == user.id) | (Case.consent == "research")
    return Case.created_by == user.id


def can_access_case(user: User, case: Case) -> bool:
    if user.role == "administrator":
        return True
    if case.created_by == user.id:
        return True
    return user.role == "researcher" and case.consent == "research"


def assert_case_access(user: User, case: Case | None) -> Case:
    if case is None or not can_access_case(user, case):
        raise AppError(404, "case_not_found", "Case not found")
    return case


def create_case(session: Session, user: User, payload: CaseCreate) -> Case:
    if user.role not in IMAGE_ROLES:
        raise AppError(403, "forbidden", "Administrators cannot create cases")
    if payload.patient_id:
        if user.role != "clinician":
            raise AppError(403, "identity_forbidden", "Only clinicians can link a patient")
        patient = session.get(Patient, payload.patient_id)
        if patient is None or patient.owner_id != user.id:
            raise AppError(404, "patient_not_found", "Patient not found")
    now = utcnow()
    case = Case(
        id=new_id("case"),
        pseudonym=payload.pseudonym.strip(),
        consent=payload.consent,
        created_by=user.id,
        patient_id=payload.patient_id,
        status="created",
        modality=None,
        retention_until=retention_until(payload.retention_days, now),
        created_at=utcnow_iso(),
    )
    session.add(case)
    append_audit(
        session,
        actor_id=user.id,
        action="case.created",
        resource_type="case",
        resource_id=case.id,
        detail={"consent": payload.consent, "patient_id": case.patient_id},
    )
    return case


def _image_counts(session: Session, case_ids: list[str]) -> dict[str, int]:
    if not case_ids:
        return {}
    rows = session.execute(
        select(Image.case_id, func.count(Image.id)).where(Image.case_id.in_(case_ids)).group_by(Image.case_id)
    ).all()
    return {case_id: count for case_id, count in rows}


def _latest_jobs(session: Session, case_ids: list[str]) -> dict[str, Job]:
    if not case_ids:
        return {}
    jobs = (
        session.execute(
            select(Job).where(Job.case_id.in_(case_ids)).order_by(Job.created_at.desc())
        )
        .scalars()
        .all()
    )
    latest: dict[str, Job] = {}
    for job in jobs:
        latest.setdefault(job.case_id, job)
    return latest


def _results_by_job(session: Session, job_ids: list[str]) -> dict[str, Result]:
    if not job_ids:
        return {}
    results = session.execute(select(Result).where(Result.job_id.in_(job_ids))).scalars().all()
    return {result.job_id: result for result in results}


def _reviews_by_result(session: Session, result_ids: list[str]) -> dict[str, dict[int, FindingReview]]:
    if not result_ids:
        return {}
    reviews = (
        session.execute(select(FindingReview).where(FindingReview.result_id.in_(result_ids)))
        .scalars()
        .all()
    )
    grouped: dict[str, dict[int, FindingReview]] = {}
    for review in reviews:
        grouped.setdefault(review.result_id, {})[review.finding_index] = review
    return grouped


def _patient_map(session: Session, user: User, case_ids: list[str]) -> dict[str, dict]:
    """Decrypt identity for case owners only; never for researchers or admins."""
    if user.role != "clinician" or not case_ids:
        return {}
    cases = session.execute(select(Case).where(Case.id.in_(case_ids), Case.patient_id.is_not(None))).scalars().all()
    patient_ids = {case.patient_id for case in cases if case.patient_id and case.created_by == user.id}
    if not patient_ids:
        return {}
    patients = session.execute(
        select(Patient).where(Patient.id.in_(patient_ids), Patient.owner_id == user.id)
    ).scalars().all()
    return {
        patient.id: patient_service.decrypt_identity_or_422(patient, user.id) for patient in patients
    }


def _ai_state(job: Job | None, result: Result | None, reviews: dict[int, FindingReview]):
    if job is None:
        return None, 0, 0, None
    if job.state in {"queued", "running", "created", "validated"}:
        return "pending", 0, 0, None
    if job.state == "failed":
        return "failed", 0, 0, None
    if result is None:
        return "pending", 0, 0, None
    document = json.loads(result.document_json or "{}")
    findings = document.get("findings") or []
    flagged = False
    needs_review: set[int] = set()
    for index, finding in enumerate(findings):
        band = band_for(float(finding.get("probability", 0.0)), finding.get("threshold"))
        if band == "above_threshold":
            flagged = True
        if band in {"above_threshold", "borderline"}:
            needs_review.add(index)
    reviewed = len(needs_review.intersection(reviews))
    return ("flagged" if flagged else "clear"), len(needs_review), reviewed, result.id


def summary_for_case(
    session: Session,
    user: User,
    case: Case,
    *,
    image_count: int,
    job: Job | None,
    result: Result | None,
    reviews: dict[int, FindingReview],
    identity: dict | None,
) -> dict:
    ai_flag, to_review, reviewed, latest_result_id = _ai_state(job, result, reviews)
    visible = bool(identity) and user.role == "clinician"
    if visible:
        display = f"{identity.get('name', '')} · {identity.get('hospital_number', '')}".strip(" ·")
    else:
        display = case.pseudonym
    return {
        "id": case.id,
        "pseudonym": case.pseudonym,
        "consent": case.consent,
        "status": case.status,
        "modality": case.modality,
        "created_at": case.created_at,
        "image_count": image_count,
        "patient_id": case.patient_id if visible else None,
        "patient_display": display,
        "identity_visible": visible,
        "ai_flag": ai_flag,
        "findings_to_review": to_review,
        "reviewed": reviewed,
        "latest_result_id": latest_result_id,
        "last_job": (
            {
                "id": job.id,
                "state": job.state,
                "progress": job.progress,
                "error_code": job.error_code,
                "updated_at": job.updated_at,
            }
            if job
            else None
        ),
    }


def _summaries(session: Session, user: User, cases: list[Case]) -> list[dict]:
    if not cases:
        return []
    case_ids = [case.id for case in cases]
    counts = _image_counts(session, case_ids)
    jobs = _latest_jobs(session, case_ids)
    results = _results_by_job(session, [job.id for job in jobs.values()])
    reviews = _reviews_by_result(session, [result.id for result in results.values()])
    identities = _patient_map(session, user, case_ids)
    summaries = []
    for case in cases:
        job = jobs.get(case.id)
        result = results.get(job.id) if job else None
        summaries.append(
            summary_for_case(
                session,
                user,
                case,
                image_count=counts.get(case.id, 0),
                job=job,
                result=result,
                reviews=reviews.get(result.id, {}) if result else {},
                identity=identities.get(case.patient_id or ""),
            )
        )
    return summaries


def list_cases(
    session: Session,
    user: User,
    *,
    limit: int = 50,
    offset: int = 0,
    sort: str = "created_at",
    order: str = "desc",
    ai_flag: str | None = None,
    modality: str | None = None,
    consent: str | None = None,
    q: str | None = None,
) -> list[dict]:
    if sort not in SORT_KEYS:
        raise AppError(422, "invalid_sort", "Unsupported sort column", sort)
    if order not in {"asc", "desc"}:
        raise AppError(422, "invalid_order", "Sort order must be asc or desc")
    if ai_flag is not None and ai_flag not in AI_FLAGS:
        raise AppError(422, "invalid_ai_flag", "Unsupported AI flag", ai_flag)

    statement = select(Case)
    condition = _case_filter(user)
    if condition is not None:
        statement = statement.where(condition)
    if modality:
        statement = statement.where(Case.modality == modality)
    if consent:
        statement = statement.where(Case.consent == consent)
    if q:
        statement = statement.where(Case.pseudonym.ilike(f"%{q.strip()}%"))
    cases = session.execute(statement.order_by(Case.created_at.desc()).limit(1000)).scalars().all()
    summaries = _summaries(session, user, cases)

    if ai_flag is not None:
        wanted = None if ai_flag == "none" else ai_flag
        summaries = [summary for summary in summaries if summary["ai_flag"] == wanted]

    def sort_value(summary: dict):
        if sort == "patient":
            return (summary["patient_display"] or summary["pseudonym"]).lower()
        value = summary.get(sort)
        return "" if value is None else value

    summaries.sort(key=sort_value, reverse=order == "desc")

    identities_shown = sum(1 for summary in summaries if summary["identity_visible"])
    if identities_shown:
        try:
            write_audit_now(
                actor_id=user.id,
                action="patient.list_viewed",
                resource_type="patient",
                resource_id=None,
                detail={"count": identities_shown},
            )
        except Exception as exc:  # noqa: BLE001 - identity reads fail closed
            raise AppError(503, "audit_unavailable", "Audit log is unavailable; worklist refused") from exc

    return summaries[offset : offset + limit]


def _image_summary(image: Image) -> ImageSummary:
    return ImageSummary(
        id=image.id,
        modality=image.modality,
        laterality=normalise_laterality(image.laterality),
        view=normalise_view(image.view),
        body_part=image.body_part,
        body_part_raw=image.body_part_raw,
        mime=image.mime,
        rows=image.rows,
        cols=image.cols,
        created_at=image.created_at,
        validation=json.loads(image.validation_json or "{}"),
        deid_receipt=json.loads(image.deid_receipt_json or "{}"),
    )


def case_detail(session: Session, user: User, case_id: str) -> dict:
    case = assert_case_access(user, session.get(Case, case_id))
    summary = _summaries(session, user, [case])[0]
    images = session.execute(select(Image).where(Image.case_id == case_id).order_by(Image.created_at)).scalars().all()
    payload = {
        **summary,
        "images": [],
        "exam": None,
        "patient": None,
    }
    if user.role == "administrator":
        # Administrators get metadata only: no image bytes, no pixel-level detail.
        return payload

    if summary["identity_visible"] and case.patient_id:
        patient = session.get(Patient, case.patient_id)
        if patient is not None:
            identity = patient_service.decrypt_identity_or_422(patient, user.id)
            patient_service.record_identity_view(user.id, patient)
            payload["patient"] = PatientSummary(
                id=patient.id,
                name=identity.get("name") or "",
                hospital_number=identity.get("hospital_number") or "",
                sex=identity.get("sex") or "unknown",
                dob=identity.get("dob"),
                age=patient_service.age_from_dob(identity.get("dob")),
                case_count=len(
                    session.execute(select(Case.id).where(Case.patient_id == patient.id)).all()
                ),
                created_at=patient.created_at,
                updated_at=patient.updated_at,
            ).model_dump()

    summaries = [_image_summary(image) for image in images]
    payload["images"] = [summary.model_dump() for summary in summaries]

    mammograms = [summary for summary in summaries if summary.modality == "mammogram"]
    xrays = [summary for summary in summaries if summary.modality == "xray"]
    if mammograms:
        grouped = group_mammogram_views([summary.model_dump() for summary in mammograms])
        payload["exam"] = {"type": "mammogram_four_view", **grouped}
    elif xrays:
        payload["exam"] = {
            "type": "xray",
            "regions": [
                {
                    "image_id": summary.id,
                    "body_part": summary.body_part_raw or summary.body_part,
                    "region": summary.body_part,
                    "capability": capability_for(
                        summary.body_part or "unrecognised", summary.modality
                    ),
                }
                for summary in xrays
            ],
        }
    return payload


def attach_patient(session: Session, user: User, case_id: str, patient_id: str) -> Case:
    case = assert_case_access(user, session.get(Case, case_id))
    patient_service.link_case(session, user, case, patient_id)
    return case


def delete_case(session: Session, user: User, case_id: str) -> None:
    case = assert_case_access(user, session.get(Case, case_id))
    if case.created_by != user.id and user.role != "administrator":
        raise AppError(403, "forbidden", "Only the case owner can delete a case")
    case.status = "archived"
    append_audit(
        session,
        actor_id=user.id,
        action="case.archived",
        resource_type="case",
        resource_id=case.id,
        detail={},
    )
