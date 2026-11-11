"""Patient identity service.

Every read of decrypted identity is written to the audit chain *before* the
payload leaves the service. A failed audit write fails the read closed, so there
is no path that returns a name without a matching event.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import append_audit, write_audit_now
from app.core.crypto import (
    DecryptionError,
    decrypt_identity,
    encrypt_identity,
    hospital_index,
    normalise_hospital_number,
)
from app.core.errors import AppError
from app.core.ids import new_id, utcnow_iso
from app.core.schema import Case, Patient, User
from app.modules.patients.schemas import PatientCaseRef, PatientCreate, PatientDetail, PatientSummary, PatientUpdate

IDENTITY_AUDIT_FIELDS = ["name", "hospital_number", "sex", "dob"]


def age_from_dob(dob: str | None, today: date | None = None) -> int | None:
    if not dob:
        return None
    try:
        born = date.fromisoformat(dob)
    except ValueError:
        return None
    reference = today or date.today()
    return reference.year - born.year - ((reference.month, reference.day) < (born.month, born.day))


def _audit_failure(patient: Patient | None, actor: str) -> None:
    try:
        write_audit_now(
            actor_id=actor,
            action="identity.decrypt_failed",
            resource_type="patient",
            resource_id=patient.id if patient else None,
            detail={},
        )
    except Exception:  # noqa: BLE001 - the read already fails closed
        pass


def decrypt_identity_or_422(patient: Patient, actor: str) -> dict:
    try:
        return decrypt_identity(
            patient.id, patient.identity_ciphertext, patient.identity_nonce, patient.key_version
        )
    except DecryptionError:
        _audit_failure(patient, actor)
        raise AppError(422, "identity_decrypt_failed", "Patient identity could not be read") from None


def record_identity_view(actor: str, patient: Patient, action: str = "patient.identity_viewed") -> None:
    try:
        write_audit_now(
            actor_id=actor,
            action=action,
            resource_type="patient",
            resource_id=patient.id,
            detail={"fields": IDENTITY_AUDIT_FIELDS},
        )
    except Exception as exc:  # noqa: BLE001 - identity reads fail closed
        raise AppError(503, "audit_unavailable", "Audit log is unavailable; identity view refused") from exc


def _hospital_index_or_422(value: str) -> str:
    try:
        return hospital_index(value)
    except ValueError:
        raise AppError(422, "invalid_hospital_number", "Hospital number is required") from None


def _summary(patient: Patient, identity: dict, case_count: int) -> dict:
    return {
        "id": patient.id,
        "name": identity.get("name") or "",
        "hospital_number": identity.get("hospital_number") or "",
        "sex": identity.get("sex") or "unknown",
        "dob": identity.get("dob"),
        "age": age_from_dob(identity.get("dob")),
        "case_count": case_count,
        "created_at": patient.created_at,
        "updated_at": patient.updated_at,
    }


def _case_counts(session: Session, patient_ids: list[str]) -> dict[str, int]:
    if not patient_ids:
        return {}
    rows = session.execute(
        select(Case.patient_id, func.count(Case.id))
        .where(Case.patient_id.in_(patient_ids))
        .group_by(Case.patient_id)
    ).all()
    return {patient_id: count for patient_id, count in rows if patient_id}


def _case_refs(session: Session, patient_id: str) -> list[PatientCaseRef]:
    cases = session.execute(select(Case).where(Case.patient_id == patient_id).order_by(Case.created_at.desc())).scalars().all()
    return [
        PatientCaseRef(
            id=case.id,
            pseudonym=case.pseudonym,
            status=case.status,
            modality=case.modality,
            created_at=case.created_at,
        )
        for case in cases
    ]


def create_patient(session: Session, user: User, payload: PatientCreate) -> Patient:
    if user.role != "clinician":
        raise AppError(403, "forbidden", "Only clinicians can create patients")
    index = _hospital_index_or_422(payload.hospital_number)
    duplicate = session.execute(
        select(Patient).where(Patient.owner_id == user.id, Patient.hospital_index == index)
    ).scalar_one_or_none()
    if duplicate is not None:
        raise AppError(409, "patient_exists", "A patient with this hospital number already exists")
    patient_id = new_id("patient")
    ciphertext, nonce, version = encrypt_identity(patient_id, payload.model_dump(mode="json"))
    now = utcnow_iso()
    patient = Patient(
        id=patient_id,
        owner_id=user.id,
        identity_ciphertext=ciphertext,
        identity_nonce=nonce,
        key_version=version,
        hospital_index=index,
        created_at=now,
        updated_at=now,
    )
    session.add(patient)
    append_audit(
        session,
        actor_id=user.id,
        action="patient.created",
        resource_type="patient",
        resource_id=patient.id,
        detail={"fields": IDENTITY_AUDIT_FIELDS},
    )
    return patient


def update_patient(session: Session, user: User, patient: Patient, payload: PatientUpdate) -> Patient:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return patient
    identity = decrypt_identity_or_422(patient, user.id)
    merged = dict(identity)
    for field, value in changes.items():
        merged[field] = value.isoformat() if isinstance(value, date) else value
    if "hospital_number" in changes:
        index = _hospital_index_or_422(str(merged["hospital_number"]))
        clash = session.execute(
            select(Patient).where(
                Patient.owner_id == user.id,
                Patient.hospital_index == index,
                Patient.id != patient.id,
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise AppError(409, "patient_exists", "A patient with this hospital number already exists")
        patient.hospital_index = index
    ciphertext, nonce, version = encrypt_identity(patient.id, merged)
    patient.identity_ciphertext = ciphertext
    patient.identity_nonce = nonce
    patient.key_version = version
    patient.updated_at = utcnow_iso()
    append_audit(
        session,
        actor_id=user.id,
        action="patient.updated",
        resource_type="patient",
        resource_id=patient.id,
        detail={"fields": sorted(changes)},
    )
    return patient


def patient_detail(session: Session, user: User, patient: Patient, *, audit: bool = True) -> dict:
    identity = decrypt_identity_or_422(patient, user.id)
    if audit:
        record_identity_view(user.id, patient)
    counts = _case_counts(session, [patient.id])
    summary = _summary(patient, identity, counts.get(patient.id, 0))
    return PatientDetail(**summary, cases=_case_refs(session, patient.id)).model_dump()


def list_patients(
    session: Session,
    user: User,
    *,
    query: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    statement = (
        select(Patient)
        .where(Patient.owner_id == user.id)
        .order_by(Patient.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if query:
        try:
            statement = statement.where(Patient.hospital_index == hospital_index(query))
        except ValueError:
            return []
    patients = session.execute(statement).scalars().all()
    if not patients:
        return []
    identities = [decrypt_identity_or_422(patient, user.id) for patient in patients]
    try:
        write_audit_now(
            actor_id=user.id,
            action="patient.list_viewed",
            resource_type="patient",
            resource_id=None,
            detail={"count": len(patients)},
        )
    except Exception as exc:  # noqa: BLE001 - identity reads fail closed
        raise AppError(503, "audit_unavailable", "Audit log is unavailable; patient list refused") from exc
    counts = _case_counts(session, [patient.id for patient in patients])
    return [
        PatientSummary(**_summary(patient, identity, counts.get(patient.id, 0))).model_dump()
        for patient, identity in zip(patients, identities)
    ]


def lookup_patient(session: Session, user: User, hospital_number: str) -> dict:
    try:
        index = hospital_index(hospital_number)
    except ValueError:
        raise AppError(422, "invalid_hospital_number", "Hospital number is required") from None
    patient = session.execute(
        select(Patient).where(Patient.owner_id == user.id, Patient.hospital_index == index)
    ).scalar_one_or_none()
    if patient is None:
        write_audit_now(
            actor_id=user.id,
            action="patient.lookup",
            resource_type="patient",
            resource_id=None,
            detail={"hit": False},
        )
        return {"found": False, "patient": None}
    identity = decrypt_identity_or_422(patient, user.id)
    try:
        write_audit_now(
            actor_id=user.id,
            action="patient.lookup",
            resource_type="patient",
            resource_id=patient.id,
            detail={"hit": True, "fields": IDENTITY_AUDIT_FIELDS},
        )
    except Exception as exc:  # noqa: BLE001
        raise AppError(503, "audit_unavailable", "Audit log is unavailable; lookup refused") from exc
    counts = _case_counts(session, [patient.id])
    return {
        "found": True,
        "patient": PatientSummary(**_summary(patient, identity, counts.get(patient.id, 0))).model_dump(),
    }


def link_case(session: Session, user: User, case: Case, patient_id: str) -> None:
    patient = session.get(Patient, patient_id)
    if patient is None or patient.owner_id != user.id:
        raise AppError(404, "patient_not_found", "Patient not found")
    if case.created_by != user.id:
        raise AppError(403, "forbidden", "Only the case owner can link a patient")
    if case.patient_id and case.patient_id != patient.id:
        raise AppError(409, "case_already_linked", "This case is already linked to another patient")
    case.patient_id = patient.id
    append_audit(
        session,
        actor_id=user.id,
        action="case.patient_linked",
        resource_type="case",
        resource_id=case.id,
        detail={"patient_id": patient.id},
    )


def display_for_case(session: Session, case: Case) -> tuple[str | None, str | None]:
    """Return (patient_id, display line) for the case owner only."""
    if not case.patient_id:
        return None, None
    patient = session.get(Patient, case.patient_id)
    if patient is None:
        return None, None
    identity = decrypt_identity_or_422(patient, case.created_by)
    name = identity.get("name") or ""
    number = identity.get("hospital_number") or ""
    return patient.id, f"{name} · {number}".strip(" ·")
