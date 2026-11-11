"""Model governance: approvals are recorded, then projected onto model_versions."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import append_audit
from app.core.db import get_session
from app.core.deps import require_roles
from app.core.errors import AppError
from app.core.ids import new_id, utcnow_iso
from app.core.schema import ModelApproval, ModelVersion, User

router = APIRouter(prefix="/models", tags=["models"])

DECISIONS = {"approve": "approved", "reject": "rejected", "revoke": "revoked"}
AUDIT_ACTIONS = {
    "approved": "model.approved",
    "rejected": "model.rejected",
    "revoked": "model.revoked",
}


class ApprovalRequest(BaseModel):
    note: str = Field(default="", max_length=2000)
    benchmark_digest: str | None = Field(default=None, max_length=128)


def _model_or_404(session: Session, model_id: str, version: str) -> ModelVersion:
    model = session.get(ModelVersion, (model_id, version))
    if model is None:
        raise AppError(404, "model_not_found", "Model version is not registered")
    return model


def effective_state(session: Session, model_id: str, version: str, fallback: str | None) -> str | None:
    """A recorded decision outranks the registry declaration."""
    model = session.get(ModelVersion, (model_id, version))
    if model is not None and model.state_source == "approval":
        return model.state
    return fallback


def decide(
    session: Session,
    user: User,
    model_id: str,
    version: str,
    decision: str,
    payload: ApprovalRequest,
) -> dict:
    if decision not in DECISIONS:
        raise AppError(422, "invalid_decision", "Unknown approval decision")
    model = _model_or_404(session, model_id, version)
    state = DECISIONS[decision]
    now = utcnow_iso()

    approval = ModelApproval(
        id=new_id("approval"),
        model_id=model_id,
        version=version,
        decision=state,
        decided_by=user.id,
        decided_at=now,
        note=payload.note,
        benchmark_digest=payload.benchmark_digest,
    )
    session.add(approval)

    model.state = state
    model.state_source = "approval"
    model.approved_by = user.id
    model.approved_at = now

    append_audit(
        session,
        actor_id=user.id,
        action=AUDIT_ACTIONS[state],
        resource_type="model",
        resource_id=f"{model_id}:{version}",
        detail={"benchmark_digest": payload.benchmark_digest},
    )
    return {
        "model_id": model_id,
        "version": version,
        "state": state,
        "decided_at": now,
        "benchmark_digest": payload.benchmark_digest,
    }


def list_approvals(session: Session) -> list[dict]:
    rows = (
        session.execute(select(ModelApproval).order_by(ModelApproval.decided_at.desc()))
        .scalars()
        .all()
    )
    return [
        {
            "id": row.id,
            "model_id": row.model_id,
            "version": row.version,
            "decision": row.decision,
            "decided_by": row.decided_by,
            "decided_at": row.decided_at,
            "note": row.note,
            "benchmark_digest": row.benchmark_digest,
        }
        for row in rows
    ]


@router.get("/approvals")
def get_approvals(
    session: Session = Depends(get_session),
    _user: User = Depends(require_roles("administrator")),
) -> list[dict]:
    return list_approvals(session)


@router.post("/{model_id}/{version}/approve")
def approve_model(
    model_id: str,
    version: str,
    payload: ApprovalRequest,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("administrator")),
) -> dict:
    result = decide(session, user, model_id, version, "approve", payload)
    session.commit()
    return result


@router.post("/{model_id}/{version}/reject")
def reject_model(
    model_id: str,
    version: str,
    payload: ApprovalRequest,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("administrator")),
) -> dict:
    result = decide(session, user, model_id, version, "reject", payload)
    session.commit()
    return result


@router.post("/{model_id}/{version}/revoke")
def revoke_model(
    model_id: str,
    version: str,
    payload: ApprovalRequest,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("administrator")),
) -> dict:
    result = decide(session, user, model_id, version, "revoke", payload)
    session.commit()
    return result
