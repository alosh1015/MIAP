from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import AppError
from app.core.ids import utcnow_iso
from app.core.schema import Patient, User
from app.core.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)

ROLES = ("clinician", "researcher", "administrator")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(get_session),
) -> User:
    if credentials is None or not credentials.credentials:
        raise AppError(401, "not_authenticated", "Authentication required")
    payload = decode_access_token(credentials.credentials)
    user = session.get(User, payload["sub"])
    if user is None or not user.is_active:
        raise AppError(401, "invalid_token", "User is not active")
    return user


def require_roles(*roles: str) -> Callable[..., User]:
    def _dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise AppError(403, "forbidden", "Your role cannot perform this action")
        return user

    return _dependency


def require_image_reader(user: User = Depends(get_current_user)) -> User:
    if user.role == "administrator":
        raise AppError(403, "images_forbidden", "Administrators do not have access to image content")
    return user


def require_identity_reader(user: User = Depends(get_current_user)) -> User:
    """Only the treating clinician may read names, hospital numbers, or DOB."""
    if user.role != "clinician":
        raise AppError(
            403,
            "identity_forbidden",
            "Patient identity is restricted to the treating clinician",
        )
    return user


def require_patient_owner(
    patient_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_identity_reader),
) -> User:
    patient = session.get(Patient, patient_id)
    if patient is None or patient.owner_id != user.id:
        raise AppError(404, "patient_not_found", "Patient not found")
    return user


def audit_login(session: Session, user: User) -> None:
    from app.core.audit import append_audit

    append_audit(session, actor_id=user.id, action="auth.login", resource_type="user", resource_id=user.id)


def iso_now() -> str:
    return utcnow_iso()
