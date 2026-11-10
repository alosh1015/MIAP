"""M0 gate: measure chest X-ray inference on this machine.

Runs the real preprocessing, model and Grad-CAM path used by the API and
checks the four acceptance criteria in the plan:

    mean < 6 s/image, p95 < 8 s, peak RSS < 4.5 GB,
    Grad-CAM computed at 7x7 and upsampled to 224x224,
    occluding the hottest CAM cell lowers the target probability by >= 10%.

Writes ml/benchmark/m0_report.json and exits non-zero if a check fails.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import numpy as np  # noqa: E402
import psutil  # noqa: E402

from app.modules.inference.engine import get_engine  # noqa: E402
from app.modules.preprocessing.service import load_pixels, to_model_input  # noqa: E402

DEFAULT_FIXTURE = REPO_ROOT / "backend" / "tests" / "fixtures" / "generated" / "chest_pa.dcm"
OUT_PATH = REPO_ROOT / "ml" / "benchmark" / "m0_report.json"

MEAN_LIMIT_S = 6.0
P95_LIMIT_S = 8.0
RSS_LIMIT_MB = 4500.0
MIN_OCCLUSION_DROP = 0.10


def _variants(count: int, seed: int = 0) -> list[np.ndarray]:
    """Deterministic chest-like inputs: the fixture plus jitter and noise."""
    rng = np.random.default_rng(seed)
    array, meta = load_pixels("application/dicom", DEFAULT_FIXTURE.read_bytes())
    inputs: list[np.ndarray] = []
    for index in range(count):
        shifted = np.roll(array, shift=(index % 5 - 2) * 3, axis=0)
        shifted = np.roll(shifted, shift=(index % 3 - 1) * 3, axis=1)
        noisy = shifted + rng.normal(0.0, 8.0 + index, shifted.shape)
        tensor, _ = to_model_input(noisy.astype(np.float32), photometric=meta["photometric"])
        inputs.append(tensor)
    return inputs


def _percentile(values: list[float], fraction: float) -> float:
    return float(np.percentile(np.asarray(values), fraction * 100.0))


def _cam_grid_shape(engine, model_input: np.ndarray) -> tuple[int, ...]:
    """Shape of the activation map Grad-CAM pools over."""
    captured: dict[str, tuple[int, ...]] = {}

    def hook(_module, _inputs, output):
        captured["shape"] = tuple(int(dim) for dim in output.shape)

    handle = engine.model.features.norm5.register_forward_hook(hook)
    try:
        engine.gradcam(model_input, 0)
    finally:
        handle.remove()
    return captured.get("shape", ())


def _occlusion_test(engine, model_input: np.ndarray, cam: np.ndarray) -> dict:
    """Occlude the hottest CAM block and re-score the same label.

    The 2x2 cell block (8% of the image) is filled with the input mean, the
    conventional occlusion baseline. Filling with the input minimum would
    write a value already present in the dark border and mask nothing.
    """
    prediction = engine.predict(model_input)
    top_index = int(prediction.extra["top_index"])
    label = engine.labels[top_index]
    before = float(prediction.findings[0]["probability"])

    grid = 7
    cell = cam.shape[0] // grid
    weights = cam[: cell * grid, : cell * grid].reshape(grid, cell, grid, cell).mean(axis=(1, 3))
    row, col = np.unravel_index(int(np.argmax(weights)), weights.shape)

    block = 2
    row = min(int(row), grid - block)
    col = min(int(col), grid - block)
    occluded = np.array(model_input, copy=True)
    occluded[
        0,
        0,
        row * cell : (row + block) * cell,
        col * cell : (col + block) * cell,
    ] = float(model_input.mean())

    torch = engine._torch
    with torch.no_grad():
        after = float(engine.model(torch.from_numpy(occluded)).squeeze(0)[top_index])

    drop = 0.0 if before <= 0 else (before - after) / before
    return {
        "label": label,
        "cell": [row, col],
        "block_cells": block,
        "area_fraction": round((block * cell / cam.shape[0]) ** 2, 3),
        "before": round(before, 4),
        "after": round(after, 4),
        "relative_drop": round(drop, 4),
        "passed": drop >= MIN_OCCLUSION_DROP,
    }


def run(images: int, warmup: int) -> dict:
    import torch
    import torchvision
    import torchxrayvision

    process = psutil.Process()
    engine = get_engine("chest_densenet121")
    inputs = _variants(images)

    for model_input in inputs[:warmup]:
        engine.predict(model_input)
        engine.gradcam(model_input, 0)

    predict_ms: list[float] = []
    gradcam_ms: list[float] = []
    for model_input in inputs:
        start = time.perf_counter()
        engine.predict(model_input)
        predict_ms.append((time.perf_counter() - start) * 1000.0)

        start = time.perf_counter()
        cam = engine.gradcam(model_input, 0)
        gradcam_ms.append((time.perf_counter() - start) * 1000.0)

    total_s = [(p + g) / 1000.0 for p, g in zip(predict_ms, gradcam_ms)]
    mean_s = float(np.mean(total_s))
    p95_s = _percentile(total_s, 0.95)

    memory = process.memory_info()
    peak_mb = float(getattr(memory, "peak_wset", memory.rss)) / (1024 * 1024)

    grid_shape = _cam_grid_shape(engine, inputs[0])
    top_index = int(engine.predict(inputs[0]).extra["top_index"])
    cam = engine.gradcam(inputs[0], top_index)
    cam_ok = grid_shape[-2:] == (7, 7) and cam.shape == (224, 224)

    occlusion = _occlusion_test(engine, inputs[0], cam)

    checks = {
        "mean_under_6s": {"value": round(mean_s, 3), "limit": MEAN_LIMIT_S, "passed": mean_s < MEAN_LIMIT_S},
        "p95_under_8s": {"value": round(p95_s, 3), "limit": P95_LIMIT_S, "passed": p95_s < P95_LIMIT_S},
        "peak_rss_under_4_5gb": {"value": round(peak_mb, 1), "limit": RSS_LIMIT_MB, "passed": peak_mb < RSS_LIMIT_MB},
        "gradcam_7x7_to_224": {"value": {"grid": list(grid_shape), "cam": list(cam.shape)}, "passed": cam_ok},
        "occlusion_drop_10pct": occlusion,
    }

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "host": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "cpu_count": psutil.cpu_count(logical=True),
            "torch_threads": torch.get_num_threads(),
        },
        "versions": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "torchvision": torchvision.__version__,
            "torchxrayvision": torchxrayvision.__version__,
        },
        "model": {
            "model_id": engine.model_id,
            "version": engine.version,
            "weights": "densenet121-res224-all",
            "digest": getattr(engine, "digest", ""),
            "labels": len(engine.labels),
        },
        "images": len(inputs),
        "timing": {
            "predict_ms": [round(value, 1) for value in predict_ms],
            "gradcam_ms": [round(value, 1) for value in gradcam_ms],
            "total_ms_mean": round(mean_s * 1000.0, 1),
            "total_ms_p95": round(p95_s * 1000.0, 1),
        },
        "peak_rss_mb": round(peak_mb, 1),
        "checks": checks,
        "passed": all(check.get("passed", False) for check in checks.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=int, default=12)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    if args.images <= args.warmup:
        parser.error("--images must be greater than --warmup")

    report = run(args.images, args.warmup)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"model      {report['model']['model_id']} {report['model']['version']}")
    print(f"images     {report['images']} (warmup {args.warmup})")
    print(f"mean       {report['timing']['total_ms_mean'] / 1000:.2f} s")
    print(f"p95        {report['timing']['total_ms_p95'] / 1000:.2f} s")
    print(f"peak RSS   {report['peak_rss_mb']:.0f} MB")
    for name, check in report["checks"].items():
        status = "PASS" if check.get("passed") else "FAIL"
        print(f"{status:10} {name}: {check.get('value', '')}")
    print(f"report     {args.out}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
