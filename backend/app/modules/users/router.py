from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.deps import require_roles
from app.core.errors import AppError
from app.core.schema import User
from app.modules.users import service
from app.modules.users.schemas import PasswordReset, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


def _target(session: Session, user_id: str) -> User:
    target = session.get(User, user_id)
    if target is None:
        raise AppError(404, "user_not_found", "User not found")
    return target


@router.get("", response_model=list[UserOut])
def list_users(
    session: Session = Depends(get_session),
    _admin: User = Depends(require_roles("administrator")),
) -> list[UserOut]:
    return service.list_users(session)


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    session: Session = Depends(get_session),
    admin: User = Depends(require_roles("administrator")),
) -> UserOut:
    created = service.create_user(session, admin, payload)
    session.commit()
    return created


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    payload: UserUpdate,
    session: Session = Depends(get_session),
    admin: User = Depends(require_roles("administrator")),
) -> UserOut:
    updated = service.update_user(session, admin, _target(session, user_id), payload)
    session.commit()
    return updated


@router.post("/{user_id}/password-reset", status_code=204)
def reset_password(
    user_id: str,
    payload: PasswordReset,
    session: Session = Depends(get_session),
    admin: User = Depends(require_roles("administrator")),
) -> None:
    service.reset_password(session, admin, _target(session, user_id), payload)
    session.commit()
