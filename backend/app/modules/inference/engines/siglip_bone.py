from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import get_settings
from app.core.errors import AppError
from app.modules.inference.engines.base import BaseEngine, Prediction, normalise_cam

PROMPTS = {
    "normal": "a normal bone radiograph with no fracture or abnormality",
    "abnormal": "a radiograph showing a fracture or bone abnormality",
}
LABELS = list(PROMPTS)
DEFAULT_DIR = "siglip2-base-patch16-224"
CAM_GRID = 14


PROMPT_NORMAL = 0
PROMPT_ABNORMAL = 1


class _ImageTextLogits:
    @staticmethod
    def build(torch: Any, vision_model: Any, text_embeds: Any, scale: Any, bias: Any) -> Any:
        from torch import nn
        from torch.nn import functional as functional

        class Scorer(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.vision_model = vision_model
                self.register_buffer("text_embeds", text_embeds)
                self.register_buffer("scale", scale)
                self.register_buffer("bias", bias)

            def forward(self, pixel_values: Any) -> Any:
                pooled = self.vision_model(pixel_values=pixel_values).pooler_output
                embeds = functional.normalize(pooled, dim=-1)
                return self.scale * (embeds @ self.text_embeds.t()) + self.bias

        return Scorer()


class _LogitDifference:
    """Expose one raw logit difference as a scalar for the CAM pass.

    Gradients of a softmax probability saturate as the two logits separate, so
    the map collapses to noise. The raw difference stays sensitive.
    """

    @staticmethod
    def build(torch: Any, scorer: Any, positive: int, negative: int) -> Any:
        from torch import nn

        class Difference(nn.Module):
            def __init__(self) -> None:
                super().__init__()
                self.scorer = scorer
                self.positive = positive
                self.negative = negative

            def forward(self, pixel_values: Any) -> Any:
                logits = self.scorer(pixel_values)
                return (logits[:, self.positive] - logits[:, self.negative]).unsqueeze(1)

        return Difference()


def _tokens_to_grid(tensor: Any) -> Any:
    batch, tokens, channels = tensor.shape
    side = int(round(tokens**0.5))
    return tensor.reshape(batch, side, side, channels).permute(0, 3, 1, 2)


class SiglipBoneEngine(BaseEngine):
    """Zero-shot normal/abnormal scoring for limb radiographs with SigLIP 2."""

    model_id = "siglip_bone"
    version = "0.1"
    demo = False
    preprocess_profile = "siglip_bone_224"
    cam_layer = "vision_model.encoder.layers[-2].layer_norm1"
    cam_method = "hirescam_logit_difference"

    def __init__(self, entry: dict[str, Any] | None = None) -> None:
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise AppError(
                409, "model_unavailable", "transformers is not installed on this host"
            ) from exc

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
        self.tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
        self.model = AutoModel.from_pretrained(path, local_files_only=True).eval()
        self.vision = self.model.vision_model
        self.labels = list(LABELS)
        self.digest = _file_digest(path / "model.safetensors")

        batch = self.tokenizer(
            [PROMPTS[label] for label in LABELS],
            padding="max_length",
            max_length=64,
            truncation=True,
            return_tensors="pt",
        )
        with torch.no_grad():
            pooled = self.model.text_model(**batch).pooler_output
            text_embeds = torch.nn.functional.normalize(pooled, dim=-1)
        self._scorer = _ImageTextLogits.build(
            torch,
            self.vision,
            text_embeds,
            self.model.logit_scale.exp().detach(),
            self.model.logit_bias.detach(),
        ).eval()
        self._cam = None
        self._cam_pair: tuple[int, int] | None = None
        self._cam_output = None

    def predict(self, model_input: np.ndarray) -> Prediction:
        torch = self._torch
        tensor = torch.from_numpy(np.asarray(model_input, dtype=np.float32))
        with torch.no_grad():
            logits = self._scorer(tensor).squeeze(0)
            probabilities = torch.softmax(logits, dim=0).cpu().numpy()

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
                "engine": "siglip_zero_shot",
                "top_index": top,
                "prompts": [PROMPTS[label] for label in LABELS],
            },
        )

    def gradcam(
        self,
        model_input: np.ndarray,
        target_index: int | None = None,
        target_label: str | None = None,
    ) -> np.ndarray:
        from pytorch_grad_cam import HiResCAM
        from pytorch_grad_cam.utils.model_targets import RawScoresOutputTarget

        from torch.nn import functional as F

        torch = self._torch
        index = self.target_index(target_label) if target_label else int(target_index or 0)
        negative = PROMPT_ABNORMAL if index == PROMPT_NORMAL else PROMPT_NORMAL
        if self._cam is None or self._cam_pair != (index, negative):
            self._cam_output = _LogitDifference.build(torch, self._scorer, index, negative).eval()
            self._cam = HiResCAM(
                model=self._cam_output,
                target_layers=[self.vision.encoder.layers[-2].layer_norm1],
                reshape_transform=_tokens_to_grid,
            )
            self._cam_pair = (index, negative)

        tensor = torch.from_numpy(np.asarray(model_input, dtype=np.float32)).clone().requires_grad_(True)
        grayscale = self._cam(input_tensor=tensor, targets=[RawScoresOutputTarget()])[0]
        values = np.maximum(np.asarray(grayscale, dtype=np.float32), 0.0)
        cam = torch.from_numpy(values)[None, None]
        # Work on the native 14 by 14 token grid, not the upsampled image.
        cam = F.adaptive_avg_pool2d(cam, (CAM_GRID, CAM_GRID))

        # Zero attention on air outside the patient. Without this a single
        # background patch can own the colour scale and look like a lesion.
        with torch.no_grad():
            grey = tensor.detach().mean(dim=1, keepdim=True)
            grid = F.adaptive_avg_pool2d(grey, (CAM_GRID, CAM_GRID))
            low, high = float(grid.min()), float(grid.max())
            if high - low > 0.1:
                background = (grid - low) / (high - low) < 0.04
                share = float(background.float().mean())
                if 0.02 <= share <= 0.8:
                    cam = cam.masked_fill(background, 0.0)

        ceiling = torch.quantile(cam.flatten(), 0.99)
        if float(ceiling) > 0:
            cam = torch.clamp(cam, max=float(ceiling))
        if float(cam.max()) <= 0:
            return np.zeros(tuple(tensor.shape[-2:]), dtype=np.float32)

        cam = F.interpolate(
            cam, size=tuple(tensor.shape[-2:]), mode="bilinear", align_corners=False
        )
        return normalise_cam(cam.squeeze().detach().cpu().numpy())

    def target_index(self, label: str) -> int:
        token = label.strip().lower()
        return LABELS.index(token) if token in LABELS else 0

    def localisable(self, label: str) -> bool:
        return label.strip().lower() != "normal"


def _weights_path(entry: dict[str, Any]) -> Path:
    relative = (entry.get("source") or {}).get("local_path") or DEFAULT_DIR
    return get_settings().model_dir / relative


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
