from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

PREFIXES = {
    "case": "c",
    "image": "i",
    "job": "j",
    "result": "r",
    "provenance": "p",
    "report": "rp",
    "audit": "a",
    "user": "u",
}


def new_id(kind: str) -> str:
    prefix = PREFIXES[kind]
    return f"{prefix}_{uuid.uuid4()}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat(timespec="seconds").replace("+00:00", "Z")


def to_sqlite_value(value: object) -> object:
    """SQLite has no native datetime; store ISO-8601 UTC strings."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return value


def is_sqlite_error(exc: BaseException) -> bool:
    return isinstance(exc, sqlite3.Error)
