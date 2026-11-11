from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator


class PatientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    hospital_number: str = Field(min_length=1, max_length=64)
    sex: str = Field(default="unknown", max_length=16)
    dob: date | None = None

    @field_validator("name", "hospital_number")
    @classmethod
    def _strip(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be blank")
        return cleaned


class PatientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    hospital_number: str | None = Field(default=None, min_length=1, max_length=64)
    sex: str | None = Field(default=None, max_length=16)
    dob: date | None = None


class PatientCaseRef(BaseModel):
    id: str
    pseudonym: str
    status: str
    modality: str | None
    created_at: str


class PatientSummary(BaseModel):
    id: str
    name: str
    hospital_number: str
    sex: str
    dob: str | None
    age: int | None
    case_count: int
    created_at: str
    updated_at: str


class PatientDetail(PatientSummary):
    cases: list[PatientCaseRef] = Field(default_factory=list)


class LookupResult(BaseModel):
    found: bool
    patient: PatientSummary | None = None
