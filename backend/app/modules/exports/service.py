"""Pseudonymised dataset export for researchers.

Identity, review notes, and image bytes never enter an export. Each export is
audited with its row count and a digest of the filters rather than their values.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import append_audit
from app.core.schema import Case, Image, Job, Result, User
from app.modules.exports.schemas import ExportRequest, filter_digest, rows_to_csv
from app.modules.results.presenter import band_for
from app.modules.settings.service import get_system_settings


def _latest_result(session: Session, case_id: str) -> Result | None:
    job = session.execute(
        select(Job).where(Job.case_id == case_id).order_by(Job.created_at.desc()).limit(1)
    ).scalar_one_or_none()
    if job is None:
        return None
    return session.execute(select(Result).where(Result.job_id == job.id)).scalar_one_or_none()


def _finding_rows(result: Result | None) -> list[dict]:
    if result is None:
        return []
    document = json.loads(result.document_json or "{}")
    rows = []
    for finding in document.get("findings") or []:
        probability = float(finding.get("probability", 0.0))
        threshold = finding.get("threshold")
        rows.append(
            {
                "label": finding.get("label"),
                "score": round(probability, 4),
                "threshold": threshold if threshold is not None else 0.5,
                "band": band_for(probability, threshold),
            }
        )
    return rows


def build_rows(session: Session, user: User, payload: ExportRequest) -> list[dict]:
    statement = select(Case).where((Case.created_by == user.id) | (Case.consent == "research"))
    if payload.consent:
        statement = statement.where(Case.consent == payload.consent)
    if payload.modality:
        statement = statement.where(Case.modality == payload.modality)
    statement = statement.order_by(Case.created_at.desc())
    cases = session.execute(statement).scalars().all()
    cap = get_system_settings(session).export_row_cap
    limit = min(payload.limit or cap, cap)
    rows = []
    for case in cases[:limit]:
        images = session.execute(select(Image.id).where(Image.case_id == case.id)).all()
        result = _latest_result(session, case.id)
        rows.append(
            {
                "case_id": case.id,
                "pseudonym": case.pseudonym,
                "consent": case.consent,
                "status": case.status,
                "modality": case.modality,
                "created_at": case.created_at,
                "retention_until": case.retention_until,
                "image_count": len(images),
                "result_id": result.id if result else None,
                "model": (
                    f"{json.loads(result.document_json).get('model', {}).get('name')}:"
                    f"{json.loads(result.document_json).get('model', {}).get('version')}"
                    if result
                    else None
                ),
                "findings": _finding_rows(result),
            }
        )
    append_audit(
        session,
        actor_id=user.id,
        action="export.created",
        resource_type="system",
        resource_id=None,
        detail={
            "format": payload.format,
            "rows": len(rows),
            "filter_digest": filter_digest(payload.model_dump(exclude_none=True)),
        },
    )
    session.commit()
    return rows


def render(rows: list[dict], fmt: str) -> tuple[str, str]:
    if fmt == "json":
        return json.dumps(rows, indent=2, sort_keys=True), "application/json"
    return rows_to_csv(rows), "text/csv"
