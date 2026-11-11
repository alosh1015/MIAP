from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.modules.models.approvals import effective_state
from app.modules.models.router import load_registry


def _find(model_id: str, version: str | None) -> dict:
    for entry in load_registry():
        if entry["model_id"] != model_id:
            continue
        if version and entry["version"] != version:
            continue
        return entry
    raise AppError(404, "model_not_found", "Model version is not registered", model_id)


def registry_entry(model_id: str, version: str | None = None) -> dict:
    return _find(model_id, version)


def select_model(
    model_id: str | None,
    model_version: str | None,
    session: Session | None = None,
) -> dict:
    settings = get_settings()
    if model_id is None:
        model_id = "stub_classifier" if settings.model_backend == "stub" else "chest_densenet121"
    entry = _find(model_id, model_version)
    state = entry.get("state")
    if session is not None:
        state = effective_state(session, entry["model_id"], entry["version"], state)
    if state != "approved":
        raise AppError(409, "model_not_approved", "Model is not approved for use", state or "unknown")
    return entry


def document_model(entry: dict) -> dict:
    return {
        "name": entry["model_id"],
        "version": entry["version"],
        "digest": entry.get("digest"),
        "demo": bool(entry.get("demo")),
        "card": entry.get("card", {}),
    }


def params_for(entry: dict, extra: dict | None = None) -> dict:
    payload = json.loads(json.dumps(extra or {}))
    payload.setdefault("model_id", entry["model_id"])
    payload.setdefault("model_version", entry["version"])
    return payload
