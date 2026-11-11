from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.core.config import get_settings
from app.core.errors import AppError
from app.modules.inference.engines import get_engine
from app.modules.preprocessing.profiles import profile_for
from app.modules.preprocessing.service import to_model_input

WEIGHTS = get_settings().model_dir
MONAI_WEIGHTS = WEIGHTS / "monai_density_model.pt"
SIGLIP_WEIGHTS = WEIGHTS / "siglip2-base-patch16-224" / "model.safetensors"


def _image(rows: int = 320, cols: int = 256) -> np.ndarray:
    rng = np.random.default_rng(7)
    return (rng.random((rows, cols)) * 4000.0).astype(np.float32)


def test_profiles_produce_their_declared_shape():
    array = _image()
    for name, size, channels in [
        ("xrv_chest_224", (224, 224), 1),
        ("monai_density_299", (299, 299), 3),
        ("siglip_bone_224", (224, 224), 3),
    ]:
        tensor, stats = to_model_input(array, profile=name)
        assert tensor.shape == (1, channels, *size)
        assert tensor.dtype == np.float32
        assert stats["profile"] == name


def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError):
        profile_for("does_not_exist")


def test_stub_engine_is_deterministic():
    engine = get_engine("stub_classifier")
    tensor, _stats = to_model_input(_image(), profile=engine.preprocess_profile)
    first = engine.predict(tensor)
    second = engine.predict(tensor)
    assert first.label == second.label
    assert first.extra["top_index"] in {0, 1}
    cam = engine.gradcam(tensor)
    assert cam.shape == tensor.shape[-2:]
    assert float(cam.min()) >= 0.0 and float(cam.max()) <= 1.0


def test_mammoscreen_is_never_selectable():
    with pytest.raises(AppError) as caught:
        get_engine("mammoscreen")
    assert caught.value.status == 409
    assert caught.value.code == "model_not_approved"


def test_unknown_engine_is_rejected():
    with pytest.raises(AppError) as caught:
        get_engine("not_a_model")
    assert caught.value.status == 404


def test_unknown_version_is_rejected():
    with pytest.raises(AppError) as caught:
        get_engine("chest_densenet121", "v0")
    assert caught.value.status == 404


@pytest.mark.skipif(not MONAI_WEIGHTS.exists(), reason="MONAI density weights are not installed")
def test_monai_density_predicts_a_birads_category_and_cam():
    engine = get_engine("monai_density")
    tensor, _stats = to_model_input(_image(640, 480), profile=engine.preprocess_profile)
    prediction = engine.predict(tensor)
    assert {finding["label"] for finding in prediction.findings} == {"A", "B", "C", "D"}
    assert 0.0 <= prediction.probability <= 1.0
    assert prediction.extra["density"] == prediction.label
    cam = engine.gradcam(tensor, target_index=prediction.extra["top_index"])
    assert cam.shape == (299, 299)
    assert float(cam.max()) <= 1.0


@pytest.mark.skipif(not SIGLIP_WEIGHTS.exists(), reason="SigLIP bone weights are not installed")
def test_siglip_bone_predicts_normal_vs_abnormal_and_cam():
    engine = get_engine("siglip_bone")
    tensor, _stats = to_model_input(_image(512, 512), profile=engine.preprocess_profile)
    prediction = engine.predict(tensor)
    assert {finding["label"] for finding in prediction.findings} == {"normal", "abnormal"}
    assert len(prediction.findings) == 2
    cam = engine.gradcam(tensor, target_label=prediction.label)
    assert cam.shape == (224, 224)
    assert float(cam.max()) <= 1.0
