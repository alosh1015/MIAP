"""Confirm/dismiss decisions on AI findings.

The decision is clinical judgement recorded against a specific finding index in
an immutable result document. Notes are encrypted with the same envelope as
patient identity and are returned to the case owner only; researchers see
aggregate counts.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import append_audit, write_audit_now
from app.core.crypto import DecryptionError, decrypt_note, encrypt_note
from app.core.errors import AppError
from app.core.ids import new_id, utcnow_iso
from app.core.schema import Case, FindingReview, Result, User
from app.modules.results.presenter import band_for, is_localisable
from app.modules.reviews.schemas import ReviewOut, ReviewRequest, ReviewSummary


def _result_for(session: Session, user: User, result_id: str) -> tuple[Result, Case]:
    result = session.get(Result, result_id)
    if result is None:
        raise AppError(404, "result_not_found", "Result not found")
    case = session.get(Case, result.case_id)
    if case is None:
        raise AppError(404, "result_not_found", "Result not found")
    if user.role == "clinician" and case.created_by == user.id:
        return result, case
    if user.role == "researcher" and (case.created_by == user.id or case.consent == "research"):
        return result, case
    raise AppError(404, "result_not_found", "Result not found")


def _finding_count(session: Session, result: Result) -> int:
    return len(json.loads(result.document_json or "{}").get("findings") or [])


def _note_cipher(review_id: str, note: str | None) -> tuple[bytes | None, bytes | None, int | None, int]:
    if not note:
        return None, None, None, 0
    ciphertext, nonce, version = encrypt_note(review_id, note)
    return ciphertext, nonce, version, 1


def upsert_review(
    session: Session, user: User, result_id: str, finding_index: int, payload: ReviewRequest
) -> FindingReview:
    result, case = _result_for(session, user, result_id)
    if case.created_by != user.id:
        raise AppError(403, "forbidden", "Only the treating clinician can review findings")
    total = _finding_count(session, result)
    if finding_index < 0 or finding_index >= total:
        raise AppError(404, "finding_not_found", "Finding not found")

    existing = session.execute(
        select(FindingReview).where(
            FindingReview.result_id == result_id, FindingReview.finding_index == finding_index
        )
    ).scalar_one_or_none()
    now = utcnow_iso()
    if existing is None:
        review_id = new_id("review")
        ciphertext, nonce, version, has_note = _note_cipher(review_id, payload.note)
        review = FindingReview(
            id=review_id,
            result_id=result_id,
            case_id=case.id,
            finding_index=finding_index,
            decision=payload.decision,
            note_ciphertext=ciphertext,
            note_nonce=nonce,
            note_key_version=version,
            has_note=has_note,
            reviewer_id=user.id,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        session.add(review)
        action = "finding.reviewed"
    else:
        review = existing
        review.decision = payload.decision
        review.reviewer_id = user.id
        review.revision += 1
        review.updated_at = now
        if payload.note is not None:
            ciphertext, nonce, version, has_note = _note_cipher(review.id, payload.note)
            review.note_ciphertext = ciphertext
            review.note_nonce = nonce
            review.note_key_version = version
            review.has_note = has_note
        action = "finding.review_changed"
    append_audit(
        session,
        actor_id=user.id,
        action=action,
        resource_type="finding_review",
        resource_id=review.id,
        detail={
            "result_id": result_id,
            "case_id": case.id,
            "finding_index": finding_index,
            "decision": payload.decision,
            "has_note": bool(review.has_note),
            "revision": review.revision,
        },
    )
    return review


def _decrypt_note(review: FindingReview, actor: str) -> str | None:
    if not review.has_note or review.note_ciphertext is None or review.note_nonce is None:
        return None
    try:
        return decrypt_note(
            review.id, review.note_ciphertext, review.note_nonce, review.note_key_version or 1
        )
    except DecryptionError:
        try:
            write_audit_now(
                actor_id=actor,
                action="identity.decrypt_failed",
                resource_type="finding_review",
                resource_id=review.id,
                detail={},
            )
        except Exception:  # noqa: BLE001 - fail closed
            pass
        raise AppError(422, "identity_decrypt_failed", "Review note could not be read") from None


def list_reviews(session: Session, user: User, result_id: str) -> ReviewSummary:
    result, case = _result_for(session, user, result_id)
    document = json.loads(result.document_json or "{}")
    findings = document.get("findings") or []
    to_review = sum(
        1
        for finding in findings
        if is_localisable(str(finding.get("label", "")))
        and band_for(float(finding.get("probability", 0.0)), finding.get("threshold"))
        in {"above_threshold", "borderline"}
    )
    reviews = (
        session.execute(
            select(FindingReview)
            .where(FindingReview.result_id == result_id)
            .order_by(FindingReview.finding_index)
        )
        .scalars()
        .all()
    )
    owner = user.role == "clinician" and case.created_by == user.id
    items: list[ReviewOut] = []
    notes_visible = False
    if owner:
        notes = [_decrypt_note(review, user.id) for review in reviews]
        if any(note is not None for note in notes):
            notes_visible = True
            try:
                write_audit_now(
                    actor_id=user.id,
                    action="finding.notes_viewed",
                    resource_type="result",
                    resource_id=result_id,
                    detail={"count": sum(1 for note in notes if note is not None)},
                )
            except Exception as exc:  # noqa: BLE001
                raise AppError(503, "audit_unavailable", "Audit log is unavailable; notes refused") from exc
        items = [
            ReviewOut(
                finding_index=review.finding_index,
                decision=review.decision,
                has_note=bool(review.has_note),
                note=note,
                reviewer_id=review.reviewer_id,
                revision=review.revision,
                created_at=review.created_at,
                updated_at=review.updated_at,
            )
            for review, note in zip(reviews, notes)
        ]
    return ReviewSummary(
        findings_to_review=to_review,
        reviewed=len(reviews),
        confirmed=sum(1 for review in reviews if review.decision == "confirmed"),
        dismissed=sum(1 for review in reviews if review.decision == "dismissed"),
        with_notes=sum(1 for review in reviews if review.has_note),
        items=items,
        notes_visible=notes_visible,
    )


def review_map(
    session: Session, user: User, result: Result, *, include_notes: bool = False
) -> dict[int, dict]:
    reviews = (
        session.execute(select(FindingReview).where(FindingReview.result_id == result.id))
        .scalars()
        .all()
    )
    case = session.get(Case, result.case_id)
    owner = user.role == "clinician" and case is not None and case.created_by == user.id
    mapping: dict[int, dict] = {}
    for review in reviews:
        note = _decrypt_note(review, user.id) if include_notes and owner else None
        mapping[review.finding_index] = {
            "finding_index": review.finding_index,
            "decision": review.decision,
            "has_note": bool(review.has_note),
            "note": note,
            "reviewer_id": review.reviewer_id,
            "revision": review.revision,
            "updated_at": review.updated_at,
        }
    return mapping
