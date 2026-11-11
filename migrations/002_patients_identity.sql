-- Patient identity is stored out-of-band from the pixels: the encrypted
-- envelope never travels through ingestion, de-identification, or inference.
-- The pseudonym on the case remains the research key.

CREATE TABLE patients (
    id VARCHAR(64) NOT NULL,
    owner_id VARCHAR(64) NOT NULL,
    identity_ciphertext BLOB NOT NULL,
    identity_nonce BLOB NOT NULL,
    key_version INTEGER NOT NULL,
    hospital_index VARCHAR(64) NOT NULL,
    created_at VARCHAR(32) NOT NULL,
    updated_at VARCHAR(32) NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(owner_id) REFERENCES users (id)
);

CREATE INDEX ix_patients_owner ON patients (owner_id, created_at);
CREATE UNIQUE INDEX uq_patients_owner_hospital ON patients (owner_id, hospital_index);

ALTER TABLE cases ADD COLUMN patient_id VARCHAR(64) REFERENCES patients (id);

CREATE INDEX ix_cases_patient ON cases (patient_id);
