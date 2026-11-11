# ADR-016: Numbered SQL migrations and an encrypted identity layer

- Status: Accepted
- Date: 2026-11-10
- Supersedes: nothing.
- Context: The MVP schema was created with `Base.metadata.create_all`, which
  cannot add columns to an existing SQLite database. The foundation phase adds
  patient identity, finding reviews, per-finding heatmaps, analysis batches,
  model approvals, report audiences and settings. Two questions had to be
  answered together: how schema changes reach an existing deployment, and how
  clinical identity coexists with mandatory image de-identification.

## Decision 1 — Numbered SQL files, not Alembic

A small runner (`backend/app/core/migrations.py`) applies
`migrations/NNN_*.sql` in version order before `create_all` on startup.

- `schema_migrations(version PK, applied_at, checksum)` records what ran.
- A database created before the runner is **baselined**: if `users` exists and
  `schema_migrations` is empty, version 1 is stamped with the SHA-256 of the
  reviewed `001_init.sql` snapshot, without executing it.
- Each file runs in one transaction with `PRAGMA foreign_keys=OFF`, followed by
  `PRAGMA foreign_key_check`; the transaction commits only if the check passes.
- A checksum mismatch refuses startup and names the file, so an edited migration
  is never silently applied.
- Re-running is a no-op. `scripts/migrate.py --dry-run --db <copy>` rehearses on
  a copy, including the `-wal`/`-shm` files.

Alembic was rejected for this cycle: it adds a dependency, autogenerate and a
second source of truth (models plus migration scripts) for a single-node SQLite
schema with six migrations. The SQL files are reviewable diffs, and the
independent verifier `scripts/verify_audit.py` already assumes plain SQL access.
Moving to Alembic or PostgreSQL remains possible because migrations are
numbered and append-only.

## Decision 2 — Identity is an out-of-band encrypted record

Patient identity is **not** stored in DICOM tags and is never derived from
pixels. A `patients` row holds:

- one AES-256-GCM ciphertext of canonical JSON `{name, hospital_number, sex,
  dob}`, with additional authenticated data `patient:{id}:v{version}` so a
  ciphertext moved to another row fails to decrypt;
- the nonce and key version;
- an HMAC-SHA256 blind index of the normalised hospital number, computed with a
  key derived from a separate `MIAP_PII_INDEX_KEY`, for exact-match lookup only.

Review notes use the same envelope with AAD `review:{id}` because free-text
notes can contain identifiers.

Access rules:

- Only the **clinician owner of the case** sees identity. Researchers and
  administrators see the pseudonym; administrators remain denied on every image,
  result, heatmap and report route.
- Every identity read writes `patient.identity_viewed` through
  `write_audit_now` (own session, `BEGIN IMMEDIATE`) **before** the payload is
  returned. A failed audit write fails the read closed with `503`; a failed
  decryption returns `422 identity_decrypt_failed` with no detail.
- Audit details contain IDs, field names and counts — never values. Decrypted
  values are never logged.

## Consequences

- The image de-identification guarantee is unchanged: original bytes are
  discarded and the UID remapping key is not retained. Deleting the patient row
  leaves no image→person path.
- The app refuses to start without `MIAP_PII_KEY`; tests set fixed keys in
  `conftest.py`. `scripts/gen_keys.py` writes a fresh pair to the gitignored
  `backend/.env`. `scripts/rotate_pii.py --to N` re-encrypts in batches while
  older versions stay readable through `MIAP_PII_KEYS`, auditing counts only.
- Governance decisions live in `model_approvals` and are projected onto
  `model_versions.state` with `state_source='approval'`. Re-seeding the registry
  updates digests, task, modalities and cards but **never** overwrites a state,
  so an approval survives a restart.
- Identity remains special personal data under Uganda's Data Protection and
  Privacy Act, 2019. A documented lawful basis, retention decision and ethics
  approval are prerequisites for real patients; until then the system is used
  with synthetic or demonstration data.
- The audit chain's `BEGIN IMMEDIATE` closes the cross-session fork window, but
  the design still assumes a single API process. Multi-process deployments need
  an outbox or a database-level append primitive; this is recorded as deferred.
