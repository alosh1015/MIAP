from __future__ import annotations

import os
import base64
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

TMP_ROOT = Path(tempfile.mkdtemp(prefix="miap-tests-"))
os.environ["MIAP_ENV"] = "test"
os.environ["MIAP_DATA_DIR"] = str(TMP_ROOT / "data")
os.environ["MIAP_DATABASE_PATH"] = str(TMP_ROOT / "data" / "test.db")
os.environ["MIAP_SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["MIAP_MODEL_BACKEND"] = "stub"
os.environ["MIAP_UPLOAD_MAX_BYTES"] = str(2 * 1024 * 1024)
os.environ["MIAP_REGISTRY_PATH"] = str(Path(__file__).resolve().parents[2] / "ml" / "registry.json")
os.environ["MIAP_PII_KEY"] = base64.b64encode(bytes(range(32))).decode()
os.environ["MIAP_PII_INDEX_KEY"] = base64.b64encode(bytes(range(32, 64))).decode()
os.environ["MIAP_PII_KEY_VERSION"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "generated"
API = "/api/v1"
PASSWORDS = {
    "clinician": "clinic-test-pw",
    "researcher": "research-test-pw",
    "administrator": "admin-test-pw",
}


@pytest.fixture(scope="session")
def client():
    with TestClient(create_app()) as test_client:
        yield test_client
    shutil.rmtree(TMP_ROOT, ignore_errors=True)


@pytest.fixture(scope="session")
def make_user(client):
    from app.core.db import SessionLocal
    from app.core.security import hash_password
    from app.core.schema import User
    from app.core.ids import new_id, utcnow_iso

    created: dict[str, str] = {}

    def _make(role: str) -> str:
        if role in created:
            return created[role]
        assert SessionLocal is not None
        user_id = new_id("user")
        with SessionLocal() as session:
            session.add(
                User(
                    id=user_id,
                    email=f"{role}-{uuid.uuid4().hex[:8]}@miap.test",
                    password_hash=hash_password(PASSWORDS[role]),
                    display_name=f"Test {role}",
                    role=role,
                    is_active=True,
                    created_at=utcnow_iso(),
                )
            )
            session.commit()
        created[role] = user_id
        return user_id

    return _make


@pytest.fixture(scope="session")
def auth(client, make_user):
    headers: dict[str, dict[str, str]] = {}

    def _headers(role: str) -> dict[str, str]:
        if role not in headers:
            user_id = make_user(role)
            from app.core.db import SessionLocal
            from app.core.schema import User

            assert SessionLocal is not None
            with SessionLocal() as session:
                email = session.get(User, user_id).email
            response = client.post(
                f"{API}/auth/login",
                json={"email": email, "password": PASSWORDS[role]},
            )
            assert response.status_code == 200, response.text
            headers[role] = {"Authorization": f"Bearer {response.json()['access_token']}"}
        return headers[role]

    return _headers


@pytest.fixture(scope="session")
def new_case(client, auth):
    def _new(role: str = "clinician") -> str:
        response = client.post(
            f"{API}/cases",
            json={"pseudonym": f"PT-{uuid.uuid4().hex[:8]}", "consent": "research"},
            headers=auth(role),
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    return _new


@pytest.fixture(scope="session")
def upload(client, auth):
    def _upload(case_id: str, path: Path, role: str = "clinician", **overrides):
        with path.open("rb") as handle:
            files = {"file": (path.name, handle, "application/octet-stream")}
            data = {key: str(value) for key, value in overrides.items() if value is not None}
            return client.post(
                f"{API}/cases/{case_id}/images",
                files=files,
                data=data,
                headers=auth(role),
            )

    return _upload


@pytest.fixture(scope="session")
def chest_image(client, auth, new_case, upload):
    def _chest(role: str = "clinician") -> tuple[str, dict]:
        case_id = new_case(role)
        response = upload(case_id, FIXTURES / "chest_pa.dcm", role=role)
        assert response.status_code == 201, response.text
        return case_id, response.json()["image"]

    return _chest
