from __future__ import annotations

from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    case_id: str
    image_id: str
    model_id: str | None = None
    model_version: str | None = None
    params: dict = Field(default_factory=dict)


class BatchModelChoice(BaseModel):
    model_id: str | None = None
    model_version: str | None = None


class BatchAnalysisRequest(BaseModel):
    case_id: str
    image_ids: list[str] | None = None
    models: list[BatchModelChoice] = Field(default_factory=list)
    params: dict = Field(default_factory=dict)


class ExamAnalysisRequest(BaseModel):
    case_id: str
    image_ids: list[str] | None = None
