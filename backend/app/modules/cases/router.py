from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.deps import get_current_user, require_roles
from app.core.schema import User
from app.modules.cases import service
from app.modules.cases.schemas import CaseCreate, CaseDetail, CaseSummary

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=CaseDetail, status_code=201)
def create_case(
    payload: CaseCreate,
    session: Session = Depends(get_session),
    user: User = Depends(require_roles("clinician", "researcher")),
) -> dict:
    case = service.create_case(session, user, payload)
    session.commit()
    return service.case_detail(session, user, case.id)


@router.get("", response_model=list[CaseSummary])
def list_cases(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    return service.list_cases(session, user, limit=limit, offset=offset)


@router.get("/{case_id}", response_model=CaseDetail)
def get_case(
    case_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    return service.case_detail(session, user, case_id)


@router.delete("/{case_id}", status_code=204)
def archive_case(
    case_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    service.delete_case(session, user, case_id)
    session.commit()
