from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.deps import require_roles
from app.core.schema import User
from app.modules.retention import service
from app.modules.retention.schemas import RetentionRunRequest

router = APIRouter(prefix="/retention", tags=["retention"])


@router.get("/preview")
def preview_retention(
    session: Session = Depends(get_session),
    admin: User = Depends(require_roles("administrator")),
) -> dict:
    return service.preview(session, admin)


@router.post("/run")
def run_retention(
    payload: RetentionRunRequest,
    session: Session = Depends(get_session),
    admin: User = Depends(require_roles("administrator")),
) -> dict:
    return service.run(session, admin, confirm=payload.confirm)
