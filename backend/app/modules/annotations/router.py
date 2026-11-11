from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.deps import require_roles
from app.core.schema import User
from app.modules.annotations import service
from app.modules.annotations.schemas import AnnotationIn, AnnotationOut

router = APIRouter(prefix="/cases/{case_id}/images/{image_id}/annotations", tags=["annotations"])


@router.get("", response_model=list[AnnotationOut])
def list_annotations(
    case_id: str,
    image_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician", "researcher")),
) -> list[dict]:
    return service.list_annotations(session, user, case_id, image_id)


@router.post("", response_model=AnnotationOut, status_code=201)
def create_annotation(
    case_id: str,
    image_id: str,
    payload: AnnotationIn,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician", "researcher")),
) -> dict:
    annotation = service.add_annotation(session, user, case_id, image_id, payload.points)
    session.commit()
    return annotation


@router.delete("")
def clear_annotations(
    case_id: str,
    image_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician", "researcher")),
) -> dict:
    removed = service.clear_annotations(session, user, case_id, image_id)
    session.commit()
    return {"removed": removed}
