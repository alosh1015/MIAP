from __future__ import annotations

from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, Field

from app.modules.patients.schemas import PatientSummary


class CaseCreate(BaseModel):
    pseudonym: str = Field(min_length=1, max_length=120)
    consent: Literal["clinical", "research", "teaching"]
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    patient_id: str | None = None


class CaseSummary(BaseModel):
    id: str
    pseudonym: str
    consent: str
    status: str
    modality: str | None
    created_at: str
    image_count: int
    patient_id: str | None = None
    patient_display: str | None = None
    identity_visible: bool = False
    ai_flag: str | None = None
    findings_to_review: int = 0
    reviewed: int = 0
    latest_result_id: str | None = None
    last_job: dict | None = None


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
    patient: PatientSummary | None = None


class PatientLink(BaseModel):
    patient_id: str = Field(min_length=1, max_length=64)


def retention_until(days: int | None, now) -> str | None:
    if days is None:
        return None
    return (now + timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")
