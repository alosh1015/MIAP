from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.core.deps import get_current_user
from app.core.errors import AppError
from app.core.schema import ModelApproval, ModelVersion, User

router = APIRouter(prefix="/models", tags=["models"])

INTERNAL_PRESENTATION = "internal"


def is_presented(entry: dict) -> bool:
    """Internal routing/fallback classifiers are registered but not offered as models."""
    return entry.get("presentation") != INTERNAL_PRESENTATION


def internal_model_ids() -> set[str]:
    return {entry["model_id"] for entry in load_registry() if not is_presented(entry)}


def load_registry() -> list[dict]:
    path = get_settings().registry_path
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries: list[dict] = []
    cards_dir = path.parent / "cards"
    for entry in payload.get("models", []):
        item = dict(entry)
        if "card" not in item:
            card_path = cards_dir / f"{item['model_id']}.json"
            if card_path.exists():
                item["card"] = json.loads(card_path.read_text(encoding="utf-8"))
        entries.append(item)
    return entries


def seed_models(session: Session) -> None:
    """Insert missing registry rows; never overwrite a governance decision.

    State for an existing row belongs to model_approvals. Re-seeding must not
    silently re-approve or re-candidate a model an administrator already decided.
    """
    for entry in load_registry():
        existing = session.get(ModelVersion, (entry["model_id"], entry["version"]))
        values = {
            "digest": entry.get("digest", "pending"),
            "state": entry.get("state", "candidate"),
            "task": entry.get("task", "classification"),
            "modalities_json": json.dumps(entry.get("modalities", [])),
            "card_json": json.dumps(entry.get("card", {})),
        }
        if existing is None:
            session.add(ModelVersion(model_id=entry["model_id"], version=entry["version"], **values))
        else:
            for key, value in values.items():
                if key == "state":
                    continue
                setattr(existing, key, value)
    session.commit()


def _to_dict(model: ModelVersion, entry: dict, history: list[dict]) -> dict:
    return {
        "model_id": model.model_id,
        "version": model.version,
        "digest": model.digest,
        "state": model.state,
        "state_source": model.state_source,
        "approved_at": model.approved_at,
        "approved_by": model.approved_by,
        "task": model.task,
        "modalities": json.loads(model.modalities_json or "[]"),
        "regions": entry.get("regions", []),
        "capabilities": entry.get("capabilities", []),
        "degraded_capabilities": entry.get("degraded_capabilities", []),
        "demo": entry.get("demo", False),
        "validated_locally": bool(entry.get("validated_locally", False)),
        "weights": entry.get("weights"),
        "preprocess_profile": entry.get("preprocess_profile"),
        "input": entry.get("input", {}),
        "cam": entry.get("cam", {}),
        "licence": entry.get("licence", {}),
        "source": entry.get("source", {}),
        "metrics": entry.get("metrics", []),
        "approval": entry.get("approval", {}),
        "approvals": history,
        "card": json.loads(model.card_json or "{}"),
    }


def _approval_history(session: Session) -> dict[tuple[str, str], list[dict]]:
    rows = (
        session.execute(
            select(ModelApproval).order_by(ModelApproval.decided_at.desc())
        )
        .scalars()
        .all()
    )
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        grouped.setdefault((row.model_id, row.version), []).append(
            {
                "id": row.id,
                "decision": row.decision,
                "decided_by": row.decided_by,
                "decided_at": row.decided_at,
                "note": row.note,
                "benchmark_digest": row.benchmark_digest,
            }
        )
    return grouped


@router.get("")
def list_models(session: Session = Depends(get_session), _user: User = Depends(get_current_user)) -> list[dict]:
    registry = {(entry["model_id"], entry["version"]): entry for entry in load_registry()}
    history = _approval_history(session)
    models = session.execute(select(ModelVersion).order_by(ModelVersion.model_id)).scalars().all()
    return [
        _to_dict(
            model,
            registry.get((model.model_id, model.version), {}),
            history.get((model.model_id, model.version), []),
        )
        for model in models
        if is_presented(registry.get((model.model_id, model.version), {}))
    ]


@router.get("/{model_id}")
def get_model(
    model_id: str,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict:
    registry = {(entry["model_id"], entry["version"]): entry for entry in load_registry()}
    history = _approval_history(session)
    models = session.execute(select(ModelVersion).where(ModelVersion.model_id == model_id)).scalars().all()
    models = [
        model
        for model in models
        if is_presented(registry.get((model.model_id, model.version), {}))
    ]
    if not models:
        raise AppError(404, "model_not_found", "Model not found")
    return {
        "model_id": model_id,
        "versions": [
            _to_dict(
                model,
                registry.get((model.model_id, model.version), {}),
                history.get((model.model_id, model.version), []),
            )
            for model in models
        ],
    }
