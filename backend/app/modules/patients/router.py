from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.deps import require_identity_reader, require_patient_owner
from app.core.schema import Patient, User
from app.modules.patients import service
from app.modules.patients.schemas import (
    LookupResult,
    PatientCreate,
    PatientDetail,
    PatientSummary,
    PatientUpdate,
)

router = APIRouter(prefix="/patients", tags=["patients"])


@router.post("", response_model=PatientDetail, status_code=201)
def create_patient(
    payload: PatientCreate,
    session: Session = Depends(get_session),
    user: User = Depends(require_identity_reader),
) -> dict:
    patient = service.create_patient(session, user, payload)
    session.commit()
    return service.patient_detail(session, user, patient, audit=False)


@router.get("", response_model=list[PatientSummary])
def list_patients(
    query: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
    user: User = Depends(require_identity_reader),
) -> list[dict]:
    return service.list_patients(session, user, query=query, limit=limit, offset=offset)


@router.get("/lookup", response_model=LookupResult)
def lookup_patient(
    hospital_number: str = Query(min_length=1, max_length=64),
    session: Session = Depends(get_session),
    user: User = Depends(require_identity_reader),
) -> dict:
    return service.lookup_patient(session, user, hospital_number)


@router.get("/{patient_id}", response_model=PatientDetail)
def get_patient(
    patient_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(require_patient_owner),
) -> dict:
    patient = session.get(Patient, patient_id)
    assert patient is not None  # require_patient_owner already resolved it
    return service.patient_detail(session, user, patient)


@router.patch("/{patient_id}", response_model=PatientDetail)
def update_patient(
    patient_id: str,
    payload: PatientUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(require_patient_owner),
) -> dict:
    patient = session.get(Patient, patient_id)
    assert patient is not None
    service.update_patient(session, user, patient, payload)
    session.commit()
    return service.patient_detail(session, user, patient, audit=False)
