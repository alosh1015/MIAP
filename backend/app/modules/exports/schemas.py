from __future__ import annotations

import csv
import hashlib
import io
import json
from typing import Literal

from pydantic import BaseModel, Field


class ExportRequest(BaseModel):
    format: Literal["csv", "json"] = "csv"
    consent: Literal["clinical", "research", "teaching"] | None = None
    modality: Literal["xray", "mammogram"] | None = None
    limit: int | None = Field(default=None, ge=1, le=100_000)


def filter_digest(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def rows_to_csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for row in rows:
        writer.writerow({key: (json.dumps(value) if isinstance(value, (list, dict)) else value) for key, value in row.items()})
    return buffer.getvalue()
