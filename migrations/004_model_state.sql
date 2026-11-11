-- Model approvals are governed by an append-only decision log; the registry
-- remains the source of model metadata, but approval state is projected from
-- model_approvals into model_versions so the existing selector keeps working.

CREATE TABLE model_approvals (
    id VARCHAR(64) NOT NULL,
    model_id VARCHAR(80) NOT NULL,
    version VARCHAR(40) NOT NULL,
    decision VARCHAR(20) NOT NULL,
    decided_by VARCHAR(64) NOT NULL,
    decided_at VARCHAR(32) NOT NULL,
    note TEXT,
    benchmark_digest VARCHAR(64),
    PRIMARY KEY (id),
    FOREIGN KEY(decided_by) REFERENCES users (id)
);

CREATE INDEX ix_approvals_model ON model_approvals (model_id, version, decided_at);

ALTER TABLE model_versions ADD COLUMN approved_by VARCHAR(64) REFERENCES users (id);
ALTER TABLE model_versions ADD COLUMN approved_at VARCHAR(32);
ALTER TABLE model_versions ADD COLUMN state_source VARCHAR(20) NOT NULL DEFAULT 'registry';
