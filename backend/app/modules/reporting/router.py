from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.deps import require_roles
from app.core.errors import AppError
from app.core.schema import User
from app.modules.reporting import service

router = APIRouter(tags=["reports"])


@router.post("/reports/{case_id}", status_code=201)
def create_report(
    case_id: str,
    job_id: str | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician", "researcher")),
) -> dict:
    report = service.render_report(session, user, case_id, job_id)
    return {
        "report_id": report.id,
        "case_id": report.case_id,
        "created_at": report.created_at,
        "url": f"/api/v1/reports/{report.id}.pdf",
    }


@router.get("/reports/{report_id}.pdf")
def download_report(
    report_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician", "researcher")),
) -> FileResponse:
    record = service.get_report(session, user, report_id)
    from pathlib import Path

    if not Path(record.path).exists():
        raise AppError(404, "report_file_missing", "The report file is no longer on disk")
    return FileResponse(record.path, media_type="application/pdf", filename=f"{report_id}.pdf")
