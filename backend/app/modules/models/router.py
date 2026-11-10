from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.core.deps import get_current_user
from app.core.errors import AppError
from app.core.schema import ModelVersion, User

router = APIRouter(prefix="/models", tags=["models"])


def load_registry() -> list[dict]:
    path = get_settings().registry_path
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("models", [])


def seed_models(session: Session) -> None:
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
                setattr(existing, key, value)
    session.commit()


def _to_dict(model: ModelVersion) -> dict:
    registry = {(entry["model_id"], entry["version"]): entry for entry in load_registry()}
    entry = registry.get((model.model_id, model.version), {})
    return {
        "model_id": model.model_id,
        "version": model.version,
        "digest": model.digest,
        "state": model.state,
        "task": model.task,
        "modalities": json.loads(model.modalities_json or "[]"),
        "regions": entry.get("regions", []),
        "demo": entry.get("demo", False),
        "weights": entry.get("weights"),
        "card": json.loads(model.card_json or "{}"),
    }


@router.get("")
def list_models(session: Session = Depends(get_session), _user: User = Depends(get_current_user)) -> list[dict]:
    models = session.execute(select(ModelVersion).order_by(ModelVersion.model_id)).scalars().all()
    return [_to_dict(model) for model in models]


@router.get("/{model_id}")
def get_model(
    model_id: str,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict:
    models = session.execute(select(ModelVersion).where(ModelVersion.model_id == model_id)).scalars().all()
    if not models:
        raise AppError(404, "model_not_found", "Model not found")
    return {"model_id": model_id, "versions": [_to_dict(model) for model in models]}
