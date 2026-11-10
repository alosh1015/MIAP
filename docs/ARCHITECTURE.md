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
  auth · cases · ingestion · de-id            users, cases, images, jobs,
  routing · inference · results               results, provenance, reports,
  reporting · audit · models                  audit_events, model_versions
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
| `core` | Settings, DB session, JWT/argon2, audit chain, blob store, problem+json | `backend/app/core/` |
| `auth` | Login, current user | `backend/app/modules/auth/` |
| `cases` | Create/list/detail/archive; consent and retention; admin metadata view | `backend/app/modules/cases/` |
| `ingestion` | Upload limit, type sniffing, de-identification, validation, decoded pixels, preview | `backend/app/modules/ingestion/` |
| `deid` | PS3.15 basic-profile subset, UID remapping, raster EXIF strip | `backend/app/modules/deid/` |
| `routing` | Modality and body-region resolution, mammogram four-view grouping | `backend/app/modules/routing/` |
| `preprocessing` | Pixel loading and model input (224×224, centre crop, normalisation) | `backend/app/modules/preprocessing/` |
| `inference` | Model selection, job queue, TorchXRayVision engine, Grad-CAM | `backend/app/modules/inference/` |
| `results` | Canonical result document, provenance record, heatmap artefacts | `backend/app/modules/results/` |
| `reporting` | A4 PDF from the stored JSON result | `backend/app/modules/reporting/` |
| `audit` | Hash-chained event export and verification | `backend/app/modules/audit/` |
| `models` | Read-only model registry seeded from `ml/registry.json` | `backend/app/modules/models/` |

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
4. **Submit analysis** (`POST /analyses`, `Idempotency-Key` required). Only
   chest X-rays are accepted in this cycle; mammograms return
   `409 analysis_not_supported`. The job is queued and the response is `202`.
5. **Worker** loads the stored (de-identified) pixels, builds the model input,
   predicts, computes Grad-CAM, writes the result document, heatmap `.npy`/`.png`,
   and a provenance record, then marks the job `completed`.
6. **Read results** (`GET /analyses/{job}/result`, `/provenance`,
   `/results/{id}/heatmap.*`). The JSON result is canonical; the PDF is a
   rendering of it.
7. **Report** (`POST /reports/{case_id}?job_id=...`) renders a two-page A4 PDF
   with study facts, findings, embedded heatmap, warnings, model limitations,
   provenance and report id.

## Storage layout

```
data/
  miap.db                                   SQLite, WAL mode
  blobs/sha256/34/8f/348f17...c05a0bcf22296577338c592e0bdee2a42dda02e09e0dbfde0d
  derived/<case_id>/<image_id>/heatmap.npy  224×224 float32
  derived/<case_id>/<image_id>/heatmap.png  224×224 RGBA overlay
  reports/<report_id>.pdf
```

Blobs are immutable and addressed by SHA-256 of the *stored* (de-identified)
bytes, written atomically through a temp file. Paths stored in SQLite are
relative to the data directory and resolved through a guard that rejects
traversal (`resolve_relative`).

## Security model

- **Authentication**: email + password (`argon2`), JWT HS256 with `sub`, `role`,
  `exp`; 8-hour default TTL. Demo users exist only for development and their
  password is printed only under `import.meta.env.DEV`.
- **Authorisation**: four role checks — `get_current_user`,
  `require_roles(...)`, `require_image_reader` (rejects administrators), and
  per-case scoping in `can_access_case`.
- **Case scoping**: clinicians see only cases they created; researchers see
  their own plus cases with `research` consent; administrators see all case
  metadata but never image bytes.
- **Administrators** are refused `403 images_forbidden` on every image-content
  endpoint (pixels, file, preview, heatmaps) and on report creation. Verified
  against the running app on 2026-11-10.
- **Audit**: append-only, hash-chained events (`seq`, `prev_hash`, `hash`).
  Every login, case/image/analysis/result/report action is recorded. The chain
  can be verified in-app or independently with `scripts/verify_audit.py`.
- **De-identification** happens before storage; see [DEID.md](DEID.md).
- **Error format**: RFC 9457 `application/problem+json` with a stable `code`
  field. The frontend keys messages off `code`, not prose.

Role matrix (see [API.md](API.md) for per-endpoint detail):

| Capability | Clinician | Researcher | Administrator |
| --- | --- | --- | --- |
| Create cases / upload | yes | yes | no |
| Read image bytes | own cases | own + research-consent | **never** |
| Submit analysis | yes | yes | no |
| Read results | own cases | own + research-consent | job status only |
| Create PDF report | yes | yes | no |
| Audit verify / export | no | no | yes |
| Model library | yes | yes | yes |

## Frontend

- Routes: `/login`, `/` (worklist), `/cases/new`, `/cases/:id`,
  `/cases/:id/results/:jobId`, `/models`, `/audit` (administrator only).
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

## Failure behaviour

- **Unsupported modality/region** → `409 analysis_not_supported` at submission
  and again in the worker (defence against stale jobs). The UI disables the
  button and explains why.
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

- Chest X-ray classification only. No mammography, CT, MRI or detection models.
- TorchXRayVision's public-dataset weights are not validated on Ugandan
  patients; every report says so.
- Single-node SQLite; no horizontal scaling, no object storage.
- Development servers are HTTP; TLS is expected from the deployment proxy.
- Test images are synthetic fixtures, not patient data.
