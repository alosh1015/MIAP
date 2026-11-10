from __future__ import annotations

from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    case_id: str
    image_id: str
    model_id: str | None = None
    model_version: str | None = None
    params: dict = Field(default_factory=dict)
