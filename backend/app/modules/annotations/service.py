"""Reviewer-drawn lasso highlights on a stored image.

Points are normalised to the image frame (0..1), so the same polygon renders in
the viewer and in a PDF at any size. Highlights only carry shape coordinates;
they are not findings and never change model output.
"""

from __future__ import annotations

import json

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.audit import append_audit
from app.core.errors import AppError
from app.core.ids import new_id, utcnow_iso
from app.core.schema import Case, Image, ImageAnnotation, User
from app.modules.cases.service import can_access_case


def _image_for(session: Session, user: User, case_id: str, image_id: str) -> Image:
    case = session.get(Case, case_id)
    if case is None or user.role == "administrator" or not can_access_case(user, case):
        raise AppError(404, "image_not_found", "Image not found")
    image = session.get(Image, image_id)
    if image is None or image.case_id != case_id:
        raise AppError(404, "image_not_found", "Image not found")
    return image


def _payload(annotation: ImageAnnotation) -> dict:
    try:
        points = json.loads(annotation.points_json)
    except ValueError:
        points = []
    return {
        "id": annotation.id,
        "image_id": annotation.image_id,
        "points": points,
        "created_at": annotation.created_at,
    }


def list_annotations(session: Session, user: User, case_id: str, image_id: str) -> list[dict]:
    image = _image_for(session, user, case_id, image_id)
    rows = session.execute(
        select(ImageAnnotation)
        .where(ImageAnnotation.image_id == image.id)
        .order_by(ImageAnnotation.created_at)
    ).scalars()
    return [_payload(row) for row in rows]


def add_annotation(
    session: Session, user: User, case_id: str, image_id: str, points: list[tuple[float, float]]
) -> dict:
    image = _image_for(session, user, case_id, image_id)
    annotation = ImageAnnotation(
        id=new_id("annot"),
        case_id=case_id,
        image_id=image.id,
        created_by=user.id,
        points_json=json.dumps(points),
        created_at=utcnow_iso(),
    )
    session.add(annotation)
    session.flush()
    append_audit(
        session,
        actor_id=user.id,
        action="annotation.created",
        resource_type="image",
        resource_id=image.id,
        detail={"annotation_id": annotation.id, "points": len(points)},
    )
    return _payload(annotation)


def clear_annotations(session: Session, user: User, case_id: str, image_id: str) -> int:
    image = _image_for(session, user, case_id, image_id)
    removed = session.execute(
        delete(ImageAnnotation).where(ImageAnnotation.image_id == image.id)
    ).rowcount
    if removed:
        append_audit(
            session,
            actor_id=user.id,
            action="annotation.cleared",
            resource_type="image",
            resource_id=image.id,
            detail={"removed": removed},
        )
    return int(removed or 0)
