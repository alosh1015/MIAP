from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.deps import require_roles
from app.core.schema import User
from app.modules.reviews import service
from app.modules.reviews.schemas import ReviewOut, ReviewRequest, ReviewSummary

router = APIRouter(tags=["reviews"])


@router.post("/results/{result_id}/findings/{finding_index}/review", response_model=ReviewOut)
def review_finding(
    result_id: str,
    payload: ReviewRequest,
    finding_index: int = Path(ge=0),
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician")),
) -> ReviewOut:
    review = service.upsert_review(session, user, result_id, finding_index, payload)
    session.commit()
    return ReviewOut(
        finding_index=review.finding_index,
        decision=review.decision,
        has_note=bool(review.has_note),
        note=None,
        reviewer_id=review.reviewer_id,
        revision=review.revision,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


@router.get("/results/{result_id}/reviews", response_model=ReviewSummary)
def list_reviews(
    result_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician", "researcher")),
) -> ReviewSummary:
    return service.list_reviews(session, user, result_id)
