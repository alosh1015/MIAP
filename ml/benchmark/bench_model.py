"""Benchmark one registered model on this CPU host.

Measures latency, peak RSS and Grad-CAM sanity through the same engine,
preprocessing profile and registry digest checks used by the API, then writes a
JSON file suitable for an administrator's approval decision.

    python ml/benchmark/bench_model.py --model monai_density
    python ml/benchmark/bench_model.py --model siglip_bone --runs 3
    python ml/benchmark/bench_model.py --model mammoscreen --allow-unavailable

The latency gate for ``monai_density`` is 6 s/image mean, per the plan. Models
without a declared gate still require a finite CAM that matches the input size.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

import numpy as np  # noqa: E402
import psutil  # noqa: E402

from app.core.errors import AppError  # noqa: E402
from app.modules.inference.engine import get_engine  # noqa: E402
from app.modules.inference.engines import engine_lock  # noqa: E402
from app.modules.preprocessing.service import load_pixels, to_model_input  # noqa: E402

FIXTURES = REPO_ROOT / "backend" / "tests" / "fixtures" / "generated"
DEFAULT_FIXTURES = {
    "monai_density": FIXTURES / "mammo_four_view" / "LCC.dcm",
    "siglip_bone": FIXTURES / "hand_pa.dcm",
    "chest_densenet121": FIXTURES / "chest_pa.dcm",
    "stub_classifier": FIXTURES / "chest_pa.dcm",
}
GATES = {
    "monai_density": {"max_mean_seconds": 6.0, "max_result_seconds": 6.0},
}
REGISTRY_PATH = REPO_ROOT / "ml" / "registry.json"


def _entry(model_id: str, version: str | None) -> dict[str, Any]:
    models = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["models"]
    for entry in models:
        if entry["model_id"] == model_id and (version is None or entry["version"] == version):
            return entry
    raise SystemExit(f"No registry entry for {model_id} {version or ''}".strip())


class _RssSampler:
    def __init__(self, interval: float = 0.05) -> None:
        self.process = psutil.Process()
        self.interval = interval
        self.peak = self.process.memory_info().rss
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self.peak = max(self.peak, self.process.memory_info().rss)

    def __enter__(self) -> "_RssSampler":
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=1)

    @property
    def peak_mb(self) -> float:
        return round(self.peak / (1024 * 1024), 1)


def _percentile(values: list[float], fraction: float) -> float:
    return round(float(np.percentile(np.asarray(values), fraction * 100.0)), 3)


def _benchmark_digest(body: dict[str, Any]) -> str:
    stable = {
        "model": body["model"],
        "fixture": body["fixture"],
        "input": body["input"],
        "latency": body["latency"],
        "cam": body["cam"],
        "checks": body["checks"],
    }
    payload = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def run(model_id: str, version: str | None, fixture: Path, runs: int, warmup: int) -> dict[str, Any]:
    entry = _entry(model_id, version)
    profile = entry.get("preprocess_profile") or "xrv_chest_224"
    if not fixture.is_file():
        raise SystemExit(f"Fixture not found: {fixture}")

    started = time.perf_counter()
    engine = get_engine(model_id, entry["version"])
    load_seconds = round(time.perf_counter() - started, 3)

    data = fixture.read_bytes()
    array, meta = load_pixels("application/dicom", data)
    model_input, stats = to_model_input(array, photometric=meta.get("photometric", ""), profile=profile)
    expected_shape = (int(stats["size"]), int(stats["size"]))

    prediction = engine.predict(model_input)
    for _ in range(warmup):
        engine.predict(model_input)

    timings: list[float] = []
    with _RssSampler() as sampler:
        for _ in range(runs):
            started = time.perf_counter()
            engine.predict(model_input)
            timings.append(time.perf_counter() - started)

    cam_started = time.perf_counter()
    with engine_lock(model_id, engine.version):
        cam = engine.gradcam(model_input, target_index=0)
    cam_seconds = round(time.perf_counter() - cam_started, 3)
    cam = np.asarray(cam, dtype=np.float32)

    gate = GATES.get(model_id)
    mean_seconds = float(np.mean(timings))
    first_result = mean_seconds + cam_seconds
    digest_ok = str(entry.get("digest") or "").startswith("stub") or engine.digest == entry.get("digest")
    checks = {
        "digest_verified": digest_ok,
        "latency_gate": mean_seconds <= gate["max_mean_seconds"] if gate else True,
        "result_gate": first_result <= gate["max_result_seconds"] if gate else True,
        "cam_matches_input": tuple(cam.shape) == expected_shape,
        "cam_finite": bool(np.isfinite(cam).all()),
        "cam_range": bool(cam.size and float(cam.min()) >= 0.0 and float(cam.max()) <= 1.0),
        "cam_has_signal": bool(cam.size and float(cam.std()) > 0.01),
    }
    body: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": {
            "platform": platform.platform(),
            "processor": platform.processor() or platform.machine(),
            "python": platform.python_version(),
            "runs": runs,
            "warmup": warmup,
        },
        "model": {
            "id": model_id,
            "version": str(engine.version),
            "digest": engine.digest,
            "preprocess_profile": profile,
        },
        "fixture": {
            "path": str(fixture.relative_to(REPO_ROOT)).replace("\\", "/"),
            "sha256": hashlib.sha256(data).hexdigest(),
            "rows": int(meta.get("rows") or array.shape[0]),
            "cols": int(meta.get("cols") or array.shape[1]),
        },
        "input": {
            "shape": list(model_input.shape),
            "min": round(float(stats["min"]), 4),
            "max": round(float(stats["max"]), 4),
            "mean": round(float(stats["mean"]), 4),
            "std": round(float(stats["std"]), 4),
        },
        "prediction": {
            "label": prediction.label,
            "probability": prediction.probability,
            "findings": prediction.findings[:5],
        },
        "load_seconds": load_seconds,
        "latency": {
            "mean": round(mean_seconds, 3),
            "p50": _percentile(timings, 0.50),
            "p95": _percentile(timings, 0.95),
            "min": round(min(timings), 3),
            "max": round(max(timings), 3),
            "first_result": round(first_result, 3),
        },
        "cam": {
            "seconds": cam_seconds,
            "shape": list(cam.shape),
            "min": round(float(cam.min()), 4),
            "max": round(float(cam.max()), 4),
            "mean": round(float(cam.mean()), 4),
            "std": round(float(cam.std()), 4),
            "checksum": hashlib.sha256(cam.tobytes()).hexdigest(),
        },
        "memory": {"peak_rss_mb": sampler.peak_mb},
        "checks": checks,
        "gates": gate or {},
    }
    body["passed"] = all(checks.values())
    body["benchmark_digest"] = _benchmark_digest(body)
    return body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="monai_density")
    parser.add_argument("--version", default=None)
    parser.add_argument("--fixture", type=Path, default=None)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--allow-unavailable", action="store_true", help="write a refusal record instead of failing")
    args = parser.parse_args(argv)

    out = args.out or REPO_ROOT / "ml" / "benchmark" / f"{args.model}_benchmark.json"
    fixture = args.fixture or DEFAULT_FIXTURES.get(args.model)
    if fixture is None:
        raise SystemExit(f"No default fixture for {args.model}; pass --fixture")

    try:
        body = run(args.model, args.version, fixture, args.runs, args.warmup)
    except AppError as exc:
        if not args.allow_unavailable:
            raise
        entry = _entry(args.model, args.version)
        body = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": {
                "id": args.model,
                "version": str(entry.get("version")),
                "digest": entry.get("digest"),
                "preprocess_profile": entry.get("preprocess_profile"),
            },
            "fixture": None,
            "status": "refused",
            "selectable": False,
            "reason": f"{exc.code}: {exc.detail or exc.title}",
            "passed": False,
            "benchmark_digest": None,
        }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(REPO_ROOT)}")
    if body.get("status") == "refused":
        print(f"refused: {body['reason']}")
        return 0
    print(
        f"mean {body['latency']['mean']} s, first result {body['latency']['first_result']} s, "
        f"p95 {body['latency']['p95']} s, rss {body['memory']['peak_rss_mb']} MB, "
        f"digest {body['benchmark_digest'][:12]}…"
    )
    print(f"checks: {json.dumps(body['checks'])}")
    return 0 if body["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
