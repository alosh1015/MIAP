from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class AnnotationIn(BaseModel):
    points: list[tuple[float, float]] = Field(min_length=3, max_length=2000)

    @field_validator("points")
    @classmethod
    def within_image(cls, value: list[tuple[float, float]]) -> list[tuple[float, float]]:
        for x, y in value:
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                raise ValueError("annotation points must be normalised to the image, 0..1")
        return value


class AnnotationOut(BaseModel):
    id: str
    image_id: str
    points: list[tuple[float, float]]
    created_at: str
