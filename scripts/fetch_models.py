"""Download and verify the weights declared in ``ml/registry.json``.

Every model records its source and SHA-256 in the registry. This script fetches
missing weights into ``ml/weights/`` (gitignored), verifies every file, and
writes ``ml/weights/manifest.json`` so an offline host can be checked with
``--offline``. ``torchxrayvision`` and vendor models are reported but not
downloaded here.

    python scripts/fetch_models.py --check
    python scripts/fetch_models.py --only monai_density
    python scripts/fetch_models.py --offline
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "ml" / "registry.json"
WEIGHTS_DIR = REPO_ROOT / "ml" / "weights"
MANIFEST_PATH = WEIGHTS_DIR / "manifest.json"
CHUNK = 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "miap-fetch-models/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as handle:
        while True:
            chunk = response.read(CHUNK)
            if not chunk:
                break
            handle.write(chunk)
    os.replace(partial, target)


def _expected_files(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Files to verify for this entry, with their expected hashes."""
    source = entry.get("source") or {}
    files = source.get("files") or []
    if files:
        return files
    local_path = source.get("local_path")
    if not local_path:
        return []
    expected = source.get("sha256") or entry.get("digest")
    if not expected or expected in {"pending", "unavailable"}:
        return []
    return [{"path": "", "sha256": expected}]


def _managed_by(entry: dict[str, Any]) -> str | None:
    source = entry.get("source") or {}
    if source.get("local_path"):
        return None
    weights = str(entry.get("weights") or "")
    if weights.startswith("torchxrayvision:"):
        return "torchxrayvision"
    if weights.startswith("therapixel:"):
        return "vendor"
    if weights.startswith("internal:"):
        return "internal"
    return None


def _file_url(entry: dict[str, Any], relative: str) -> str | None:
    source = entry.get("source") or {}
    base = source.get("weights_url")
    if not base:
        return None
    if not relative:
        return base
    if "huggingface.co" in base:
        return f"{base.rstrip('/')}/resolve/main/{relative}"
    return f"{base.rstrip('/')}/{relative}"


def fetch_entry(
    entry: dict[str, Any], *, offline: bool, force: bool
) -> dict[str, Any]:
    model_id = entry["model_id"]
    version = str(entry.get("version"))
    source = entry.get("source") or {}
    local_path = source.get("local_path")
    record: dict[str, Any] = {
        "model_id": model_id,
        "version": version,
        "local_path": local_path,
        "files": [],
        "status": "ok",
    }
    managed = _managed_by(entry)
    if not local_path:
        record["status"] = "managed"
        record["managed_by"] = managed
        record["note"] = (
            "weights are resolved by the library or vendor, not by this script"
            if managed
            else "no downloadable source is declared"
        )
        return record

    target = WEIGHTS_DIR / local_path
    expected = _expected_files(entry)
    if not expected:
        record["status"] = "unverifiable"
        record["note"] = "no SHA-256 is declared"
        return record

    for item in expected:
        relative = item.get("path") or ""
        path = target / relative if relative else target
        url = _file_url(entry, relative)
        if force or not path.exists():
            if offline:
                record["status"] = "missing"
                record["files"].append(
                    {"path": relative or local_path, "status": "missing"}
                )
                continue
            if not url:
                record["status"] = "missing"
                record["files"].append(
                    {"path": relative or local_path, "status": "no_url"}
                )
                continue
            print(f"  downloading {model_id} {relative or local_path}")
            _download(url, path)
        actual = _sha256(path) if path.is_file() else None
        ok = actual == item["sha256"]
        if not ok:
            record["status"] = "digest_mismatch"
        record["files"].append(
            {
                "path": relative or local_path,
                "bytes": path.stat().st_size if path.is_file() else 0,
                "sha256": actual,
                "expected_sha256": item["sha256"],
                "status": "ok" if ok else "digest_mismatch",
            }
        )
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="restrict to one model_id")
    parser.add_argument("--offline", action="store_true", help="never download; verify only")
    parser.add_argument("--force", action="store_true", help="re-download installed files")
    parser.add_argument("--check", action="store_true", help="alias for --offline")
    args = parser.parse_args(argv)
    offline = args.offline or args.check

    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))["models"]
    if args.only:
        registry = [entry for entry in registry if entry["model_id"] == args.only]
        if not registry:
            print(f"No registry entry for {args.only}", file=sys.stderr)
            return 2

    records = []
    for entry in registry:
        print(f"{entry['model_id']} {entry.get('version')}")
        records.append(fetch_entry(entry, offline=offline, force=args.force))

    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    previous: dict[str, dict[str, Any]] = {}
    if MANIFEST_PATH.is_file():
        try:
            old = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            previous = {record["model_id"]: record for record in old.get("models", [])}
        except (OSError, ValueError):
            previous = {}
    previous.update({record["model_id"]: record for record in records})
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": platform.node(),
        "registry": str(REGISTRY_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "models": [previous[key] for key in sorted(previous)],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    width = max(len(record["model_id"]) for record in records)
    for record in records:
        print(f"  {record['model_id']:<{width}}  {record['status']}")
    failures = [record for record in records if record["status"] not in {"ok", "managed"}]
    print(f"manifest: {MANIFEST_PATH.relative_to(REPO_ROOT)}")
    if failures:
        print(f"{len(failures)} model(s) failed verification", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
