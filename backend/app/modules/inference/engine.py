from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np


@dataclass
class Prediction:
    findings: list[dict[str, Any]]
    label: str
    probability: float
    extra: dict[str, Any] = field(default_factory=dict)


class StubEngine:
    """Deterministic stand-in used by tests and demo mode. Never clinical."""

    model_id = "stub_classifier"
    version = "0.1"
    digest = "stub-not-a-model"
    demo = True

    def predict(self, model_input: np.ndarray) -> Prediction:
        array = np.asarray(model_input, dtype=np.float32).squeeze()
        mean = float(array.mean())
        std = float(array.std())
        probability = float(1.0 / (1.0 + np.exp(-(std / 180.0) + (mean / 900.0))))
        findings = [
            {"label": "normal", "probability": round(1.0 - probability, 4)},
            {"label": "abnormal", "probability": round(probability, 4)},
        ]
        label = "abnormal" if probability >= 0.5 else "normal"
        return Prediction(
            findings=findings,
            label=label,
            probability=round(max(probability, 1.0 - probability), 4),
            extra={"engine": "stub", "mean": mean, "std": std},
        )

    def gradcam(
        self,
        model_input: np.ndarray,
        target_index: int | None = None,
        target_label: str | None = None,
    ) -> np.ndarray:
        array = np.asarray(model_input, dtype=np.float32).squeeze()
        gy, gx = np.gradient(array)
        magnitude = np.hypot(gy, gx)
        if magnitude.max() > 0:
            magnitude = magnitude / magnitude.max()
        return magnitude.astype(np.float32)


class TorchXRayVisionEngine:
    model_id = "chest_densenet121"
    version = "xrv-0.1"
    demo = False

    def __init__(self) -> None:
        import torch
        import torchxrayvision as xrv

        self._torch = torch
        torch.set_num_threads(min(4, torch.get_num_threads()))
        self.model = xrv.models.DenseNet(weights="densenet121-res224-all")
        self.model.eval()
        self.labels: list[str] = list(self.model.pathologies)
        self.digest = _weights_digest(self.model)
        self._cam = None

    def predict(self, model_input: np.ndarray) -> Prediction:
        torch = self._torch
        tensor = torch.from_numpy(np.asarray(model_input, dtype=np.float32))
        with torch.no_grad():
            output = self.model(tensor).squeeze(0)

        probabilities = output.detach().cpu().numpy()
        order = np.argsort(probabilities)[::-1]
        findings = [
            {
                "label": self.labels[index],
                "probability": round(float(probabilities[index]), 4),
                "threshold": 0.5,
            }
            for index in order[:8]
        ]
        top = int(order[0])
        return Prediction(
            findings=findings,
            label=self.labels[top],
            probability=round(float(probabilities[top]), 4),
            extra={"engine": "torchxrayvision", "top_index": top},
        )

    def gradcam(self, model_input: np.ndarray, target_index: int | None = None) -> np.ndarray:
        from pytorch_grad_cam import GradCAM
        from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget

        torch = self._torch
        if self._cam is None:
            self._cam = GradCAM(model=self.model, target_layers=[self.model.features.norm5])

        tensor = torch.from_numpy(np.asarray(model_input, dtype=np.float32)).clone().requires_grad_(True)
        index = 0 if target_index is None else int(target_index)
        grayscale = self._cam(input_tensor=tensor, targets=[ClassifierOutputTarget(index)])[0]
        return np.asarray(grayscale, dtype=np.float32)


def _weights_digest(model: Any) -> str:
    digest = hashlib.sha256()
    state = model.state_dict()
    for key in sorted(state):
        digest.update(key.encode("utf-8"))
        digest.update(state[key].detach().cpu().numpy().tobytes())
    return digest.hexdigest()


def _build_engine(model_id: str) -> StubEngine | TorchXRayVisionEngine:
    if model_id == "stub_classifier":
        return StubEngine()
    if model_id == "chest_densenet121":
        return TorchXRayVisionEngine()
    raise ValueError(f"Unknown model: {model_id}")


@lru_cache(maxsize=2)
def get_engine(model_id: str) -> StubEngine | TorchXRayVisionEngine:
    return _build_engine(model_id)
