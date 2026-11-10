from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import verify_chain
from app.core.db import get_session
from app.core.deps import require_roles
from app.core.schema import AuditEvent, User

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/export")
def export_audit(
    from_ts: str | None = Query(default=None, alias="from"),
    to_ts: str | None = Query(default=None, alias="to"),
    session: Session = Depends(get_session),
    _user: User = Depends(require_roles("administrator")),
) -> Response:
    statement = select(AuditEvent).order_by(AuditEvent.seq.asc())
    if from_ts:
        statement = statement.where(AuditEvent.ts >= from_ts)
    if to_ts:
        statement = statement.where(AuditEvent.ts <= to_ts)
    events = session.execute(statement).scalars().all()
    lines = []
    for event in events:
        lines.append(
            json.dumps(
                {
                    "seq": event.seq,
                    "event_id": event.event_id,
                    "ts": event.ts,
                    "actor_id": event.actor_id,
                    "action": event.action,
                    "resource_type": event.resource_type,
                    "resource_id": event.resource_id,
                    "detail": json.loads(event.detail_json or "{}"),
                    "prev_hash": event.prev_hash,
                    "hash": event.hash,
                },
                sort_keys=True,
            )
        )
    return Response(
        content="\n".join(lines) + ("\n" if lines else ""),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="miap-audit.ndjson"'},
    )


@router.get("/verify")
def verify_audit(
    session: Session = Depends(get_session),
    _user: User = Depends(require_roles("administrator")),
) -> dict:
    ok, checked, first_bad = verify_chain(session)
    return {"ok": ok, "checked": checked, "first_bad_seq": first_bad}
