from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.deps import require_roles
from app.core.errors import AppError
from app.core.schema import Report, User
from app.modules.reporting import service

router = APIRouter(tags=["reports"])


def _payload(report: Report, case_id: str | None = None) -> dict:
    return {
        "report_id": report.id,
        "case_id": case_id if case_id is not None else report.case_id,
        "audience": report.audience,
        "kind": report.kind,
        "title": report.title,
        "sha256": report.sha256,
        "template_version": report.template_version,
        "created_at": report.created_at,
        "url": f"/api/v1/reports/{report.id}.pdf",
    }


@router.post("/reports/{case_id}", status_code=201)
def create_report(
    case_id: str,
    job_id: str | None = None,
    audience: str | None = Query(default=None),
    include_identity: bool = Query(default=False),
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician", "researcher")),
) -> dict:
    report = service.render_report(
        session,
        user,
        case_id,
        job_id,
        audience=audience,
        include_identity=include_identity,
    )
    return _payload(report)


@router.post("/governance/reports", status_code=201)
def create_governance_report(
    days: int = Query(default=30, ge=1, le=365),
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("administrator")),
) -> dict:
    report = service.render_governance_report(session, user, days=days)
    return _payload(report)


@router.get("/reports/{report_id}.pdf")
def download_report(
    report_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician", "researcher", "administrator")),
) -> FileResponse:
    record = service.get_report(session, user, report_id, download=True)
    if not Path(record.path).exists():
        raise AppError(404, "report_file_missing", "The report file is no longer on disk")
    return FileResponse(record.path, media_type="application/pdf", filename=f"{report_id}.pdf")
