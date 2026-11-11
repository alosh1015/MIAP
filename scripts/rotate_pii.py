"""Re-encrypt patient identity and review notes under a new key version.

Prepare the two keys first:
  * ``MIAP_PII_KEY`` must hold the NEW key and ``MIAP_PII_KEY_VERSION`` the new
    version number.
  * ``MIAP_PII_KEYS`` must be a JSON map of {old_version: old_base64_key}.

    python scripts/rotate_pii.py --to 2 --batch-size 100
    python scripts/rotate_pii.py --to 2 --dry-run

Only counts are written to the audit chain; no identity value is logged.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from sqlalchemy import select  # noqa: E402

from app.core.audit import append_audit  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.crypto import decrypt_identity, decrypt_note, encrypt_identity, encrypt_note  # noqa: E402
from app.core.db import SessionLocal, init_db  # noqa: E402
from app.core.schema import FindingReview, Patient  # noqa: E402


def rotate(*, to_version: int, batch_size: int, dry_run: bool) -> tuple[int, int]:
    settings = get_settings()
    if settings.pii_key_version != to_version:
        raise SystemExit(
            f"MIAP_PII_KEY_VERSION is {settings.pii_key_version}, expected {to_version}"
        )
    init_db()
    assert SessionLocal is not None
    patients_done = 0
    reviews_done = 0
    with SessionLocal() as session:
        offset = 0
        while True:
            rows = (
                session.execute(select(Patient).order_by(Patient.id).offset(offset).limit(batch_size))
                .scalars()
                .all()
            )
            if not rows:
                break
            for patient in rows:
                if patient.key_version == to_version:
                    continue
                identity = decrypt_identity(
                    patient.id,
                    patient.identity_ciphertext,
                    patient.identity_nonce,
                    patient.key_version,
                )
                ciphertext, nonce, version = encrypt_identity(patient.id, identity)
                if not dry_run:
                    patient.identity_ciphertext = ciphertext
                    patient.identity_nonce = nonce
                    patient.key_version = version
                patients_done += 1
            offset += len(rows)
            if not dry_run:
                session.commit()
        offset = 0
        while True:
            rows = (
                session.execute(
                    select(FindingReview).order_by(FindingReview.id).offset(offset).limit(batch_size)
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for review in rows:
                if not review.has_note or review.note_ciphertext is None or review.note_nonce is None:
                    continue
                if review.note_key_version == to_version:
                    continue
                note = decrypt_note(
                    review.id,
                    review.note_ciphertext,
                    review.note_nonce,
                    review.note_key_version or 1,
                )
                ciphertext, nonce, version = encrypt_note(review.id, note)
                if not dry_run:
                    review.note_ciphertext = ciphertext
                    review.note_nonce = nonce
                    review.note_key_version = version
                reviews_done += 1
            offset += len(rows)
            if not dry_run:
                session.commit()
        if not dry_run:
            append_audit(
                session,
                actor_id=None,
                action="pii.rotated",
                resource_type="system",
                resource_id=None,
                detail={"to_version": to_version, "patients": patients_done, "reviews": reviews_done},
            )
            session.commit()
    return patients_done, reviews_done


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Rotate MIAP PII keys")
    parser.add_argument("--to", type=int, default=settings.pii_key_version)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    patients, reviews = rotate(
        to_version=args.to, batch_size=args.batch_size, dry_run=args.dry_run
    )
    prefix = "would rotate" if args.dry_run else "rotated"
    print(f"{prefix} {patients} patient record(s) and {reviews} review note(s) to v{args.to}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
