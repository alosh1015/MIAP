from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.core.audit import append_audit
from app.core.errors import AppError
from app.core.ids import utcnow_iso
from app.core.schema import AppSetting, User, UserPref
from app.modules.settings.schemas import (
    Preferences,
    PreferencesPatch,
    SettingsResponse,
    SystemSettings,
    SystemSettingsPatch,
)

CAPABILITIES: dict[str, dict[str, bool]] = {
    "clinician": {
        "can_see_identity": True,
        "can_create_patient": True,
        "can_review_findings": True,
        "can_run_batch": True,
        "can_export_dataset": False,
        "can_view_images": True,
        "can_manage_users": False,
        "can_approve_models": False,
        "can_verify_audit": False,
        "can_manage_retention": False,
    },
    "researcher": {
        "can_see_identity": False,
        "can_create_patient": False,
        "can_review_findings": False,
        "can_run_batch": True,
        "can_export_dataset": True,
        "can_view_images": True,
        "can_manage_users": False,
        "can_approve_models": False,
        "can_verify_audit": False,
        "can_manage_retention": False,
    },
    "administrator": {
        "can_see_identity": False,
        "can_create_patient": False,
        "can_review_findings": False,
        "can_run_batch": False,
        "can_export_dataset": False,
        "can_view_images": False,
        "can_manage_users": True,
        "can_approve_models": True,
        "can_verify_audit": True,
        "can_manage_retention": True,
    },
}

SYSTEM_DEFAULTS = {
    "retention_default_days": 365,
    "export_row_cap": 5000,
    "max_batch_images": 40,
    "tb_notice": (
        "MIAP does not screen for tuberculosis. A low or negative AI result does not "
        "exclude TB; use the local TB pathway."
    ),
}


def preferences_for(session: Session, user: User) -> Preferences:
    row = session.get(UserPref, user.id)
    stored = json.loads(row.prefs_json or "{}") if row else {}
    return Preferences(**{**Preferences().model_dump(), **stored})


def update_preferences(session: Session, user: User, patch: PreferencesPatch) -> Preferences:
    current = preferences_for(session, user)
    changes = patch.model_dump(exclude_unset=True)
    merged = {**current.model_dump(), **changes}
    prefs = Preferences(**merged)
    row = session.get(UserPref, user.id)
    if row is None:
        session.add(UserPref(user_id=user.id, prefs_json=json.dumps(prefs.model_dump()), updated_at=utcnow_iso()))
    else:
        row.prefs_json = json.dumps(prefs.model_dump())
        row.updated_at = utcnow_iso()
    append_audit(
        session,
        actor_id=user.id,
        action="settings.updated",
        resource_type="user",
        resource_id=user.id,
        detail={"scope": "personal", "fields": sorted(changes)},
    )
    return prefs


def settings_for(session: Session, user: User) -> SettingsResponse:
    prefs = preferences_for(session, user)
    system = get_system_settings(session)
    return SettingsResponse(
        profile={"id": user.id, "email": user.email, "display_name": user.display_name, "role": user.role},
        preferences=prefs,
        capabilities=CAPABILITIES.get(user.role, {}),
        viewer_defaults={
            "overlay_opacity": prefs.viewer_overlay_opacity,
            "split_view": prefs.viewer_split,
            "theme": prefs.theme,
        },
        notices=[system.tb_notice, "Decision support only. Not a diagnostic device."],
    )


def get_system_settings(session: Session) -> SystemSettings:
    rows = session.query(AppSetting).all()
    values = {row.key: json.loads(row.value_json) for row in rows}
    merged = {**SYSTEM_DEFAULTS, **{key: value for key, value in values.items() if key in SYSTEM_DEFAULTS}}
    return SystemSettings(**merged)


def update_system_settings(session: Session, user: User, patch: SystemSettingsPatch) -> SystemSettings:
    changes = patch.model_dump(exclude_unset=True)
    now = utcnow_iso()
    for key, value in changes.items():
        row = session.get(AppSetting, key)
        if row is None:
            session.add(AppSetting(key=key, value_json=json.dumps(value), updated_by=user.id, updated_at=now))
        else:
            row.value_json = json.dumps(value)
            row.updated_by = user.id
            row.updated_at = now
    append_audit(
        session,
        actor_id=user.id,
        action="settings.updated",
        resource_type="system",
        resource_id=None,
        detail={"scope": "system", "fields": sorted(changes)},
    )
    return get_system_settings(session)


def require_capability(user: User, capability: str) -> None:
    if not CAPABILITIES.get(user.role, {}).get(capability):
        raise AppError(403, "forbidden", "Your role cannot perform this action")
