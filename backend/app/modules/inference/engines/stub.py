from __future__ import annotations

from typing import Any

import numpy as np

from app.modules.inference.engines.base import BaseEngine, Prediction, normalise_cam


class StubEngine(BaseEngine):
    """Deterministic stand-in used by tests and demo mode. Never clinical."""

    model_id = "stub_classifier"
    version = "0.1"
    digest = "stub-not-a-model"
    demo = True
    preprocess_profile = "xrv_chest_224"
    cam_layer = "input-gradient"

    def __init__(self, entry: dict[str, Any] | None = None) -> None:
        entry = entry or {}
        self.version = str(entry.get("version") or self.version)
        self.preprocess_profile = str(entry.get("preprocess_profile") or self.preprocess_profile)
        self.cam_layer = (entry.get("cam") or {}).get("target_layer") or "input-gradient"

    def predict(self, model_input: np.ndarray) -> Prediction:
        array = np.asarray(model_input, dtype=np.float32).squeeze()
        mean = float(array.mean())
        std = float(array.std())
        probability = float(1.0 / (1.0 + np.exp(-(std / 180.0) + (mean / 900.0))))
        findings = [
            {"label": "normal", "probability": round(1.0 - probability, 4), "threshold": 0.5},
            {"label": "abnormal", "probability": round(probability, 4), "threshold": 0.5},
        ]
        label = "abnormal" if probability >= 0.5 else "normal"
        top = 1 if label == "abnormal" else 0
        return Prediction(
            findings=findings,
            label=label,
            probability=round(max(probability, 1.0 - probability), 4),
            extra={"engine": "stub", "top_index": top, "mean": mean, "std": std},
        )

    def gradcam(
        self,
        model_input: np.ndarray,
        target_index: int | None = None,
        target_label: str | None = None,
    ) -> np.ndarray:
        array = np.asarray(model_input, dtype=np.float32).squeeze()
        gy, gx = np.gradient(array)
        return normalise_cam(np.hypot(gy, gx))

    def target_index(self, label: str) -> int:
        return 1 if label.lower() in {"abnormal", "b", "fracture"} else 0
