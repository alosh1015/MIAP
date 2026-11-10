from __future__ import annotations

from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, Field


class CaseCreate(BaseModel):
    pseudonym: str = Field(min_length=1, max_length=120)
    consent: Literal["clinical", "research", "teaching"]
    retention_days: int | None = Field(default=None, ge=1, le=3650)


class CaseSummary(BaseModel):
    id: str
    pseudonym: str
    consent: str
    status: str
    modality: str | None
    created_at: str
    image_count: int


class ImageSummary(BaseModel):
    id: str
    modality: str | None
    laterality: str | None
    view: str | None
    body_part: str | None
    body_part_raw: str | None = None
    mime: str
    rows: int | None
    cols: int | None
    created_at: str
    validation: dict
    deid_receipt: dict


class CaseDetail(CaseSummary):
    images: list[ImageSummary]
    exam: dict | None = None


def retention_until(days: int | None, now) -> str | None:
    if days is None:
        return None
    return (now + timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")
