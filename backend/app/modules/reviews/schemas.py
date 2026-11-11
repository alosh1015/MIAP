from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ReviewRequest(BaseModel):
    decision: Literal["confirmed", "dismissed"]
    note: str | None = Field(default=None, max_length=2000)


class ReviewOut(BaseModel):
    finding_index: int
    decision: str
    has_note: bool
    note: str | None = None
    reviewer_id: str
    revision: int
    created_at: str
    updated_at: str


class ReviewSummary(BaseModel):
    findings_to_review: int
    reviewed: int
    confirmed: int
    dismissed: int
    with_notes: int
    items: list[ReviewOut] = Field(default_factory=list)
    notes_visible: bool = False
