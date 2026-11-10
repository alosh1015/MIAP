# MIAP HTTP API

Base path: `/api/v1`. Development host: `http://127.0.0.1:8000`
(proxied as `/api` by the Vite dev server). The interactive schema is served at
`/docs` and `/openapi.json`.

## Conventions

- **Auth**: `Authorization: Bearer <jwt>` on every route except
  `POST /auth/login` and `/healthz`.
- **Content**: JSON unless stated. Uploads use `multipart/form-data`.
- **Errors**: `application/problem+json`, always with a stable `code`:

```json
{
  "type": "https://miap.local/problems/case_not_found",
  "code": "case_not_found",
  "title": "Case not found",
  "status": 404,
  "instance": "/api/v1/cases/c_missing"
}
```

  Validation failures add `errors: [{loc, msg, type}]`.
- **IDs** are prefixed: `u_`, `c_` (case), `i_` (image), `j_` (job), `r_`
  (result), `p_` (provenance), `rp_` (report), `a_` (audit event).
- **Timestamps** are UTC ISO-8601 with `Z`.

Common error codes: `not_authenticated` (401), `invalid_token` (401),
`forbidden` (403), `images_forbidden` (403), `*_not_found` (404),
`analysis_not_supported` (409), `idempotency_conflict` (422),
`validation_error` (422), `*_unreadable` (422).

## Role summary

| Endpoint | Clinician | Researcher | Administrator |
| --- | --- | --- | --- |
| `POST /auth/login`, `GET /auth/me` | ✓ | ✓ | ✓ |
| `POST /cases` | ✓ | ✓ | 403 |
| `GET /cases`, `GET /cases/{id}` | own | own + research consent | all (metadata only) |
| `DELETE /cases/{id}` | owner | owner | 403 unless owner |
| `POST /cases/{id}/images` | owner | owner or research consent | 403 |
| `GET /images/{id}` and content routes | owner | owner + research | **403** |
| `POST /analyses` | ✓ | ✓ | 403 |
| `GET /analyses/{job}` | ✓ | ✓ | ✓ (status) |
| `GET /analyses/{job}/result`, `/provenance` | ✓ | ✓ | 403 |
| `GET /results/{id}/heatmap.*` | ✓ | ✓ | 403 |
| `GET /models`, `/models/{id}` | ✓ | ✓ | ✓ |
| `POST /reports/{case}`, `GET /reports/{id}.pdf` | ✓ | ✓ | 403 |
| `GET /audit/verify`, `/audit/export` | 403 | 403 | ✓ |

"Owner" means `case.created_by == user.id`. Researchers additionally reach
cases whose consent basis is `research`. Administrators reach all case metadata
but are rejected by `require_image_reader` on image content.

## Auth

### `POST /auth/login`

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"clinician@miap.local","password":"<demo password>"}'
```

`200` → `{"access_token": "...", "token_type": "bearer", "user": {id, email, name, role}}`.
The token carries `sub`, `role`, `exp`. A failed login is `401 invalid_credentials`
and is audited.

### `GET /auth/me`

Returns the current user: `{id, email, name, role}`.

## Cases

### `POST /cases` — create

```json
{"pseudonym": "Study-2026-001", "consent": "clinical", "retention_days": 365}
```

`consent` is `clinical`, `research` or `teaching`; `retention_days` is optional
(1–3650). `201` → `CaseDetail`.

### `GET /cases?limit=50&offset=0`

`200` → `CaseSummary[]`:
`{id, pseudonym, consent, status, modality, created_at, image_count}`.

### `GET /cases/{case_id}` — detail

`CaseDetail` = summary plus:
- `images[]`: `{id, modality, laterality, view, body_part, body_part_raw, mime,
  rows, cols, created_at, validation, deid_receipt}`
- `exam`: for mammograms, `{layout, by_view, missing, duplicates, unassigned,
  complete}`; otherwise `null`.

For administrators `images` is always `[]` — metadata without pixel-level detail.

### `DELETE /cases/{case_id}` — archive

`204`. The case row and audit trail remain; the status changes. Only the owner
(or an administrator acting on their own case) may archive.

## Images

### `POST /cases/{case_id}/images`

`multipart/form-data`:
- `file` (required) — DICOM, PNG or JPEG within `MIAP_UPLOAD_MAX_BYTES`
- optional form overrides: `modality`, `body_part`, `laterality`, `view`

`201` →

```json
{
  "image": { "id": "i_...", "modality": "xray", "body_part": "chest", ... },
  "validation": {
    "capability": {"area": "A", "task": "multi_finding_classification", "supported": true},
    "checks": [{"code": "decode", "status": "pass", "detail": "Decoded 512x512, MONOCHROME2"}],
    "modality": {"value": "xray", "method": "dicom_metadata", "confidence": 0.99},
    "region_or_view": {"value": "chest", "method": "dicom_metadata", "confidence": 0.95},
    "warnings": []
  },
  "deid_receipt": { "pipeline": "ps3.15-basic-subset/1.0", "sha256_in": "...", "sha256_out": "..." }
}
```

The original bytes are hashed for the receipt and then discarded. Failures:
`413 upload_too_large`, `415 unsupported_media_type`, `422 dicom_unreadable` /
`image_unreadable`, `409 duplicate_image` (same content already attached).

### `GET /images/{image_id}`

Metadata plus validation and de-identification receipt. No bytes.

### `GET /images/{image_id}/file`

The stored (de-identified) file as `application/dicom` / `image/png` /
`image/jpeg`, `Content-Disposition: inline`. Administrators: `403`.

### `GET /images/{image_id}/pixels` — viewer contract

Binary little-endian samples; `Content-Type` is
`application/x-miap-{uint8,uint16,int16,float32}`. Geometry and display hints
travel in the `X-MIAP-Meta` header as compact JSON:

```json
{"rows":512,"cols":512,"samples_per_pixel":1,"photometric":"MONOCHROME2",
 "slope":1.0,"intercept":0.0,"window_center":null,"window_width":null,
 "row_pixel_spacing":0.5,"column_pixel_spacing":0.5,"frames":1,"voi_lut_function":"LINEAR"}
```

The frontend loader applies slope/intercept, picks DICOM window values when
present and a 1st/99th percentile window otherwise.

### `GET /images/{image_id}/preview.png`

Small PNG for worklists and thumbnails. Administrators: `403`.

## Analyses

### `POST /analyses`

Headers: `Idempotency-Key: <1–128 chars>` (required).

```json
{"case_id": "c_...", "image_id": "i_...", "model_id": null, "model_version": null, "params": {}}
```

`202` →

```json
{"job_id":"j_...","case_id":"c_...","image_id":"i_...","state":"queued",
 "progress":0.0,"model_id":"chest_densenet121","model_version":"xrv-0.1",
 "error":null,"created_at":"...","updated_at":"..."}
```

- Repeating the same key with the same case/image returns the same job (`202`).
- Reusing a key for a different case/image → `422 idempotency_conflict`.
- Non-X-ray modality or unsupported region → `409 analysis_not_supported`.
- Job states: `queued`, `running`, `completed`, `failed`.

### `GET /analyses/{job_id}`

Job status: `{job_id, state, progress, error: {code, detail} | null, model_id,
model_version, ...}`. Administrators may read status.

### `GET /analyses/{job_id}/result`

`200` → the canonical result document. If the job is not complete:
`409 result_not_ready`; if failed: `409 analysis_failed` with the job's error.

```json
{
  "case_id": "c_...", "image_id": "i_...",
  "modality": {"value": "xray", "method": "dicom_metadata", "confidence": 0.99},
  "region_or_view": {"value": "chest", "method": "dicom_metadata", "confidence": 0.95},
  "model": {"name": "chest_densenet121", "version": "xrv-0.1", "digest": "c8f0...", "demo": false},
  "classification": {"label": "Lung Opacity", "probability": 0.9009},
  "findings": [{"label": "Lung Opacity", "probability": 0.9009, "threshold": 0.5}],
  "detections": [], "segmentation": null, "birads": null, "density": null,
  "heatmap": {"format": "npy", "shape": [224, 224], "path": "derived/...", "overlay_png": "derived/..."},
  "warnings": ["Decision support only. This output is not a diagnosis.", "..."],
  "provenance_id": "p_...", "degraded": false, "created_at": "..."
}
```

### `GET /analyses/{job_id}/provenance`

```json
{"record_id":"p_...","result_id":"r_...","job_id":"j_...","created_at":"...",
 "operator":"u_...","code_commit":"uncommitted","seed":0,
 "model":{"name":"chest_densenet121","version":"xrv-0.1","digest":"c8f0...","demo":false},
 "runtime":{"backend":"torch-cpu","python":"3.13.1","platform":"Windows-11-..."},
 "parameters":{"input_size":224,"normalisation":"torchxrayvision.datasets.normalize(img, 255)",
               "gradcam_layer":"features.norm5","heatmap_shape":[224,224],"threshold":0.5},
 "inputs":[{"role":"original_upload","digest":"...","retained":false},
           {"role":"deidentified_image","digest":"...","retained":true}]}
```

### `GET /results/{result_id}/heatmap.npy`

The raw 224×224 float32 array (`application/octet-stream`) as written by
`numpy.save`; the frontend parses it for the overlay.

### `GET /results/{result_id}/heatmap.png`

An RGBA preview with the same 224×224 grid, embedded in the PDF report.

Both heatmap routes are `404 result_not_found` when the result is outside the
caller's cases, so existence is not leaked.

## Models

### `GET /models`

Read-only registry entries:

```json
{"model_id":"chest_densenet121","version":"xrv-0.1","digest":"c8f0...",
 "state":"approved","task":"multi_finding_classification",
 "modalities":["xray"],"regions":["chest"],
 "weights":"torchxrayvision.densenet121-res224-all","demo":false,
 "card":{"intended_use":"...","validation":"...","limitations":["..."],"training_data":"..."}}
```

### `GET /models/{model_id}`

One entry, or `404 model_not_found`.

## Reports

### `POST /reports/{case_id}?job_id={job_id}`

`201` → `{"report_id":"rp_...","case_id":"c_...","created_at":"...","url":"/api/v1/reports/rp_....pdf"}`.

`job_id` is optional; without it the latest completed analysis for the case is
used. Report creation is audited and refused for administrators.

### `GET /reports/{report_id}.pdf`

Two-page A4 PDF: study facts, findings table, embedded heatmap, warnings, model
limitations, intended use, validation statement and the provenance reference.
`404 report_file_missing` if the file was removed — the JSON result remains
canonical.

## Audit (administrator only)

### `GET /audit/verify`

`200` → `{"ok": true, "checked": 70, "first_bad_seq": null}`. Recomputes the
SHA-256 link for every event in sequence order.

### `GET /audit/export`

`application/x-ndjson`, one event per line in sequence order:

```json
{"seq":1,"event_id":"a_...","ts":"...","actor_id":"u_...","action":"auth.login",
 "resource_type":"user","resource_id":"u_...","detail":{"role":"clinician"},
 "prev_hash":"0000...","hash":"a6f4..."}
```

Verify independently:

```bash
python scripts/verify_audit.py exported.ndjson
```

Exit code `0` means intact; `1` reports the first bad sequence and reason.

## Health

`GET /healthz` (no auth) → `{"status":"ok","service":"miap","version":"0.1.0"}`.
