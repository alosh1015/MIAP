from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import get_settings
from app.core.errors import AppError
from app.modules.inference.engines.base import BaseEngine, Prediction, normalise_cam

LABELS = ["A", "B", "C", "D"]
DEFAULT_WEIGHTS = "monai_density_model.pt"


class _DensityNet:
    """NetAdapter layout from the MONAI bundle: ``features`` backbone plus ``fc``."""

    @staticmethod
    def build(torch: Any) -> Any:
        from torch import nn
        from torchvision.models.inception import inception_v3

        class Net(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.features = inception_v3(
                    weights=None, aux_logits=True, transform_input=False, init_weights=False
                )
                self.features.fc = nn.Identity()
                self.fc = nn.Linear(2048, len(LABELS))

            def forward(self, x: Any) -> Any:
                x = self.features(x)
                if isinstance(x, tuple):
                    x = x[0]
                return self.fc(torch.flatten(x, 1))

        return Net()


class MonaiDensityEngine(BaseEngine):
    model_id = "monai_density"
    version = "0.1"
    demo = False
    preprocess_profile = "monai_density_299"
    cam_layer = "features.Mixed_7c"

    def __init__(self, entry: dict[str, Any] | None = None) -> None:
        import torch

        entry = entry or {}
        self.version = str(entry.get("version") or self.version)
        self.preprocess_profile = str(entry.get("preprocess_profile") or self.preprocess_profile)
        self.cam_layer = (entry.get("cam") or {}).get("target_layer") or self.cam_layer
        path = _weights_path(entry)
        if not path.exists():
            raise AppError(
                409,
                "model_unavailable",
                "Model weights are not installed on this host",
                f"{self.model_id}: {path.name}",
            )

        torch.set_num_threads(min(4, torch.get_num_threads()))
        self._torch = torch
        self.model = _DensityNet.build(torch)
        state = torch.load(path, map_location="cpu", weights_only=True)
        self.model.load_state_dict(state)
        self.model.eval()
        self.digest = _file_digest(path)
        self.labels = list(LABELS)
        self._cam = None

    def predict(self, model_input: np.ndarray) -> Prediction:
        torch = self._torch
        tensor = torch.from_numpy(np.asarray(model_input, dtype=np.float32))
        with torch.no_grad():
            logits = self.model(tensor).squeeze(0)
            probabilities = torch.sigmoid(logits).cpu().numpy()

        order = np.argsort(probabilities)[::-1]
        findings = [
            {
                "label": LABELS[index],
                "probability": round(float(probabilities[index]), 4),
                "threshold": 0.5,
            }
            for index in order
        ]
        top = int(order[0])
        return Prediction(
            findings=findings,
            label=LABELS[top],
            probability=round(float(probabilities[top]), 4),
            extra={
                "engine": "monai_density",
                "top_index": top,
                "density": LABELS[top],
                "scores": {label: round(float(value), 4) for label, value in zip(LABELS, probabilities)},
            },
        )

    def gradcam(
        self,
        model_input: np.ndarray,
        target_index: int | None = None,
        target_label: str | None = None,
    ) -> np.ndarray:
        from pytorch_grad_cam import GradCAM
        from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget

        torch = self._torch
        if self._cam is None:
            target = self.model.features.Mixed_7c
            self._cam = GradCAM(model=self.model, target_layers=[target])

        tensor = torch.from_numpy(np.asarray(model_input, dtype=np.float32)).clone().requires_grad_(True)
        index = self.target_index(target_label) if target_label else int(target_index or 0)
        grayscale = self._cam(input_tensor=tensor, targets=[ClassifierOutputTarget(index)])[0]
        return normalise_cam(grayscale)

    def target_index(self, label: str) -> int:
        token = label.strip().upper().replace("DENSITY", "").strip()
        return LABELS.index(token) if token in LABELS else 0


def _weights_path(entry: dict[str, Any]) -> Path:
    relative = (entry.get("source") or {}).get("local_path") or DEFAULT_WEIGHTS
    return get_settings().model_dir / relative


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
