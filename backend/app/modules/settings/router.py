from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.deps import get_current_user, require_roles
from app.core.schema import User
from app.modules.settings import service
from app.modules.settings.schemas import (
    PreferencesPatch,
    SettingsResponse,
    SystemSettings,
    SystemSettingsPatch,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/me", response_model=SettingsResponse)
def my_settings(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SettingsResponse:
    return service.settings_for(session, user)


@router.patch("/me", response_model=SettingsResponse)
def update_my_settings(
    payload: PreferencesPatch,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> SettingsResponse:
    service.update_preferences(session, user, payload)
    session.commit()
    return service.settings_for(session, user)


@router.get("/system", response_model=SystemSettings)
def system_settings(
    session: Session = Depends(get_session),
    _user: User = Depends(require_roles("administrator")),
) -> SystemSettings:
    return service.get_system_settings(session)


@router.patch("/system", response_model=SystemSettings)
def update_system_settings(
    payload: SystemSettingsPatch,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("administrator")),
) -> SystemSettings:
    settings = service.update_system_settings(session, user, payload)
    session.commit()
    return settings
