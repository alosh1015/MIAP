from __future__ import annotations

import json

from tests.conftest import API


def test_audit_chain_verifies(client, auth):
    response = client.get(f"{API}/audit/verify", headers=auth("administrator"))
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["checked"] > 0
    assert body["first_bad_seq"] is None


def test_audit_export_is_ndjson(client, auth):
    response = client.get(f"{API}/audit/export", headers=auth("administrator"))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    lines = [line for line in response.text.splitlines() if line.strip()]
    assert lines
    events = [json.loads(line) for line in lines]
    assert {"seq", "event_id", "action", "prev_hash", "hash"} <= set(events[0])
    actions = {event["action"] for event in events}
    assert "auth.login" in actions


def test_only_administrator_may_export(client, auth):
    for role in ("clinician", "researcher"):
        assert client.get(f"{API}/audit/export", headers=auth(role)).status_code == 403
        assert client.get(f"{API}/audit/verify", headers=auth(role)).status_code == 403


def test_tampering_breaks_the_chain_and_is_detected(client, auth):
    from sqlalchemy import select

    from app.core.audit import verify_chain
    from app.core.db import SessionLocal
    from app.core.schema import AuditEvent

    assert SessionLocal is not None
    with SessionLocal() as session:
        event = session.execute(select(AuditEvent).order_by(AuditEvent.seq.asc())).scalars().first()
        original = event.detail_json
        event.detail_json = json.dumps({"tampered": True})
        session.commit()
        seq = event.seq

    damaged = client.get(f"{API}/audit/verify", headers=auth("administrator")).json()
    assert damaged["ok"] is False
    assert damaged["first_bad_seq"] == seq

    with SessionLocal() as session:
        statement = select(AuditEvent).where(AuditEvent.seq == seq)
        event = session.execute(statement).scalar_one()
        event.detail_json = original
        session.commit()
        ok, _checked, _bad = verify_chain(session)
    assert ok is True

    assert client.get(f"{API}/audit/verify", headers=auth("administrator")).json()["ok"] is True
