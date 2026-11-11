"""Verify installed model weights, cards and benchmark evidence.

Reads ``ml/registry.json`` and checks, without importing torch:

* every declared weight file exists and matches its SHA-256;
* every model has ``ml/cards/<model_id>.json``;
* every entry that points at a benchmark has a readable benchmark JSON whose
  ``model.digest`` matches the registry digest;
* ``ml/weights/manifest.json`` (written by ``fetch_models.py``) covers the
  installed models.

    python scripts/verify_models.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "ml" / "registry.json"
WEIGHTS_DIR = REPO_ROOT / "ml" / "weights"
CARDS_DIR = REPO_ROOT / "ml" / "cards"
MANIFEST_PATH = WEIGHTS_DIR / "manifest.json"
CHUNK = 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _weight_checks(entry: dict[str, Any]) -> list[tuple[str, bool, str]]:
    source = entry.get("source") or {}
    local_path = source.get("local_path")
    if not local_path:
        managed = str(entry.get("weights") or "").split(":", 1)[0]
        return [("weights", True, f"managed by {managed or 'vendor'}")]
    target = WEIGHTS_DIR / local_path
    files = source.get("files") or []
    if not files:
        expected = source.get("sha256") or entry.get("digest")
        if not expected or expected in {"pending", "unavailable"}:
            return [("weights", True, "no digest declared")]
        files = [{"path": "", "sha256": expected}]
    checks: list[tuple[str, bool, str]] = []
    for item in files:
        relative = item.get("path") or ""
        path = target / relative if relative else target
        name = relative or local_path
        if not path.is_file():
            checks.append((name, False, "missing"))
            continue
        actual = _sha256(path)
        ok = actual == item["sha256"]
        checks.append((name, ok, "ok" if ok else f"sha256 {actual[:12]}… != {item['sha256'][:12]}…"))
    return checks


def _benchmark_check(path: str, digest: str) -> tuple[str, bool, str]:
    file = REPO_ROOT / path
    if not file.is_file():
        return ("benchmark", False, f"{path} missing")
    try:
        body = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return ("benchmark", False, f"{path} unreadable: {exc}")
    recorded = ((body.get("model") or {}).get("digest")) or ""
    if not recorded:
        return ("benchmark", False, f"{path} has no model.digest")
    if recorded != digest:
        return ("benchmark", False, f"{path} digest {recorded[:12]}… != {digest[:12]}…")
    passed = body.get("passed")
    return ("benchmark", bool(passed), f"{path} {'passed' if passed else 'failed its gates'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-weights", action="store_true", help="skip hashing installed weights")
    args = parser.parse_args(argv)

    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["models"]
    manifest_models = set()
    if MANIFEST_PATH.is_file():
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        manifest_models = {record["model_id"] for record in manifest.get("models", [])}

    failures = 0
    width = max(len(entry["model_id"]) for entry in registry)
    for entry in registry:
        model_id = entry["model_id"]
        digest = str(entry.get("digest") or "")
        checks: list[tuple[str, bool, str]] = []
        if not args.skip_weights:
            checks.extend(_weight_checks(entry))
        card = CARDS_DIR / f"{model_id}.json"
        checks.append(("card", card.is_file(), "ok" if card.is_file() else "missing"))
        approval = entry.get("approval") or {}
        benchmark_path = approval.get("benchmark_path")
        if benchmark_path:
            checks.append(_benchmark_check(benchmark_path, digest))
        if (entry.get("source") or {}).get("local_path"):
            checks.append(
                (
                    "manifest",
                    model_id in manifest_models,
                    "ok" if model_id in manifest_models else "run scripts/fetch_models.py",
                )
            )
        bad = [check for check in checks if not check[1]]
        failures += len(bad)
        print(f"{model_id:<{width}}  {'OK' if not bad else 'FAIL'}")
        for name, ok, detail in checks:
            if not ok or name in {"weights", "benchmark"}:
                print(f"  {'ok  ' if ok else 'fail'} {name}: {detail}")

    if failures:
        print(f"{failures} check(s) failed", file=sys.stderr)
        return 1
    print("all model checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
