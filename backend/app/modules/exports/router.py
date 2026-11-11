from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.deps import require_roles
from app.core.schema import User
from app.modules.exports import service
from app.modules.exports.schemas import ExportRequest

router = APIRouter(prefix="/exports", tags=["exports"])


@router.post("")
def create_export(
    payload: ExportRequest,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("researcher")),
) -> Response:
    rows = service.build_rows(session, user, payload)
    body, media_type = service.render(rows, payload.format)
    extension = "json" if payload.format == "json" else "csv"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="miap-export.{extension}"'},
    )
