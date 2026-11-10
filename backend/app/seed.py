"""Create the demo accounts. Run from the backend directory:

    python -m app.seed
"""

from __future__ import annotations

import argparse

from app.core import db
from app.core.config import get_settings
from app.core.ids import new_id, utcnow_iso
from app.core.schema import User
from app.core.security import hash_password

DEMO_USERS = (
    ("clinician@miap.local", "Dr. Aisha Nakato", "clinician"),
    ("researcher@miap.local", "Joshua Kakaire", "researcher"),
    ("admin@miap.local", "MIAP Administrator", "administrator"),
)
DEMO_PASSWORD = "miap-demo-2026"


def seed_users() -> list[tuple[str, str]]:
    db.init_db()
    assert db.SessionLocal is not None
    created: list[tuple[str, str]] = []
    with db.SessionLocal() as session:
        for email, name, role in DEMO_USERS:
            if session.query(User).filter(User.email == email).first() is not None:
                continue
            session.add(
                User(
                    id=new_id("user"),
                    email=email,
                    display_name=name,
                    role=role,
                    password_hash=hash_password(DEMO_PASSWORD),
                    created_at=utcnow_iso(),
                )
            )
            created.append((email, role))
        session.commit()
    return created


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed MIAP demo users")
    parser.parse_args()
    if get_settings().env == "production":
        raise SystemExit("Refusing to seed demo accounts in production")
    created = seed_users()
    if not created:
        print("Demo users already exist; nothing created.")
        return
    print(f"Created {len(created)} demo users (password: {DEMO_PASSWORD}):")
    for email, role in created:
        print(f"  {role:14s} {email}")


if __name__ == "__main__":
    main()
