"""Role-specific dashboard payloads.

Identity is only ever included for a clinician's own cases; the worklist helper
audits the identity view. Researchers and administrators get counts only.
"""

from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import verify_chain
from app.core.ids import utcnow_iso
from app.core.schema import AnalysisBatch, AuditEvent, Case, Job, ModelVersion, Patient, User
from app.modules.cases import service as case_service
from app.modules.models.router import internal_model_ids
from app.modules.settings.service import get_system_settings

RECENT_LIMIT = 5


def _clinician(session: Session, user: User) -> dict:
    cases = case_service.list_cases(session, user, limit=1000)
    open_cases = [case for case in cases if case["status"] != "archived"]
    flagged = sum(1 for case in cases if case["ai_flag"] == "flagged")
    awaiting = sum(max(case["findings_to_review"] - case["reviewed"], 0) for case in cases)
    patients = session.execute(
        select(func.count(Patient.id)).where(Patient.owner_id == user.id)
    ).scalar() or 0
    return {
        "role": "clinician",
        "patients": {"mine": patients},
        "studies": {"total": len(cases), "open": len(open_cases)},
        "ai": {"flagged": flagged, "awaiting_review": awaiting},
        "recent_cases": open_cases[:RECENT_LIMIT],
        "notices": [get_system_settings(session).tb_notice],
    }


def _researcher(session: Session, user: User) -> dict:
    own = session.execute(
        select(func.count(Case.id)).where(Case.created_by == user.id)
    ).scalar() or 0
    research = session.execute(
        select(func.count(Case.id)).where(Case.consent == "research")
    ).scalar() or 0
    queued = session.execute(
        select(func.count(AnalysisBatch.id)).where(
            AnalysisBatch.requested_by == user.id, AnalysisBatch.state.in_(["queued", "running"])
        )
    ).scalar() or 0
    hidden_models = internal_model_ids()
    rows = session.execute(select(ModelVersion.model_id, ModelVersion.state)).all()
    states: dict[str, int] = {}
    for model_id, state in rows:
        if model_id not in hidden_models:
            states[state] = states.get(state, 0) + 1
    exports = (
        session.execute(
            select(AuditEvent)
            .where(AuditEvent.actor_id == user.id, AuditEvent.action == "export.created")
            .order_by(AuditEvent.seq.desc())
            .limit(RECENT_LIMIT)
        )
        .scalars()
        .all()
    )
    return {
        "role": "researcher",
        "datasets": {"own": own, "research_consent": research},
        "batches": {"active": queued},
        "models": {
            "approved": states.get("approved", 0),
            "candidate": states.get("candidate", 0),
        },
        "recent_exports": [
            {"at": event.ts, "detail": json.loads(event.detail_json or "{}")} for event in exports
        ],
        "compute_warning": "Batch analysis is CPU-bound and may take several minutes per study.",
    }


def _administrator(session: Session, user: User) -> dict:
    now = utcnow_iso()
    queued = session.execute(select(func.count(Job.id)).where(Job.state == "queued")).scalar() or 0
    running = session.execute(select(func.count(Job.id)).where(Job.state == "running")).scalar() or 0
    active_users = session.execute(
        select(func.count(User.id)).where(User.is_active == 1)
    ).scalar() or 0
    pending = session.execute(
        select(func.count(ModelVersion.model_id)).where(ModelVersion.state == "candidate")
    ).scalar() or 0
    retention_due = session.execute(
        select(func.count(Case.id)).where(
            Case.retention_until.is_not(None),
            Case.retention_until < now,
            Case.status != "archived",
        )
    ).scalar() or 0
    ok, checked, first_bad = verify_chain(session)
    return {
        "role": "administrator",
        "queue": {"queued": queued, "running": running},
        "users": {"active": active_users},
        "models": {"pending_approvals": pending},
        "retention": {"due": retention_due},
        "audit": {
            "ok": ok,
            "checked": checked,
            "first_bad_seq": first_bad,
            "verified_at": now,
        },
    }


def dashboard_for(session: Session, user: User) -> dict:
    if user.role == "administrator":
        return _administrator(session, user)
    if user.role == "researcher":
        return _researcher(session, user)
    return _clinician(session, user)
