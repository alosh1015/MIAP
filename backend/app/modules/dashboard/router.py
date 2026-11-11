from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.deps import get_current_user
from app.core.schema import User
from app.modules.dashboard.service import dashboard_for

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def get_dashboard(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    return dashboard_for(session, user)
