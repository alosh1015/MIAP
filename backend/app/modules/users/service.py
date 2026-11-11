from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import append_audit
from app.core.errors import AppError
from app.core.ids import new_id, utcnow_iso
from app.core.schema import User
from app.core.security import hash_password
from app.modules.users.schemas import PasswordReset, UserCreate, UserOut, UserUpdate


def _out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        is_active=bool(user.is_active),
        created_at=user.created_at,
    )


def list_users(session: Session) -> list[UserOut]:
    users = session.execute(select(User).order_by(User.created_at)).scalars().all()
    return [_out(user) for user in users]


def create_user(session: Session, admin: User, payload: UserCreate) -> UserOut:
    existing = session.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing is not None:
        raise AppError(409, "email_exists", "An account with this email already exists")
    user = User(
        id=new_id("user"),
        email=payload.email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
        role=payload.role,
        is_active=1,
        created_at=utcnow_iso(),
    )
    session.add(user)
    append_audit(
        session,
        actor_id=admin.id,
        action="user.created",
        resource_type="user",
        resource_id=user.id,
        detail={"role": user.role},
    )
    session.flush()
    return _out(user)


def update_user(session: Session, admin: User, target: User, payload: UserUpdate) -> UserOut:
    changes = payload.model_dump(exclude_unset=True)
    if target.id == admin.id:
        if changes.get("is_active") is False:
            raise AppError(422, "self_lockout", "You cannot deactivate your own account")
        if "role" in changes and changes["role"] != "administrator":
            raise AppError(422, "self_lockout", "You cannot remove your own administrator role")
    if "display_name" in changes:
        target.display_name = str(changes["display_name"]).strip()
    if "role" in changes:
        target.role = str(changes["role"])
    if "is_active" in changes:
        target.is_active = 1 if changes["is_active"] else 0
    action = "user.updated"
    if "is_active" in changes:
        action = "user.activated" if changes["is_active"] else "user.deactivated"
    append_audit(
        session,
        actor_id=admin.id,
        action=action,
        resource_type="user",
        resource_id=target.id,
        detail={"fields": sorted(changes)},
    )
    return _out(target)


def reset_password(session: Session, admin: User, target: User, payload: PasswordReset) -> None:
    target.password_hash = hash_password(payload.password)
    append_audit(
        session,
        actor_id=admin.id,
        action="user.password_reset",
        resource_type="user",
        resource_id=target.id,
        detail={},
    )
