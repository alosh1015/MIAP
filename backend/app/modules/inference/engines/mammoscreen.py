from __future__ import annotations

from typing import Any

from app.core.errors import AppError
from app.modules.inference.engines.base import BaseEngine


class MammoScreenEngine(BaseEngine):
    """Vendor model placeholder.

    The weights are commercial, require remote code, and have no local CPU
    benchmark. The engine refuses to load, and the registry keeps the model in
    the candidate state so it cannot be selected for an analysis.
    """

    model_id = "mammoscreen"
    version = "vendor"
    digest = "unavailable"
    preprocess_profile = "mammoscreen_vendor"
    cam_layer = None

    def __init__(self, entry: dict[str, Any] | None = None) -> None:
        raise AppError(
            409,
            "model_not_approved",
            "MammoScreen is a candidate model",
            "Commercial weights, remote code and no local benchmark; not selectable.",
        )
