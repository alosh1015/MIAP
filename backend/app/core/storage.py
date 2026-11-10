from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def blob_path(digest: str) -> Path:
    return settings.blob_dir / digest[:2] / digest[2:4] / digest


def write_blob(data: bytes) -> str:
    digest = sha256_bytes(data)
    target = blob_path(digest)
    if target.exists():
        return digest
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=str(target.parent), prefix=".tmp-")
    try:
        with os.fdopen(handle, "wb") as sink:
            sink.write(data)
        os.replace(temp_name, target)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return digest


def read_blob(digest: str) -> bytes:
    return blob_path(digest).read_bytes()


def relative(path: Path) -> str:
    return path.relative_to(settings.data_dir).as_posix()


def resolve_relative(relative_path: str) -> Path:
    candidate = (settings.data_dir / relative_path).resolve()
    if settings.data_dir.resolve() not in candidate.parents:
        raise ValueError("Path escapes the data directory")
    return candidate
