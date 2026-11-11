"""Retention: remove due study data while keeping pseudonymous case metadata.

Only counts and byte totals reach the administrator; no pseudonym, name, image,
or finding is returned.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.audit import append_audit
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.ids import utcnow_iso
from app.core.schema import (
    Case,
    FindingReview,
    Image,
    Job,
    Provenance,
    Report,
    Result,
    ResultHeatmap,
    User,
)
from app.core.storage import blob_path

DATA_SUFFIXES = (".dcm", ".png", ".jpg", ".jpeg", ".pdf")


def _due_cases(session: Session) -> list[Case]:
    now = utcnow_iso()
    return (
        session.execute(
            select(Case).where(
                Case.retention_until.is_not(None),
                Case.retention_until < now,
                Case.status != "archived",
            )
        )
        .scalars()
        .all()
    )


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                continue
    return total


def _safe_unlink(path: Path, settings) -> int:
    try:
        resolved = path.resolve()
        if settings.data_dir.resolve() not in resolved.parents:
            return 0
    except OSError:
        return 0
    if not resolved.exists():
        return 0
    size = resolved.stat().st_size
    resolved.unlink(missing_ok=True)
    return size


def preview(session: Session, admin: User) -> dict:
    cases = _due_cases(session)
    case_ids = [case.id for case in cases]
    settings = get_settings()
    blob_digests: set[str] = set()
    derived_bytes = 0
    if case_ids:
        images = session.execute(select(Image).where(Image.case_id.in_(case_ids))).scalars().all()
        blob_digests = {image.blob_digest for image in images}
        derived_bytes = sum(_dir_size(settings.derived_dir / case_id) for case_id in case_ids)
    blob_bytes = sum(
        blob_path(digest).stat().st_size
        for digest in blob_digests
        if blob_path(digest).exists()
    )
    reports = session.execute(select(Report).where(Report.case_id.in_(case_ids))).scalars().all() if case_ids else []
    report_bytes = sum(Path(report.path).stat().st_size for report in reports if Path(report.path).exists())
    append_audit(
        session,
        actor_id=admin.id,
        action="retention.previewed",
        resource_type="system",
        resource_id=None,
        detail={"due_cases": len(cases), "blobs": len(blob_digests)},
    )
    session.commit()
    return {
        "due_cases": len(cases),
        "blobs": len(blob_digests),
        "bytes_blobs": blob_bytes,
        "bytes_derived": derived_bytes,
        "bytes_reports": report_bytes,
        "bytes_total": blob_bytes + derived_bytes + report_bytes,
        "cutoff": utcnow_iso(),
    }


def run(session: Session, admin: User, *, confirm: bool) -> dict:
    if not confirm:
        raise AppError(422, "confirmation_required", "Retention run requires confirm=true")
    cases = _due_cases(session)
    if not cases:
        return {
            "archived": 0,
            "deleted_results": 0,
            "deleted_reports": 0,
            "deleted_images": 0,
            "freed_bytes": 0,
        }
    case_ids = [case.id for case in cases]
    settings = get_settings()

    results = session.execute(select(Result).where(Result.case_id.in_(case_ids))).scalars().all()
    result_ids = [result.id for result in results]
    if result_ids:
        session.execute(delete(ResultHeatmap).where(ResultHeatmap.result_id.in_(result_ids)))
        session.execute(delete(FindingReview).where(FindingReview.result_id.in_(result_ids)))
        session.execute(delete(Provenance).where(Provenance.result_id.in_(result_ids)))
        session.execute(delete(Result).where(Result.id.in_(result_ids)))

    reports = session.execute(select(Report).where(Report.case_id.in_(case_ids))).scalars().all()
    freed = 0
    for report in reports:
        freed += _safe_unlink(Path(report.path), settings)
    if reports:
        session.execute(delete(Report).where(Report.case_id.in_(case_ids)))

    images = session.execute(select(Image).where(Image.case_id.in_(case_ids))).scalars().all()
    digests = {image.blob_digest for image in images}
    session.execute(delete(Job).where(Job.case_id.in_(case_ids)))
    session.execute(delete(Image).where(Image.case_id.in_(case_ids)))
    for digest in digests:
        remaining = session.execute(
            select(func.count(Image.id)).where(Image.blob_digest == digest)
        ).scalar() or 0
        if remaining == 0:
            freed += _safe_unlink(blob_path(digest), settings)

    for case_id in case_ids:
        directory = settings.derived_dir / case_id
        freed += _dir_size(directory)
        shutil.rmtree(directory, ignore_errors=True)
        case = session.get(Case, case_id)
        if case is not None:
            case.status = "archived"

    append_audit(
        session,
        actor_id=admin.id,
        action="retention.run",
        resource_type="system",
        resource_id=None,
        detail={
            "archived_cases": len(case_ids),
            "deleted_results": len(results),
            "deleted_reports": len(reports),
            "deleted_images": len(images),
            "bytes_freed": freed,
        },
    )
    session.commit()
    return {
        "archived": len(case_ids),
        "deleted_results": len(results),
        "deleted_reports": len(reports),
        "deleted_images": len(images),
        "freed_bytes": freed,
    }
