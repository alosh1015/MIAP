from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import append_audit
from app.core.errors import AppError
from app.core.schema import User
from app.core.security import create_access_token, verify_password


def authenticate(session: Session, email: str, password: str) -> tuple[User, str]:
    user = session.execute(select(User).where(User.email == email.strip().lower())).scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise AppError(401, "invalid_credentials", "Email or password is incorrect")
    if not user.is_active:
        raise AppError(403, "account_disabled", "This account is disabled")

    token = create_access_token(user.id, user.role, user.display_name)
    append_audit(
        session,
        actor_id=user.id,
        action="auth.login",
        resource_type="user",
        resource_id=user.id,
        detail={"role": user.role},
    )
    session.commit()
    return user, token
