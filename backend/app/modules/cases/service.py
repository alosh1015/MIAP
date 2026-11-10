from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import append_audit
from app.core.errors import AppError
from app.core.ids import new_id, utcnow, utcnow_iso
from app.core.schema import Case, Image, User
from app.modules.cases.schemas import CaseCreate, ImageSummary, retention_until
from app.modules.routing.service import capability_for, group_mammogram_views, normalise_laterality, normalise_view

IMAGE_ROLES = {"clinician", "researcher"}


def _case_filter(user: User):
    if user.role == "administrator":
        return None
    if user.role == "researcher":
        return (Case.created_by == user.id) | (Case.consent == "research")
    return Case.created_by == user.id


def can_access_case(user: User, case: Case) -> bool:
    if user.role == "administrator":
        return True
    if case.created_by == user.id:
        return True
    return user.role == "researcher" and case.consent == "research"


def assert_case_access(user: User, case: Case | None) -> Case:
    if case is None or not can_access_case(user, case):
        raise AppError(404, "case_not_found", "Case not found")
    return case


def create_case(session: Session, user: User, payload: CaseCreate) -> Case:
    if user.role not in IMAGE_ROLES:
        raise AppError(403, "forbidden", "Administrators cannot create cases")
    now = utcnow()
    case = Case(
        id=new_id("case"),
        pseudonym=payload.pseudonym.strip(),
        consent=payload.consent,
        created_by=user.id,
        status="created",
        modality=None,
        retention_until=retention_until(payload.retention_days, now),
        created_at=utcnow_iso(),
    )
    session.add(case)
    append_audit(
        session,
        actor_id=user.id,
        action="case.created",
        resource_type="case",
        resource_id=case.id,
        detail={"consent": payload.consent},
    )
    return case


def _image_counts(session: Session, case_ids: list[str]) -> dict[str, int]:
    if not case_ids:
        return {}
    rows = session.execute(
        select(Image.case_id, func.count(Image.id)).where(Image.case_id.in_(case_ids)).group_by(Image.case_id)
    ).all()
    return {case_id: count for case_id, count in rows}


def list_cases(session: Session, user: User, limit: int = 50, offset: int = 0) -> list[dict]:
    statement = select(Case).order_by(Case.created_at.desc()).limit(limit).offset(offset)
    condition = _case_filter(user)
    if condition is not None:
        statement = statement.where(condition)
    cases = session.execute(statement).scalars().all()
    counts = _image_counts(session, [case.id for case in cases])
    return [
        {
            "id": case.id,
            "pseudonym": case.pseudonym,
            "consent": case.consent,
            "status": case.status,
            "modality": case.modality,
            "created_at": case.created_at,
            "image_count": counts.get(case.id, 0),
        }
        for case in cases
    ]


def _image_summary(image: Image) -> ImageSummary:
    return ImageSummary(
        id=image.id,
        modality=image.modality,
        laterality=normalise_laterality(image.laterality),
        view=normalise_view(image.view),
        body_part=image.body_part,
        body_part_raw=image.body_part_raw,
        mime=image.mime,
        rows=image.rows,
        cols=image.cols,
        created_at=image.created_at,
        validation=json.loads(image.validation_json or "{}"),
        deid_receipt=json.loads(image.deid_receipt_json or "{}"),
    )


def case_detail(session: Session, user: User, case_id: str) -> dict:
    case = assert_case_access(user, session.get(Case, case_id))
    images = session.execute(select(Image).where(Image.case_id == case_id).order_by(Image.created_at)).scalars().all()
    payload = {
        "id": case.id,
        "pseudonym": case.pseudonym,
        "consent": case.consent,
        "status": case.status,
        "modality": case.modality,
        "created_at": case.created_at,
        "image_count": len(images),
        "images": [],
        "exam": None,
    }
    if user.role == "administrator":
        # Administrators get metadata only: no image bytes, no pixel-level detail.
        return payload

    summaries = [_image_summary(image) for image in images]
    payload["images"] = [summary.model_dump() for summary in summaries]

    mammograms = [summary for summary in summaries if summary.modality == "mammogram"]
    xrays = [summary for summary in summaries if summary.modality == "xray"]
    if mammograms:
        grouped = group_mammogram_views([summary.model_dump() for summary in mammograms])
        payload["exam"] = {"type": "mammogram_four_view", **grouped}
    elif xrays:
        payload["exam"] = {
            "type": "xray",
            "regions": [
                {
                    "image_id": summary.id,
                    "body_part": summary.body_part_raw or summary.body_part,
                    "region": summary.body_part,
                    "capability": capability_for(summary.body_part or "unrecognised"),
                }
                for summary in xrays
            ],
        }
    return payload


def delete_case(session: Session, user: User, case_id: str) -> None:
    case = assert_case_access(user, session.get(Case, case_id))
    if case.created_by != user.id and user.role != "administrator":
        raise AppError(403, "forbidden", "Only the case owner can delete a case")
    case.status = "archived"
    append_audit(
        session,
        actor_id=user.id,
        action="case.archived",
        resource_type="case",
        resource_id=case.id,
        detail={},
    )
