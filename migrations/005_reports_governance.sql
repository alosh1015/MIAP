-- Governance reports are not case-scoped. SQLite cannot drop NOT NULL in
-- place, so rebuild the table while preserving every existing row.
CREATE TABLE reports_new (
    id VARCHAR(64) NOT NULL,
    case_id VARCHAR(64),
    path TEXT NOT NULL,
    created_by VARCHAR(64) NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    audience VARCHAR(20) NOT NULL DEFAULT 'legacy',
    kind VARCHAR(20) NOT NULL DEFAULT 'case',
    result_id VARCHAR(64),
    sha256 VARCHAR(64),
    template_version VARCHAR(20),
    title VARCHAR(200),
    PRIMARY KEY (id),
    FOREIGN KEY(case_id) REFERENCES cases (id),
    FOREIGN KEY(created_by) REFERENCES users (id)
);

INSERT INTO reports_new (id, case_id, path, created_by, created_at, audience, kind, result_id, sha256, template_version, title)
SELECT id, case_id, path, created_by, created_at, audience, kind, result_id, sha256, template_version, title
FROM reports;

DROP TABLE reports;
ALTER TABLE reports_new RENAME TO reports;

CREATE INDEX ix_reports_audience ON reports (audience);
