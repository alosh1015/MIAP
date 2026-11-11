-- Baseline snapshot of the MIAP schema as shipped in the MVP (2026-11-10).
-- Existing databases stamp this version without executing it; fresh databases
-- execute it before the later numbered migrations.

CREATE TABLE users (
    id VARCHAR(64) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash TEXT NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    role VARCHAR(20) NOT NULL,
    is_active INTEGER NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (email)
);

CREATE TABLE cases (
    id VARCHAR(64) NOT NULL,
    pseudonym VARCHAR(120) NOT NULL,
    consent VARCHAR(20) NOT NULL,
    created_by VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL,
    modality VARCHAR(20),
    retention_until VARCHAR(32),
    created_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(created_by) REFERENCES users (id)
);

CREATE TABLE images (
    id VARCHAR(64) NOT NULL,
    case_id VARCHAR(64) NOT NULL,
    blob_digest VARCHAR(64) NOT NULL,
    original_digest VARCHAR(64) NOT NULL,
    mime VARCHAR(80) NOT NULL,
    modality VARCHAR(20),
    laterality VARCHAR(4),
    "view" VARCHAR(8),
    body_part VARCHAR(40),
    body_part_raw VARCHAR(64),
    rows INTEGER,
    cols INTEGER,
    photometric VARCHAR(24),
    validation_json TEXT NOT NULL,
    deid_receipt_json TEXT NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE INDEX ix_images_case ON images (case_id);

CREATE TABLE jobs (
    id VARCHAR(64) NOT NULL,
    case_id VARCHAR(64) NOT NULL,
    image_id VARCHAR(64),
    state VARCHAR(20) NOT NULL,
    progress REAL NOT NULL,
    idempotency_key VARCHAR(128),
    model_id VARCHAR(80),
    model_version VARCHAR(40),
    params_json TEXT NOT NULL,
    attempts INTEGER NOT NULL,
    error_code VARCHAR(80),
    error_detail TEXT,
    requested_by VARCHAR(64) NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(case_id) REFERENCES cases (id),
    FOREIGN KEY(image_id) REFERENCES images (id),
    UNIQUE (idempotency_key),
    FOREIGN KEY(requested_by) REFERENCES users (id)
);

CREATE INDEX ix_jobs_state ON jobs (state);

CREATE TABLE results (
    id VARCHAR(64) NOT NULL,
    job_id VARCHAR(64) NOT NULL,
    image_id VARCHAR(64) NOT NULL,
    case_id VARCHAR(64) NOT NULL,
    document_json TEXT NOT NULL,
    heatmap_npy_path TEXT,
    heatmap_png_path TEXT,
    model_digest VARCHAR(64),
    created_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (job_id),
    FOREIGN KEY(job_id) REFERENCES jobs (id),
    FOREIGN KEY(image_id) REFERENCES images (id),
    FOREIGN KEY(case_id) REFERENCES cases (id)
);

CREATE TABLE provenance (
    id VARCHAR(64) NOT NULL,
    result_id VARCHAR(64) NOT NULL,
    record_json TEXT NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (result_id),
    FOREIGN KEY(result_id) REFERENCES results (id)
);

CREATE TABLE audit_events (
    seq INTEGER NOT NULL,
    event_id VARCHAR(64) NOT NULL,
    ts VARCHAR(32) NOT NULL,
    actor_id VARCHAR(64),
    action VARCHAR(80) NOT NULL,
    resource_type VARCHAR(40),
    resource_id VARCHAR(64),
    detail_json TEXT NOT NULL,
    prev_hash VARCHAR(64) NOT NULL,
    hash VARCHAR(64) NOT NULL,
    PRIMARY KEY (seq),
    UNIQUE (event_id)
);

CREATE TABLE model_versions (
    model_id VARCHAR(80) NOT NULL,
    version VARCHAR(40) NOT NULL,
    digest VARCHAR(64) NOT NULL,
    state VARCHAR(20) NOT NULL,
    task VARCHAR(40) NOT NULL,
    modalities_json TEXT NOT NULL,
    card_json TEXT NOT NULL,
    PRIMARY KEY (model_id, version)
);

CREATE TABLE reports (
    id VARCHAR(64) NOT NULL,
    case_id VARCHAR(64) NOT NULL,
    path TEXT NOT NULL,
    created_by VARCHAR(64) NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(case_id) REFERENCES cases (id),
    FOREIGN KEY(created_by) REFERENCES users (id)
);
