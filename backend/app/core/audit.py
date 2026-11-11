from __future__ import annotations

import json
import threading
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.ids import new_id, utcnow_iso
from app.core.schema import AuditEvent

GENESIS_HASH = "0" * 64
_CHAIN_LOCK = threading.Lock()


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(event: dict[str, Any]) -> str:
    import hashlib

    return hashlib.sha256(_canonical(event).encode("utf-8")).hexdigest()


def _append(
    session: Session,
    *,
    actor_id: str | None,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditEvent:
    last = session.execute(select(AuditEvent).order_by(AuditEvent.seq.desc()).limit(1)).scalar_one_or_none()
    prev_hash = last.hash if last else GENESIS_HASH
    event = AuditEvent(
        event_id=new_id("audit"),
        ts=utcnow_iso(),
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail_json=_canonical(detail or {}),
        prev_hash=prev_hash,
        hash="",
    )
    body = {
        "event_id": event.event_id,
        "ts": event.ts,
        "actor_id": event.actor_id,
        "action": event.action,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        "detail": json.loads(event.detail_json),
        "prev_hash": prev_hash,
    }
    event.hash = _digest(body)
    session.add(event)
    session.flush()
    return event


def append_audit(
    session: Session,
    *,
    actor_id: str | None,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append one event to the hash chain. Caller owns the transaction."""
    with _CHAIN_LOCK:
        return _append(
            session,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
        )


def write_audit_now(
    *,
    actor_id: str | None,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Commit one event in its own write transaction before the caller returns.

    Identity reads use this through ``BEGIN IMMEDIATE`` so a reader cannot hand
    back decrypted details that are missing from the chain. If the append
    fails, the read fails.
    """
    from app.core import db

    if db.SessionLocal is None:
        raise RuntimeError("Database is not initialised; call init_db() first")
    with _CHAIN_LOCK:
        session = db.SessionLocal()
        try:
            session.execute(text("BEGIN IMMEDIATE"))
            _append(
                session,
                actor_id=actor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                detail=detail,
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def verify_chain(session: Session) -> tuple[bool, int, int | None]:
    """Return (ok, checked_count, first_bad_seq)."""
    prev = GENESIS_HASH
    checked = 0
    events = session.execute(select(AuditEvent).order_by(AuditEvent.seq.asc())).scalars().all()
    for event in events:
        body = {
            "event_id": event.event_id,
            "ts": event.ts,
            "actor_id": event.actor_id,
            "action": event.action,
            "resource_type": event.resource_type,
            "resource_id": event.resource_id,
            "detail": json.loads(event.detail_json),
            "prev_hash": event.prev_hash,
        }
        if event.prev_hash != prev or _digest(body) != event.hash:
            return False, checked, event.seq
        prev = event.hash
        checked += 1
    return True, checked, None
