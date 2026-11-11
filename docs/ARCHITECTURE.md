# MIAP architecture

**Medical Image AI Pipeline** — a decision-support pipeline for chest X-rays and
mammogram viewing, built for Mbarara University of Science and Technology.
It is not a diagnostic device and every surface says so.

This document describes the system as built for the MVP cycle that ended
2026-11-10. Scope decisions are recorded in
[ADR-015](adr/ADR-015-mvp-scope.md); milestone evidence is in
[MILESTONES.md](MILESTONES.md).

## Runtime topology

```
Browser (React 19 + Cornerstone3D)
        │  /api/v1/*  (Vite dev proxy or same-origin reverse proxy)
        ▼
FastAPI modular monolith  ──────────────►  SQLite (WAL)   data/miap.db
  auth · patients · cases · ingestion         users, patients, cases, images,
  de-id · routing · inference · results       jobs, results, provenance,
  reviews · reporting · dashboard             reviews, heatmaps, reports,
  settings · users · system                   audit_events, model_versions,
  retention · exports · audit · models        approvals, settings
        │
        ├─► content-addressed blobs   data/blobs/sha256/ab/cd/<sha256>
        ├─► derived artefacts         data/derived/<case>/<image>/heatmap.{npy,png}
        ├─► PDF reports               data/reports/<report_id>.pdf
        └─► in-process CPU worker     ThreadPoolExecutor(max_workers=1)
```

One process serves the API and runs inference. The worker is an `asyncio.Queue`
consumed on a dedicated thread, so a 0.7 s inference cannot block request
handling. On startup the runner re-queues jobs left `queued`/`running`; a job
that was interrupted twice is failed with `interrupted` rather than retried
forever (`backend/app/modules/inference/worker.py`).

## Backend modules

| Module | Responsibility | Key file |
| --- | --- | --- |
| `core` | Settings, DB session, numbered migrations, crypto envelope, JWT/argon2, audit chain, blob store, problem+json | `backend/app/core/` |
| `auth` | Login, current user | `backend/app/modules/auth/` |
| `patients` | Encrypted identity, blind-index lookup, audited identity reads, case linking | `backend/app/modules/patients/` |
| `cases` | Create/list/detail/archive; sorting/filters; AI flags; admin metadata view | `backend/app/modules/cases/` |
| `ingestion` | Upload limit, type sniffing, de-identification, validation, decoded pixels, preview | `backend/app/modules/ingestion/` |
| `deid` | PS3.15 basic-profile subset, UID remapping, raster EXIF strip | `backend/app/modules/deid/` |
| `routing` | Modality and body-region resolution, mammogram four-view grouping | `backend/app/modules/routing/` |
| `preprocessing` | Pixel loading and model input (224×224, centre crop, normalisation) | `backend/app/modules/preprocessing/` |
| `inference` | Capability routing, model selection, job queue, batch and exam jobs, per-model engine adapters, Grad-CAM | `backend/app/modules/inference/` |
| `results` | Immutable result document, v2 presenter, plain language, provenance, heatmap artefacts | `backend/app/modules/results/` |
| `reviews` | Confirm/dismiss findings, encrypted notes, owner-only note reads | `backend/app/modules/reviews/` |
| `reporting` | Audience-aware A4 PDFs (clinician, researcher, governance) rendered from the stored JSON result | `backend/app/modules/reporting/` |
| `dashboard` | Role-specific landing payloads | `backend/app/modules/dashboard/` |
| `settings` | Personal preferences and system settings; capability matrix | `backend/app/modules/settings/` |
| `users` | Administrator user lifecycle | `backend/app/modules/users/` |
| `system` | Health and storage summary | `backend/app/modules/system/` |
| `retention` | Due-study preview and confirmed deletion run | `backend/app/modules/retention/` |
| `exports` | Pseudonymised researcher export | `backend/app/modules/exports/` |
| `audit` | Hash-chained event export and verification | `backend/app/modules/audit/` |
| `models` | Registry, seeded versions, approval history and projection | `backend/app/modules/models/` |

## End-to-end flow

1. **Create a case** (`POST /cases`) with a pseudonym and a consent basis
   (`clinical` or `research`). An audit event is appended.
2. **Upload an image** (`POST /cases/{id}/images`). The server enforces the size
   limit, sniffs the real type, de-identifies, writes the de-identified bytes to
   the blob store, validates the pixels, resolves modality/region/view, and
   records the original digest (not retained) next to the stored digest.
3. **View** (`GET /images/{id}/pixels`). The server decodes with pydicom and
   returns raw little-endian samples plus an `X-MIAP-Meta` JSON header
   (geometry, spacing, rescale, window, photometric). The browser never decodes
   DICOM, so every accepted transfer syntax works in the viewer.
4. **Submit analysis** (`POST /analyses`, `Idempotency-Key` required). The
   routing service maps the de-identified body part and modality to a capability
   bucket (`chest`, `bone_limb`, `bone_hip_pelvis`, `mammogram_density`), then
   picks an approved model that covers it. No approved model → `409
   analysis_not_supported` naming the bucket. Mammograms use `POST
   /analyses/exam`, which queues one job per view. The response is `202`.
5. **Worker** loads the stored (de-identified) pixels, builds the model input
   from the registry's preprocessing profile (`xrv_chest_224`,
   `monai_density_299`, `siglip_bone_224`), predicts, computes the primary
   Grad-CAM, writes the result document, heatmap `.npy`/`.png`, and a provenance
   record, then marks the job `completed`. Other findings' CAMs are computed on
   first request and cached in `result_heatmaps`.
6. **Read results** (`GET /analyses/{job}/result`, `/provenance`,
   `/results/{id}/heatmap.*`). The JSON result is canonical; the PDF is a
   rendering of it. The stored document is immutable and presented on read as
   v2: bands, plain language, per-finding review state and a single
   server-computed `impression` naming the leading pattern (or density
   category, or the absence of a review-band finding) so the workspace and both
   PDF audiences state the same conclusion.
7. **Report** (`POST /reports/{case_id}?job_id=...`) renders an audience-specific
   A4 PDF. Clinicians get identity, plain-language bands, decisions and notes;
   researchers get pseudonymised scores, thresholds, provenance and agreement
   counts; administrators get a separate governance PDF with no patients,
   pixels or findings. The stored JSON result remains canonical.

## Storage layout

```
data/
  miap.db                                   SQLite, WAL mode
  blobs/sha256/34/8f/348f17...c05a0bcf22296577338c592e0bdee2a42dda02e09e0dbfde0d
  derived/<case_id>/<image_id>/heatmap.npy  224×224 or 299×299 float32 (primary)
  derived/<case_id>/<image_id>/heatmap_3.npy per-finding CAM, computed lazily
  derived/<case_id>/<image_id>/heatmap.png  RGBA overlay
  reports/<report_id>.pdf
```

Blobs are immutable and addressed by SHA-256 of the *stored* (de-identified)
bytes, written atomically through a temp file. Paths stored in SQLite are
relative to the data directory and resolved through a guard that rejects
traversal (`resolve_relative`).

## Schema migrations

`Base.metadata.create_all` cannot alter existing tables, so startup applies
numbered SQL files from `migrations/` before `create_all`
(`backend/app/core/migrations.py`). `schema_migrations(version, applied_at,
checksum)` records what ran. A live database created before the runner is
baselined at v1 by stamping the SHA-256 of the reviewed `001_init.sql` snapshot
without re-executing it. Each file runs in one transaction with foreign keys
off, followed by `PRAGMA foreign_key_check`; a checksum mismatch refuses startup
and names the file. Rehearse on a copy with
`python scripts/migrate.py --dry-run --db <copy>`. See
[ADR-016](adr/ADR-016-migrations-and-identity.md).

## Patient identity versus image de-identification

These are deliberately separate systems:

- **Image de-identification** (`deid/`) removes identifiers from pixels and
  headers. The original bytes are discarded and the UID remapping key is not
  retained, so there is no image→person path.
- **Patient identity** is an out-of-band clinical record. A case may reference a
  `patients` row; the row holds one AES-256-GCM ciphertext (canonical JSON with
  name, hospital number, sex and date of birth) bound by AAD to the patient id,
  plus an HMAC-SHA256 blind index of the normalised hospital number for exact
  lookup. The plaintext is never written to SQLite, audit details, logs or
  error messages.
- Only the **clinician owner** of the case may read identity. Researchers and
  administrators see the pseudonym. Deleting the patient row leaves no path
  from the image to a person.

Identity reads are the one deliberate exception to read-only GETs: the audit
event is committed through a dedicated session with `BEGIN IMMEDIATE` **before**
the decrypted payload is returned. If the audit write fails, the read fails
closed (`503`). Decryption failures return `422 identity_decrypt_failed` with no
detail. Key material comes from `MIAP_PII_KEY`, `MIAP_PII_INDEX_KEY` and
`MIAP_PII_KEY_VERSION`; the app refuses to start without the PII key.
`scripts/gen_keys.py` writes a fresh keypair to the gitignored `backend/.env`,
and `scripts/rotate_pii.py --to N` re-encrypts in batches while old versions
remain readable.

## Model registry, cards and approvals

`ml/registry.json` is the declarative catalogue. Each entry carries the model
id/version, digest, task, modalities, regions, capability buckets, preprocessing
profile, input shape, CAM layer, licence and source metadata, metrics and an
approval benchmark path. Prose model cards live in `ml/cards/<model_id>.json`
(intended use, training data, validation, limitations) and are merged into the
registry at load time.

Startup `seed_models` inserts missing versions and refreshes descriptive fields
(digest, task, modalities, card, metadata) but never overwrites `state` on an
existing row. `model_approvals` is the source of truth: an administrator's
approve/reject/revoke decision is recorded there, projected onto
`model_versions.state` with `state_source='approval'`, `approved_by` and
`approved_at`, and audited. `GET /models` returns the merged state, full
approval history and licence/source/metrics metadata. Candidate and rejected
models remain visible in the library but cannot be selected for analysis.

Weights are not committed. `scripts/fetch_models.py` downloads the declared
files, checks each SHA-256 and writes `ml/weights/manifest.json`;
`--offline`/`--check` verifies a host with no network. `scripts/verify_models.py`
re-checks weights, cards and any declared benchmark, and
`ml/benchmark/bench_model.py` measures latency, peak RSS and CAM sanity through
the real engine and writes a JSON with a stable `benchmark_digest`. An
administrator approves a model with that digest; the engine factory re-checks
the registry digest on load and fails with `409 model_digest_mismatch` if a file
was swapped.

## Inference engines and preprocessing

`inference/engines/` is a factory keyed by `(model_id, version)` with an
`lru_cache(maxsize=4)`. Each adapter wraps one model family:

| Engine | Input | Output | CAM layer |
|---|---|---|---|
| `StubEngine` | `xrv_chest_224` | deterministic normal/abnormal | input gradient |
| `XrvChestEngine` | `xrv_chest_224` | top-8 chest findings | `features.norm5` |
| `MonaiDensityEngine` | `monai_density_299` | BI-RADS density A–D (sigmoid) | `features.Mixed_7c` |
| `SiglipBoneEngine` | `siglip_bone_224` | zero-shot normal vs abnormal | last ViT block, token grid |
| `MammoScreenEngine` | — | refuses until benchmarked and approved | — |

Preprocessing profiles (`preprocessing/profiles.py`) fix size, channels, crop,
intensity scale and normalisation. The worker records the profile name, input
size, channel count, CAM layer and capability bucket in `provenance.parameters`,
so a stored result can be reproduced without hard-coded 224px assumptions.
Torch and transformers are imported lazily: the stub path runs without them.
CAM passes on one engine are serialised by `engine_lock(model_id, version)`
because torch modules are not re-entrant safe.

## Security model

- **Authentication**: email + password (`argon2`), JWT HS256 with `sub`, `role`,
  `exp`; 8-hour default TTL. Demo users exist only for development and their
  password is printed only under `import.meta.env.DEV`.
- **Authorisation**: dependencies `get_current_user`, `require_roles(...)`,
  `require_image_reader` (rejects administrators), `require_identity_reader`
  (clinicians only), `require_patient_owner` (404 for foreign patients), and
  per-case scoping in `can_access_case`.
- **Case scoping**: clinicians see only cases they created; researchers see
  their own plus cases with `research` consent; administrators see all case
  metadata but never image bytes or identity.
- **Patient identity** is visible only to the clinician owner; every view is
  audited before the payload is returned (see above).
- **Administrators** are refused `403 images_forbidden` on every image-content
  endpoint (pixels, file, preview, heatmaps) and on report creation. Verified
  against the running app on 2026-11-10.
- **Audit**: append-only, hash-chained events (`seq`, `prev_hash`, `hash`).
  Every login, identity read, case/image/analysis/result/review/report action is
  recorded. `write_audit_now` uses its own session and `BEGIN IMMEDIATE` for
  events that must be durable before continuing (identity views). The chain can
  be verified in-app or independently with `scripts/verify_audit.py`.
- **De-identification** happens before storage; see [DEID.md](DEID.md).
- **Error format**: RFC 9457 `application/problem+json` with a stable `code`
  field. The frontend keys messages off `code`, not prose.

Role matrix (see [API.md](API.md) for per-endpoint detail):

| Capability | Clinician | Researcher | Administrator |
| --- | --- | --- | --- |
| Create cases / upload | yes | yes | no |
| Patient identity | owner only, audited | never | never |
| Read image bytes | own cases | own + research-consent | **never** |
| Submit analysis / batch | yes | yes | no |
| Read results | own cases | own + research-consent | job status only |
| Confirm/dismiss findings | owner | counts only | no |
| Create PDF report | yes | yes (pseudonymised) | governance PDF only |
| Export dataset | no | yes (pseudonymised) | no |
| Users / approvals / retention / health | no | read-only models | yes |
| Audit verify / export | no | no | yes |

## Frontend

- Routes: `/login`, `/` (role dashboard), `/worklist`, `/patients/new`,
  `/patients/:patientId`, `/cases/new`, `/cases/:caseId` (unified workspace,
  with `?result=<jobId>&finding=<index>`), `/research`,
  `/research/batches`, `/models`, `/settings`, `/admin/users`,
  `/admin/audit`, `/admin/health`, `/admin/retention`, `/admin/models`.
  `/cases/:id/results/:jobId` and `/audit` redirect to their current pages.
- `src/api/client.ts` is the only place that talks to the API; it attaches the
  bearer token, parses problem+json into `ApiError`, and downloads with auth.
- `src/lib/cornerstone.ts` registers one custom `miap:` image loader. The loader
  fetches `/pixels`, applies rescale, derives a window from DICOM values or a
  1st/99th percentile, registers the metadata modules Cornerstone requires, and
  returns a bare `IImage` — it never inserts into the cache itself, because
  `loadAndCacheImage` has already registered a pending entry.
- **One RenderingEngine for all viewports** (`ENGINE_ID`), reference-counted by
  `acquireEngine`/`releaseEngine`. Multiple engines produced separate WebGL
  contexts and vtk.js intermittently aborted frames (blank panes); a single
  context renders the four mammogram views reliably and uses less GPU memory.
- `ZoomPanSynchronizer` keeps the four mammogram panes aligned.
- The Grad-CAM overlay is a 2D canvas over the WebGL canvas. It maps the
  224×224 centre crop back to image indices using image origin/direction/spacing
  (Cornerstone 3.33 no longer exposes `imageData.indexToWorld`), then through
  `viewport.worldToCanvas`, and redraws on `IMAGE_RENDERED`/`CAMERA_MODIFIED`.
  Measured hotspot vs `.npy` argmax agreed within 0.4 % of image width.

## Configuration

All settings come from environment variables prefixed `MIAP_`, optionally read
from `backend/.env`. Relative paths in that file are resolved against
`backend/`, not the current directory.

| Variable | Default | Meaning |
| --- | --- | --- |
| `MIAP_ENV` | `development` | Environment label |
| `MIAP_SECRET_KEY` | dev placeholder | JWT signing and UID HMAC key |
| `MIAP_DATA_DIR` | `data/` | Blob, derived and report root |
| `MIAP_DATABASE_PATH` | `data/miap.db` | SQLite file |
| `MIAP_JWT_TTL_MINUTES` | `480` | Token lifetime |
| `MIAP_UPLOAD_MAX_BYTES` | `524288000` | Per-file upload limit |
| `MIAP_MODEL_BACKEND` | `stub` | `torch` for real inference |
| `MIAP_MODEL_DEVICE` | `cpu` | Torch device |
| `MIAP_MODEL_DIR` | `ml/weights/` | Weight cache |
| `MIAP_REGISTRY_PATH` | `ml/registry.json` | Model registry |
| `MIAP_CORS_ORIGINS` | `http://localhost:5173` | Allowed origins |
| `MIAP_MIGRATIONS_DIR` | `<repo>/migrations` | Numbered SQL migrations |
| `MIAP_PII_KEY` | — (required) | Base64 32-byte AES-GCM key for identity |
| `MIAP_PII_INDEX_KEY` | — (required) | Base64 key for the hospital-number blind index |
| `MIAP_PII_KEY_VERSION` | `1` | Version tag written with each ciphertext |
| `MIAP_PII_KEYS` | `{}` | JSON map of older key versions during rotation |

## Failure behaviour

- **Unsupported capability bucket** → `409 analysis_not_supported` with
  `capability: <bucket>` at submission and again in the worker (defence against
  stale jobs). The UI disables the button and explains why.
- **Model outside the capability** → `409 model_scope_mismatch`; **candidate or
  rejected model** → `409 model_not_approved`. Neither may be selected manually
  or automatically.
- **Idempotency conflict** → `422 idempotency_conflict` when a key is reused for
  a different case/image.
- **Worker failure** → job `failed` with `error_code`/`error_detail`, an
  `job.failed` audit event, and the UI shows the code.
- **Missing mammogram view** → the grouping service returns `missing`,
  `duplicates`, `unassigned` and the UI renders an explicit placeholder rather
  than an empty pane.
- **Report file deleted** → `404 report_file_missing`; the result JSON remains
  canonical.
- **Decode failures** → `422` with `dicom_unreadable`, `image_unreadable` or
  `dicom_reencode_failed`, never a partial store.

## Known limits of this cycle

- Chest X-ray, limb/hand radiograph and mammogram density analysis are
  implemented. The bone model is experimental: it has no documented dataset
  provenance, and hip/pelvis studies are flagged `degraded` with a visible
  caveat. MammoScreen remains a candidate and cannot be selected.
- Mammogram density is a qualitative BI-RADS-style category (highest per breast,
  one job per view). It is not a cancer screen, and the summary says so.
- TorchXRayVision's public-dataset weights are not validated on Ugandan
  patients; every report says so.
- Scores are uncalibrated. Bands are qualitative and server-computed; they are
  not probabilities of disease.
- Single-node SQLite; no horizontal scaling, no object storage.
- The audit chain's `BEGIN IMMEDIATE` closes the cross-session fork window but
  remains a single-process assumption.
- Report audiences (clinician / researcher / governance) are implemented;
  reports created before the audience column existed remain readable as
  `legacy`. There is no report template management screen.
- Development servers are HTTP; TLS is expected from the deployment proxy.
- Test images are synthetic fixtures, not patient data.
