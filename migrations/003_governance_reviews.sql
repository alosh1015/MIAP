-- Clinician review, per-finding heatmaps, batch analyses, and role-scoped
-- reports. Review notes are encrypted because they may contain identifiers.

CREATE TABLE finding_reviews (
    id VARCHAR(64) NOT NULL,
    result_id VARCHAR(64) NOT NULL,
    case_id VARCHAR(64) NOT NULL,
    finding_index INTEGER NOT NULL,
    decision VARCHAR(20) NOT NULL,
    note_ciphertext BLOB,
    note_nonce BLOB,
    note_key_version INTEGER,
    has_note INTEGER NOT NULL DEFAULT 0,
    reviewer_id VARCHAR(64) NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(result_id) REFERENCES results (id),
    FOREIGN KEY(case_id) REFERENCES cases (id),
    FOREIGN KEY(reviewer_id) REFERENCES users (id)
);

CREATE UNIQUE INDEX uq_reviews_result_finding ON finding_reviews (result_id, finding_index);
CREATE INDEX ix_reviews_case ON finding_reviews (case_id);

CREATE TABLE result_heatmaps (
    id VARCHAR(64) NOT NULL,
    result_id VARCHAR(64) NOT NULL,
    finding_index INTEGER NOT NULL,
    label VARCHAR(160) NOT NULL,
    npy_path TEXT NOT NULL,
    png_path TEXT NOT NULL,
    shape_json TEXT NOT NULL DEFAULT '[]',
    created_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(result_id) REFERENCES results (id)
);

CREATE UNIQUE INDEX uq_heatmaps_result_finding ON result_heatmaps (result_id, finding_index);

CREATE TABLE analysis_batches (
    id VARCHAR(64) NOT NULL,
    case_id VARCHAR(64) NOT NULL,
    requested_by VARCHAR(64) NOT NULL,
    model_id VARCHAR(80) NOT NULL,
    model_version VARCHAR(40),
    state VARCHAR(20) NOT NULL DEFAULT 'queued',
    total INTEGER NOT NULL DEFAULT 0,
    completed INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(case_id) REFERENCES cases (id),
    FOREIGN KEY(requested_by) REFERENCES users (id)
);

CREATE INDEX ix_batches_case ON analysis_batches (case_id);

ALTER TABLE jobs ADD COLUMN batch_id VARCHAR(64) REFERENCES analysis_batches (id);

CREATE INDEX ix_jobs_batch ON jobs (batch_id);

ALTER TABLE reports ADD COLUMN audience VARCHAR(20) NOT NULL DEFAULT 'legacy';
ALTER TABLE reports ADD COLUMN kind VARCHAR(20) NOT NULL DEFAULT 'case';
ALTER TABLE reports ADD COLUMN result_id VARCHAR(64);
ALTER TABLE reports ADD COLUMN sha256 VARCHAR(64);
ALTER TABLE reports ADD COLUMN template_version VARCHAR(20);
ALTER TABLE reports ADD COLUMN title VARCHAR(200);

CREATE INDEX ix_reports_audience ON reports (audience);

CREATE TABLE app_settings (
    key VARCHAR(80) NOT NULL,
    value_json TEXT NOT NULL,
    updated_by VARCHAR(64),
    updated_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (key)
);

CREATE TABLE user_prefs (
    user_id VARCHAR(64) NOT NULL,
    prefs_json TEXT NOT NULL DEFAULT '{}',
    updated_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (user_id),
    FOREIGN KEY(user_id) REFERENCES users (id)
);
