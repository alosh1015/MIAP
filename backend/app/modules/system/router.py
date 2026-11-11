from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.deps import require_roles
from app.core.schema import User
from app.modules.system import service

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health")
def system_health(
    session: Session = Depends(get_session),
    _admin: User = Depends(require_roles("administrator")),
) -> dict:
    return service.health(session)
