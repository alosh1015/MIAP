from __future__ import annotations

from tests.conftest import API, PASSWORDS


def test_login_returns_token_and_role(client, make_user):
    from app.core.db import SessionLocal
    from app.core.schema import User

    user_id = make_user("clinician")
    assert SessionLocal is not None
    with SessionLocal() as session:
        email = session.get(User, user_id).email

    response = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORDS["clinician"]})
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["role"] == "clinician"
    assert body["access_token"]


def test_login_rejects_wrong_password(client, make_user):
    from app.core.db import SessionLocal
    from app.core.schema import User

    user_id = make_user("researcher")
    assert SessionLocal is not None
    with SessionLocal() as session:
        email = session.get(User, user_id).email

    response = client.post(f"{API}/auth/login", json={"email": email, "password": "wrong-password"})
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["status"] == 401


def test_me_requires_token(client):
    assert client.get(f"{API}/auth/me").status_code == 401


def test_me_returns_identity(client, auth):
    response = client.get(f"{API}/auth/me", headers=auth("administrator"))
    assert response.status_code == 200
    assert response.json()["role"] == "administrator"


def test_problem_json_on_unknown_route(client):
    response = client.get(f"{API}/does-not-exist")
    assert response.status_code == 404


def test_send_files_forbidden(client, auth):
    """Unauthenticated access to any image route is refused."""
    response = client.get(f"{API}/images/i_missing/file")
    assert response.status_code == 401
