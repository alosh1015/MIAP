from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, LargeBinary, REAL, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    identity_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    identity_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    hospital_index: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


Index("ix_patients_owner", Patient.owner_id, Patient.created_at)
Index("uq_patients_owner_hospital", Patient.owner_id, Patient.hospital_index, unique=True)


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    pseudonym: Mapped[str] = mapped_column(String(120), nullable=False)
    consent: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    patient_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("patients.id"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="created")
    modality: Mapped[str | None] = mapped_column(String(20))
    retention_until: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


Index("ix_cases_patient", Case.patient_id)


class Image(Base):
    __tablename__ = "images"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("cases.id"), nullable=False)
    blob_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    original_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    mime: Mapped[str] = mapped_column(String(80), nullable=False)
    modality: Mapped[str | None] = mapped_column(String(20))
    laterality: Mapped[str | None] = mapped_column(String(4))
    view: Mapped[str | None] = mapped_column(String(8))
    body_part: Mapped[str | None] = mapped_column(String(40))
    body_part_raw: Mapped[str | None] = mapped_column(String(64))
    rows: Mapped[int | None] = mapped_column(Integer)
    cols: Mapped[int | None] = mapped_column(Integer)
    photometric: Mapped[str | None] = mapped_column(String(24))
    validation_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    deid_receipt_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


Index("ix_images_case", Image.case_id)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("cases.id"), nullable=False)
    image_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("images.id"))
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="created")
    progress: Mapped[float] = mapped_column(REAL, nullable=False, default=0.0)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
    batch_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("analysis_batches.id"))
    model_id: Mapped[str | None] = mapped_column(String(80))
    model_version: Mapped[str | None] = mapped_column(String(40))
    params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_detail: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


Index("ix_jobs_state", Job.state)
Index("ix_jobs_batch", Job.batch_id)


class Result(Base):
    __tablename__ = "results"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("jobs.id"), unique=True, nullable=False)
    image_id: Mapped[str] = mapped_column(String(64), ForeignKey("images.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("cases.id"), nullable=False)
    document_json: Mapped[str] = mapped_column(Text, nullable=False)
    heatmap_npy_path: Mapped[str | None] = mapped_column(Text)
    heatmap_png_path: Mapped[str | None] = mapped_column(Text)
    model_digest: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class Provenance(Base):
    __tablename__ = "provenance"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    result_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("results.id"), unique=True, nullable=False
    )
    record_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


class ResultHeatmap(Base):
    __tablename__ = "result_heatmaps"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    result_id: Mapped[str] = mapped_column(String(64), ForeignKey("results.id"), nullable=False)
    finding_index: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    npy_path: Mapped[str] = mapped_column(Text, nullable=False)
    png_path: Mapped[str] = mapped_column(Text, nullable=False)
    shape_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


Index("uq_heatmaps_result_finding", ResultHeatmap.result_id, ResultHeatmap.finding_index, unique=True)


class ImageAnnotation(Base):
    __tablename__ = "image_annotations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("cases.id"), nullable=False)
    image_id: Mapped[str] = mapped_column(String(64), ForeignKey("images.id"), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    points_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


Index("ix_annotations_image", ImageAnnotation.image_id, ImageAnnotation.created_at)


class FindingReview(Base):
    __tablename__ = "finding_reviews"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    result_id: Mapped[str] = mapped_column(String(64), ForeignKey("results.id"), nullable=False)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("cases.id"), nullable=False)
    finding_index: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    note_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    note_nonce: Mapped[bytes | None] = mapped_column(LargeBinary)
    note_key_version: Mapped[int | None] = mapped_column(Integer)
    has_note: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reviewer_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


Index("uq_reviews_result_finding", FindingReview.result_id, FindingReview.finding_index, unique=True)
Index("ix_reviews_case", FindingReview.case_id)


class AnalysisBatch(Base):
    __tablename__ = "analysis_batches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str] = mapped_column(String(64), ForeignKey("cases.id"), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    model_id: Mapped[str] = mapped_column(String(80), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


Index("ix_batches_case", AnalysisBatch.case_id)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    ts: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(40))
    resource_id: Mapped[str | None] = mapped_column(String(64))
    detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    model_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    version: Mapped[str] = mapped_column(String(40), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    task: Mapped[str] = mapped_column(String(40), nullable=False)
    modalities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    card_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    approved_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id"))
    approved_at: Mapped[str | None] = mapped_column(String(32))
    state_source: Mapped[str] = mapped_column(String(20), nullable=False, default="registry")


class ModelApproval(Base):
    __tablename__ = "model_approvals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(80), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    decided_by: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    decided_at: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    benchmark_digest: Mapped[str | None] = mapped_column(String(64))


Index("ix_approvals_model", ModelApproval.model_id, ModelApproval.version, ModelApproval.decided_at)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    case_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("cases.id"))
    path: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    audience: Mapped[str] = mapped_column(String(20), nullable=False, default="legacy")
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="case")
    result_id: Mapped[str | None] = mapped_column(String(64))
    sha256: Mapped[str | None] = mapped_column(String(64))
    template_version: Mapped[str | None] = mapped_column(String(20))
    title: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[str] = mapped_column(String(32), nullable=False)


Index("ix_reports_audience", Report.audience)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(64))
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)


class UserPref(Base):
    __tablename__ = "user_prefs"

    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), primary_key=True)
    prefs_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[str] = mapped_column(String(32), nullable=False)
