from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class Prediction:
    findings: list[dict[str, Any]]
    label: str
    probability: float
    extra: dict[str, Any] = field(default_factory=dict)


class BaseEngine:
    """Common contract shared by every model adapter."""

    model_id: str = ""
    version: str = ""
    digest: str = ""
    demo: bool = False
    preprocess_profile: str = "xrv_chest_224"
    cam_layer: str | None = None
    cam_method: str = "gradcam"
    degraded: bool = False

    def predict(self, model_input: np.ndarray) -> Prediction:  # pragma: no cover - interface
        raise NotImplementedError

    def gradcam(
        self,
        model_input: np.ndarray,
        target_index: int | None = None,
        target_label: str | None = None,
    ) -> np.ndarray:  # pragma: no cover - interface
        raise NotImplementedError

    def target_index(self, label: str) -> int:
        return 0

    def localisable(self, label: str) -> bool:
        """Whether a class names a region the model can point at."""
        return True


def normalise_cam(cam: np.ndarray) -> np.ndarray:
    array = np.asarray(cam, dtype=np.float32)
    low, high = float(array.min()), float(array.max())
    if high > low:
        array = (array - low) / (high - low)
    else:
        array = np.zeros_like(array)
    return array.astype(np.float32)


_LOCKS: dict[tuple[str, str], threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def engine_lock(model_id: str, version: str) -> threading.Lock:
    """Serialise CAM passes on one engine; torch modules are not re-entrant safe."""
    with _LOCKS_GUARD:
        return _LOCKS.setdefault((model_id, version), threading.Lock())
