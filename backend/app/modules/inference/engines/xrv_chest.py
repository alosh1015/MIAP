from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

from app.modules.inference.engines.base import BaseEngine, Prediction


class XrvChestEngine(BaseEngine):
    model_id = "chest_densenet121"
    version = "xrv-0.1"
    demo = False
    preprocess_profile = "xrv_chest_224"
    cam_layer = "features.norm5"

    def __init__(self, entry: dict[str, Any] | None = None) -> None:
        import torch
        import torchxrayvision as xrv

        entry = entry or {}
        self.version = str(entry.get("version") or self.version)
        self.preprocess_profile = str(entry.get("preprocess_profile") or self.preprocess_profile)
        self.cam_layer = (entry.get("cam") or {}).get("target_layer") or self.cam_layer
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
            self._cam = GradCAM(model=self.model, target_layers=[self.model.features.norm5])

        tensor = torch.from_numpy(np.asarray(model_input, dtype=np.float32)).clone().requires_grad_(True)
        index = 0 if target_index is None else int(target_index)
        grayscale = self._cam(input_tensor=tensor, targets=[ClassifierOutputTarget(index)])[0]
        return np.asarray(grayscale, dtype=np.float32)

    def target_index(self, label: str) -> int:
        try:
            return self.labels.index(label)
        except ValueError:
            return 0


def _weights_digest(model: Any) -> str:
    digest = hashlib.sha256()
    state = model.state_dict()
    for key in sorted(state):
        digest.update(key.encode("utf-8"))
        digest.update(state[key].detach().cpu().numpy().tobytes())
    return digest.hexdigest()
