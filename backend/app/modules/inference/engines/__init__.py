"""Engine factory keyed by ``(model_id, version)``."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app.core.errors import AppError
from app.modules.inference.engines.base import BaseEngine, Prediction, engine_lock, normalise_cam
from app.modules.inference.engines.mammoscreen import MammoScreenEngine
from app.modules.inference.engines.monai_density import MonaiDensityEngine
from app.modules.inference.engines.siglip_bone import SiglipBoneEngine
from app.modules.inference.engines.stub import StubEngine
from app.modules.inference.engines.xrv_chest import XrvChestEngine

ENGINES: dict[str, type[BaseEngine]] = {
    "stub_classifier": StubEngine,
    "chest_densenet121": XrvChestEngine,
    "monai_density": MonaiDensityEngine,
    "siglip_bone": SiglipBoneEngine,
    "mammoscreen": MammoScreenEngine,
}

__all__ = [
    "BaseEngine",
    "Prediction",
    "engine_lock",
    "get_engine",
    "normalise_cam",
]


@lru_cache(maxsize=4)
def get_engine(model_id: str, version: str | None = None) -> BaseEngine:
    entry = _entry_for(model_id, version)
    engine_class = ENGINES.get(model_id)
    if engine_class is None:
        raise AppError(404, "model_not_found", "No engine is installed for this model", model_id)
    engine = engine_class(entry)
    if version:
        engine.version = version
    _verify_digest(entry, engine)
    return engine


def _entry_for(model_id: str, version: str | None) -> dict[str, Any]:
    from app.modules.models.router import load_registry

    matches = [entry for entry in load_registry() if entry["model_id"] == model_id]
    if not matches:
        raise AppError(404, "model_not_found", "Model is not registered", model_id)
    if version is None:
        return matches[0]
    for entry in matches:
        if entry["version"] == version:
            return entry
    raise AppError(
        404,
        "model_version_unavailable",
        "The model version that produced this result is not available",
        f"{model_id}:{version}",
    )


def _verify_digest(entry: dict[str, Any], engine: BaseEngine) -> None:
    declared = entry.get("digest")
    if not declared or declared in {"pending", "unavailable"} or declared.startswith("stub"):
        return
    if engine.digest != declared:
        raise AppError(
            409,
            "model_digest_mismatch",
            "Model weights do not match the registered digest",
            f"{engine.model_id}: expected {declared[:12]}…, found {engine.digest[:12]}…",
        )
