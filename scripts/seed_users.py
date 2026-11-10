"""Create the three demo accounts. Idempotent. Development only."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.core import db  # noqa: E402
from app.core.ids import new_id, utcnow_iso  # noqa: E402
from app.core.schema import User  # noqa: E402
from app.core.security import hash_password  # noqa: E402

ACCOUNTS = [
    ("clinician@miap.local", "Clinician Demo", "clinician", os.environ.get("MIAP_CLINICIAN_PASSWORD", "miap-demo-2026")),
    ("researcher@miap.local", "Researcher Demo", "researcher", os.environ.get("MIAP_RESEARCHER_PASSWORD", "miap-demo-2026")),
    ("admin@miap.local", "Administrator Demo", "administrator", os.environ.get("MIAP_ADMIN_PASSWORD", "miap-demo-2026")),
]


def main() -> None:
    db.init_db()
    assert db.SessionLocal is not None
    created = 0
    with db.SessionLocal() as session:
        for email, name, role, password in ACCOUNTS:
            existing = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
            if existing is not None:
                continue
            session.add(
                User(
                    id=new_id("user"),
                    email=email,
                    password_hash=hash_password(password),
                    display_name=name,
                    role=role,
                    is_active=1,
                    created_at=utcnow_iso(),
                )
            )
            created += 1
        session.commit()

    print(f"Created {created} account(s).")
    for email, _name, role, password in ACCOUNTS:
        print(f"  {role:14} {email:26} {password}")
    print("Change these passwords before any real deployment.")


if __name__ == "__main__":
    main()
