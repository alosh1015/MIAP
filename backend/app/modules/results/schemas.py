from __future__ import annotations

from pydantic import BaseModel, Field


class ConfidenceSource(BaseModel):
    value: str
    method: str
    confidence: float = Field(ge=0.0, le=1.0)


class ModelRef(BaseModel):
    name: str
    version: str
    digest: str | None = None
    demo: bool = False


class Finding(BaseModel):
    label: str
    probability: float = Field(ge=0.0, le=1.0)
    threshold: float | None = None


class Detection(BaseModel):
    label: str
    box: list[float]
    score: float = Field(ge=0.0, le=1.0)


class HeatmapRef(BaseModel):
    format: str = "npy"
    path: str
    overlay_png: str | None = None
    shape: list[int] | None = None


class Birads(BaseModel):
    category: str | None = None
    supporting_findings: list[str] = Field(default_factory=list)


class ResultDocument(BaseModel):
    """Canonical result, MIAP §7 plus model digest, provenance and degraded flag."""

    case_id: str
    image_id: str
    modality: ConfidenceSource
    region_or_view: ConfidenceSource
    model: ModelRef
    classification: dict[str, str | float]
    findings: list[Finding] = Field(default_factory=list)
    detections: list[Detection] = Field(default_factory=list)
    segmentation: dict | None = None
    heatmap: HeatmapRef | None = None
    birads: Birads | None = None
    density: str | None = None
    warnings: list[str] = Field(default_factory=list)
    provenance_id: str
    degraded: bool = False
    created_at: str
