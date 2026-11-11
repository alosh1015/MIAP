"""Role-specific report rendering.

Stored results are immutable; this service presents them and renders one of
three audiences. A clinician report can include the linked identity and review
notes because it is only rendered for the case owner. A researcher report is
pseudonymised and withholds notes. A governance report is generated for an
administrator and contains no patients, pixels, or findings.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import append_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.schema import (
    AuditEvent,
    Case,
    Image,
    ImageAnnotation,
    Job,
    ModelApproval,
    Patient,
    Provenance,
    Report,
    Result,
    User,
)
from app.modules.cases.service import can_access_case
from app.modules.models.router import load_registry
from app.modules.patients.service import decrypt_identity_or_422, record_identity_view
from app.modules.reporting.templates import clinician, governance, researcher
from app.modules.reporting.templates.common import TEMPLATE_VERSION, brand_page
from app.modules.results.heatmaps import (
    cam_is_current,
    heatmaps_for_result,
    mapping_for_document,
)
from app.modules.results.presenter import present_document
from app.modules.reviews.service import review_map

AUDIENCES = {"clinician", "researcher"}
GOVERNANCE_MAX_DAYS = 365
APPROVAL_LIMIT = 50


def _now() -> str:
    return _label(datetime.now(timezone.utc))


def _stamp() -> str:
    """UTC timestamp for the stored row; reports show the human label."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _label(moment: datetime) -> str:
    local = moment.astimezone()
    zone = local.tzname() or "local"
    return f"{local:%Y-%m-%d %H:%M} {zone} · {moment:%H:%M} UTC"


def _model_card(document: dict) -> dict:
    name = document.get("model", {}).get("name")
    version = document.get("model", {}).get("version")
    for entry in load_registry():
        if entry.get("model_id") == name and entry.get("version") == version:
            return entry.get("card", {})
    return {}


def _latest_result(session: Session, case_id: str, job_id: str | None) -> tuple[Result, Job]:
    if job_id:
        job = session.get(Job, job_id)
        if job is None or job.case_id != case_id:
            raise AppError(404, "job_not_found", "Analysis job not found for this case")
        result = session.execute(select(Result).where(Result.job_id == job.id)).scalar_one_or_none()
        if result is None or job.state != "completed":
            raise AppError(409, "job_not_complete", "The analysis has not completed")
        return result, job

    row = session.execute(
        select(Result).where(Result.case_id == case_id).order_by(Result.created_at.desc())
    ).scalars().first()
    if row is None:
        raise AppError(409, "no_results", "This case has no completed analysis to report")
    job = session.get(Job, row.job_id)
    return row, job


def _annotations(session: Session, image_id: str) -> list[list[tuple[float, float]]]:
    """Reviewer-drawn polygons, normalised to the image frame, oldest first."""
    rows = session.execute(
        select(ImageAnnotation)
        .where(ImageAnnotation.image_id == image_id)
        .order_by(ImageAnnotation.created_at)
    ).scalars()
    polygons = []
    for row in rows:
        try:
            stored = json.loads(row.points_json)
            points = [
                (float(x), float(y))
                for x, y in stored
                if 0.0 <= float(x) <= 1.0 and 0.0 <= float(y) <= 1.0
            ]
        except (ValueError, TypeError):
            continue
        if len(points) >= 3:
            polygons.append(points)
    return polygons


def _resolve_audience(user: User, requested: str | None) -> str:
    if user.role == "administrator":
        raise AppError(403, "forbidden", "Administrators cannot create clinical case reports")
    if user.role not in {"clinician", "researcher"}:
        raise AppError(403, "forbidden", "This role cannot create reports")
    if requested is None:
        return "clinician" if user.role == "clinician" else "researcher"
    if requested not in AUDIENCES:
        raise AppError(422, "invalid_audience", "Audience must be clinician or researcher")
    if user.role == "researcher" and requested != "researcher":
        raise AppError(403, "forbidden", "Researchers can only create pseudonymised reports")
    return requested


def _reviewer_names(session: Session, reviews: dict[int, dict]) -> None:
    ids = {review.get("reviewer_id") for review in reviews.values() if review.get("reviewer_id")}
    if not ids:
        return
    names = dict(
        session.execute(select(User.id, User.display_name).where(User.id.in_(ids))).all()
    )
    for review in reviews.values():
        review["reviewer_name"] = names.get(review.get("reviewer_id"), "unknown reviewer")


def _identity_for(session: Session, user: User, case: Case) -> dict | None:
    if user.role != "clinician" or case.created_by != user.id or not case.patient_id:
        return None
    patient = session.get(Patient, case.patient_id)
    if patient is None or patient.owner_id != user.id:
        return None
    identity = decrypt_identity_or_422(patient, user.id)
    payload = {
        "name": identity.get("name"),
        "hospital_number": identity.get("hospital_number"),
        "sex": identity.get("sex"),
        "dob": identity.get("dob"),
    }
    record_identity_view(user.id, patient)
    return payload


def _provenance(session: Session, result: Result) -> dict:
    record = session.execute(
        select(Provenance).where(Provenance.result_id == result.id)
    ).scalar_one_or_none()
    if record is None:
        return {}
    try:
        return json.loads(record.record_json)
    except ValueError:
        return {}


def _agreement(document: dict, reviews: dict[int, dict]) -> dict:
    flagged = [
        finding
        for finding in document.get("findings", [])
        if finding.get("band") in {"above_threshold", "borderline"}
    ]
    decisions = [
        reviews[int(finding.get("index", 0))]["decision"]
        for finding in flagged
        if int(finding.get("index", 0)) in reviews
    ]
    return {
        "confirmed": sum(1 for decision in decisions if decision == "confirmed"),
        "dismissed": sum(1 for decision in decisions if decision == "dismissed"),
        "not_reviewed": len(flagged) - len(decisions),
    }


def _build_pdf(
    path: Path,
    title: str,
    subject: str,
    story: list,
    *,
    report_id: str,
    audience: str,
    generated: str,
) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=31 * mm,
        bottomMargin=20 * mm,
        title=title,
        author="MIAP",
        subject=subject,
    )

    def decorate(canvas, document):
        brand_page(
            canvas,
            document,
            report_id=report_id,
            audience=audience,
            generated=generated,
        )

    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)


def render_report(
    session: Session,
    user: User,
    case_id: str,
    job_id: str | None = None,
    *,
    audience: str | None = None,
    include_identity: bool = False,
) -> Report:
    case = session.get(Case, case_id)
    if case is None or user.role == "administrator" or not can_access_case(user, case):
        raise AppError(404, "case_not_found", "Case not found")
    resolved = _resolve_audience(user, audience)
    if include_identity and (resolved != "clinician" or user.role != "clinician"):
        raise AppError(403, "forbidden", "Only the treating clinician can include patient identity")

    result, job = _latest_result(session, case_id, job_id)
    stored = json.loads(result.document_json)
    reviews = review_map(session, user, result, include_notes=resolved == "clinician")
    _reviewer_names(session, reviews)
    document = present_document(
        stored,
        heatmaps=heatmaps_for_result(session, result.id),
        reviews=reviews if resolved == "clinician" else None,
    )
    if not cam_is_current(session, result, stored):
        document["heatmap"] = None
    document["heatmap_mapping"] = mapping_for_document(stored)
    image = session.get(Image, result.image_id)
    requester = session.get(User, job.requested_by)
    generated = _now()

    ctx = {
        "case": case,
        "result": result,
        "job": job,
        "image": image,
        "annotations": _annotations(session, result.image_id) if image else [],
        "document": document,
        "identity": (
            _identity_for(session, user, case) if resolved == "clinician" and include_identity else None
        ),
        "identity_requested": bool(include_identity),
        "reviews": reviews if resolved == "clinician" else None,
        "summary": document.get("review_summary") or {},
        "agreement": _agreement(document, reviews),
        "provenance": _provenance(session, result),
        "card": _model_card(stored),
        "requester": {
            "name": requester.display_name if requester else "n/a",
            "role": requester.role if requester else "n/a",
        },
        "generated_at": generated,
        "audience": resolved,
    }

    report_id = new_id("report")
    directory = get_settings().report_dir
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report_id}.pdf"

    renderer = clinician if resolved == "clinician" else researcher
    story = renderer.render(ctx, report_id)
    title = f"MIAP {'clinical' if resolved == 'clinician' else 'research'} report {case.pseudonym}"
    _build_pdf(
        path,
        title,
        "Decision-support report",
        story,
        report_id=report_id,
        audience="Clinical report" if resolved == "clinician" else "Research report",
        generated=generated,
    )

    record = Report(
        id=report_id,
        case_id=case.id,
        path=str(path),
        created_by=user.id,
        audience=resolved,
        kind="case",
        result_id=result.id,
        sha256=_digest(path),
        template_version=TEMPLATE_VERSION,
        title=title,
        created_at=_stamp(),
    )
    session.add(record)
    append_audit(
        session,
        actor_id=user.id,
        action="report.created",
        resource_type="report",
        resource_id=report_id,
        detail={
            "case_id": case.id,
            "job_id": job.id,
            "result_id": result.id,
            "audience": resolved,
            "identity_included": bool(ctx["identity"]),
            "sha256": record.sha256,
        },
    )
    session.commit()
    return record


def render_governance_report(session: Session, user: User, *, days: int = 30) -> Report:
    if user.role != "administrator":
        raise AppError(403, "forbidden", "Only administrators can create governance reports")
    window = max(1, min(int(days), GOVERNANCE_MAX_DAYS))
    generated_at = datetime.now(timezone.utc)
    start = (generated_at - timedelta(days=window)).strftime("%Y-%m-%dT%H:%M:%SZ")
    period = {
        "days": window,
        "from": start,
        "to": generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    from app.modules.system.service import health

    users = session.execute(select(User)).scalars().all()
    accounts: dict[str, dict[str, int]] = {}
    for account in users:
        entry = accounts.setdefault(account.role, {"active": 0, "total": 0})
        entry["total"] += 1
        if account.is_active:
            entry["active"] += 1

    approvals = (
        session.execute(
            select(ModelApproval)
            .where(ModelApproval.decided_at >= start)
            .order_by(ModelApproval.decided_at.desc())
            .limit(APPROVAL_LIMIT)
        )
        .scalars()
        .all()
    )
    retention_events = (
        session.execute(
            select(AuditEvent)
            .where(AuditEvent.action == "retention.run", AuditEvent.ts >= start)
            .order_by(AuditEvent.seq.desc())
            .limit(APPROVAL_LIMIT)
        )
        .scalars()
        .all()
    )
    retention_runs = []
    for event in retention_events:
        try:
            detail = json.loads(event.detail_json)
        except ValueError:
            detail = {}
        retention_runs.append({"ts": event.ts, "detail": detail})

    report_id = new_id("report")
    directory = get_settings().report_dir
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report_id}.pdf"
    title = f"MIAP governance report {period['from'][:10]} to {period['to'][:10]}"

    ctx = {
        "generated_at": _now(),
        "period": period,
        "health": health(session),
        "accounts": accounts,
        "approvals": [
            {
                "model_id": row.model_id,
                "version": row.version,
                "decision": row.decision,
                "decided_at": row.decided_at,
                "benchmark_digest": row.benchmark_digest,
            }
            for row in approvals
        ],
        "retention_runs": retention_runs,
    }
    story = governance.render(ctx, report_id)
    _build_pdf(
        path,
        title,
        "Governance summary",
        story,
        report_id=report_id,
        audience="Governance summary",
        generated=ctx["generated_at"],
    )

    record = Report(
        id=report_id,
        case_id=None,
        path=str(path),
        created_by=user.id,
        audience="governance",
        kind="governance",
        result_id=None,
        sha256=_digest(path),
        template_version=TEMPLATE_VERSION,
        title=title,
        created_at=_stamp(),
    )
    session.add(record)
    append_audit(
        session,
        actor_id=user.id,
        action="report.created",
        resource_type="report",
        resource_id=report_id,
        detail={
            "kind": "governance",
            "audience": "governance",
            "period_days": window,
            "sha256": record.sha256,
        },
    )
    session.commit()
    return record


def get_report(session: Session, user: User, report_id: str, *, download: bool = False) -> Report:
    record = session.get(Report, report_id)
    if record is None:
        raise AppError(404, "report_not_found", "Report not found")

    if record.kind == "governance":
        if user.role != "administrator":
            raise AppError(404, "report_not_found", "Report not found")
    else:
        if user.role == "administrator":
            raise AppError(403, "forbidden", "Administrators cannot download clinical case reports")
        case = session.get(Case, record.case_id) if record.case_id else None
        if case is None or not can_access_case(user, case):
            raise AppError(404, "report_not_found", "Report not found")
        if user.role == "researcher" and record.audience == "clinician":
            raise AppError(404, "report_not_found", "Report not found")

    if download:
        append_audit(
            session,
            actor_id=user.id,
            action="report.downloaded",
            resource_type="report",
            resource_id=record.id,
            detail={
                "audience": record.audience,
                "kind": record.kind,
                "case_id": record.case_id,
            },
        )
        session.commit()
    return record


def _digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
