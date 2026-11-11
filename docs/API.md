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
- **IDs** are prefixed: `u_` (user), `c_` (case), `i_` (image), `j_` (job),
  `r_` (result), `p_` (provenance), `rp_` (report), `a_` (audit event),
  `pt_` (patient), `rv_` (finding review), `hm_` (heatmap record),
  `b_` (analysis batch), `ma_` (model approval).
- **Timestamps** are UTC ISO-8601 with `Z`.

Common error codes: `not_authenticated` (401), `invalid_token` (401),
`forbidden` (403), `images_forbidden` (403), `*_not_found` (404),
`analysis_not_supported` (409), `idempotency_conflict` (422),
`validation_error` (422), `*_unreadable` (422).

## Role summary

| Endpoint | Clinician | Researcher | Administrator |
| --- | --- | --- | --- |
| `POST /auth/login`, `GET /auth/me` | ✓ | ✓ | ✓ |
| `GET /dashboard` | ✓ own | ✓ dataset | ✓ system |
| `POST /patients`, `GET /patients*` (identity) | ✓ owner | 403 | 403 |
| `POST /cases` | ✓ | ✓ | 403 |
| `POST /cases/{id}/patient` (link identity) | owner | 403 | 403 |
| `GET /cases`, `GET /cases/{id}` | own | own + research consent | all (metadata only) |
| `DELETE /cases/{id}` | owner | owner | 403 unless owner |
| `POST /cases/{id}/images` | owner | owner or research consent | 403 |
| `GET /images/{id}` and content routes | owner | owner + research | **403** |
| `POST /analyses`, `POST /analyses/batch` | ✓ | ✓ | 403 |
| `GET /analyses/{job}`, `GET /analyses/batch/{id}` | ✓ | ✓ | job status / 403 batch |
| `GET /analyses/{job}/result`, `/provenance` | ✓ | ✓ | 403 |
| `GET /results/{id}/heatmap.*` | ✓ | ✓ | 403 |
| `GET /results/{id}/findings/{i}/heatmap.*` | ✓ | ✓ | 403 |
| `POST /results/{id}/findings/{i}/review` | owner | 403 | 403 |
| `GET /results/{id}/reviews` | owner (notes) | counts only | 403 |
| `GET /models`, `/models/{id}` | ✓ | ✓ | ✓ |
| `GET /models/approvals`, `POST /models/{id}/{v}/approve` etc. | 403 | 403 | ✓ |
| `GET/PATCH /settings/me` | ✓ | ✓ | ✓ |
| `GET/PATCH /settings/system` | 403 | 403 | ✓ |
| `GET/POST /users`, `PATCH /users/{id}` | 403 | 403 | ✓ |
| `POST /exports` | 403 | ✓ | 403 |
| `GET /retention/*`, `GET /system/health` | 403 | 403 | ✓ |
| `POST /reports/{case}` | owner | researcher-audience only | 403 |
| `GET /reports/{id}.pdf` (case) | owner | researcher-audience only | 403 |
| `POST /governance/reports`, governance PDF | 403 | 403 | ✓ |
| `GET /audit/verify`, `/audit/export` | 403 | 403 | ✓ |

"Owner" means `case.created_by == user.id`. Researchers additionally reach
cases whose consent basis is `research`. Administrators reach all case metadata
but are rejected by `require_image_reader` on image content and never receive
patient identity.

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
{"pseudonym": "Study-2026-001", "consent": "clinical", "retention_days": 365, "patient_id": null}
```

`consent` is `clinical`, `research` or `teaching`; `retention_days` is optional
(1–3650); `patient_id` is optional and must belong to the caller (clinicians
only). `201` → `CaseDetail`.

### `GET /cases?limit=50&offset=0&sort=created_at&order=desc&ai_flag=&modality=&consent=&q=`

Server-side sort and filter. `sort` accepts `created_at`, `patient`,
`pseudonym`, `status`, `modality`, `image_count`, `ai_flag`,
`findings_to_review`, `reviewed`. `ai_flag` is one of `flagged`, `clear`,
`pending`, `failed`, `none`. `q` matches the pseudonym. Unknown sort/filter
values return `422`.

`200` → `CaseSummary[]`:
`{id, pseudonym, consent, status, modality, created_at, image_count,
patient_id, patient_display, identity_visible, ai_flag, findings_to_review,
reviewed, latest_result_id, last_job}`.

`patient_display` contains the decrypted name and hospital number only when the
caller is the clinician owner of the case; for every other caller it is the
pseudonym and `patient_id` is `null`. Listing identity-bearing cases writes one
`patient.list_viewed` audit event per request.

### `GET /cases/{case_id}` — detail

`CaseDetail` = summary plus:
- `images[]`: `{id, modality, laterality, view, body_part, body_part_raw, mime,
  rows, cols, created_at, validation, deid_receipt}`
- `exam`: for mammograms, `{layout, by_view, missing, duplicates, unassigned,
  complete}`; for X-rays, the per-image region capability; otherwise `null`.
- `patient`: `{id, name, hospital_number, sex, dob, age, case_count, ...}` for
  the clinician owner only; `null` otherwise.

For administrators `images` is always `[]` — metadata without pixel-level detail.

### `GET /cases/{case_id}/exam-summary` — mammogram summary

Image readers (clinician owner or researcher with access); administrators get
`403`. Deterministic aggregation over the stored per-view results:

```json
{
  "case_id": "c_...", "exam": "mammogram_four_view",
  "complete": true, "missing": [], "duplicates": [], "unassigned": [],
  "views": {
    "LCC": {"image_id": "i_...", "view": "LCC", "laterality": "L", "position": "CC",
            "result_id": "r_...", "job_id": "j_...", "density": "C",
            "density_text": "heterogeneously dense tissue", "probability": 0.71,
            "model": {"name": "monai_density", "version": "0.1"}, "degraded": false}
  },
  "breasts": {
    "L": {"density": "C", "density_text": "...", "views_evaluated": ["LCC","LMLO"],
          "views_pending": [], "single_view": false},
    "R": {"density": null, "density_text": null, "views_evaluated": [],
          "views_pending": ["RCC","RMLO"], "single_view": false}
  },
  "any_result": true,
  "caveat": "Breast density is a qualitative BI-RADS-style category ... not a cancer screen."
}
```

The summary never merges views into one image and never turns density into a
cancer probability. `single_view` marks a breast supported by only one scored
view.


### `POST /cases/{case_id}/patient` — link identity

```json
{"patient_id": "pt_..."}
```

Clinician only, owner only. A case can be linked to one patient; a different
patient id returns `409 case_already_linked`. The event `case.patient_linked`
is audited with IDs only. Linking never inspects or derives anything from image
pixels.

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
    "capability": {"area": "A", "task": "multi_finding_classification", "supported": true,
                   "experimental": false, "bucket": "chest"},
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
- The approved model is chosen from the study's capability bucket (below).
  No approved model for the bucket → `409 analysis_not_supported` with
  `capability: <bucket>` in `detail`; an explicit model that does not cover the
  study → `409 model_scope_mismatch`; an unapproved model →
  `409 model_not_approved`.
- Job states: `queued`, `running`, `completed`, `failed`.

### Capability buckets

| Bucket | Typical studies | Task | Default model |
|---|---|---|---|
| `chest` | chest X-ray | multi-finding classification | `chest_densenet121` (stub in demo mode) |
| `bone_limb` | hand, wrist, forearm, femur, knee, ankle | normal vs abnormal | `siglip_bone` |
| `bone_hip_pelvis` | hip, pelvis, femoral neck | fracture detection (experimental, `degraded`) | `siglip_bone` |
| `mammogram_density` | mammogram views | BI-RADS-style density A–D | `monai_density` |
| `unsupported` | skull, spine, abdomen, ribs | — | none |
| `unrecognised` | unknown body part | — | none |

The bucket is derived from the de-identified body part and modality at upload
time and shown in `validation.capability` (`{area, task, supported,
experimental, bucket}`). A candidate model is never selected automatically; it
must be approved by an administrator first.

### `POST /analyses/exam` — mammogram exam

```json
{"case_id": "c_...", "image_ids": null}
```

Clinician or researcher with access. Creates one job per mammogram view (never a
mosaic) and returns the batch (`202`, same shape as `/analyses/batch`). Views are
scored independently; the exam summary takes the highest density category per
breast. Images that are not mammograms in this case → `422 image_not_in_case`.


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

The stored document is immutable. Responses are a **v2 presentation** of it,
computed on read: each finding gains `index`, `threshold`, `band`
(`above_threshold` | `borderline` | `below_threshold`), `band_label`,
`plain_label`, `plain_sentence`, plus a per-finding `heatmap` (once cached) and
a `review` object. The response also carries `document_version: 2`,
`primary_finding_index`, `plain_language_note` and `review_summary`. Bands are
qualitative: the model is not calibrated, so raw scores appear only in the
technical expander / researcher view and are labelled uncalibrated. Review
notes are included only for the clinician owner.

It also carries `impression`, the single server-computed statement of the
leading pattern, shared by the UI, the clinician PDF and the researcher PDF:

```json
{"kind": "finding", "label": "Lung Opacity", "plain_label": "a cloudy patch in the lung",
 "band": "above_threshold", "band_label": "Above review band",
 "probability": 0.9009, "text": "Most likely pattern: Lung Opacity (a cloudy patch in the lung). Worth reviewing."}
```

`kind` is `finding` (a finding at or above the review band), `density`
(mammography density category `A`–`D`, with `band: null`), or `none`
(`text` is the fixed "No finding reached the review band..." sentence). A
`borderline` leading finding uses "Possible pattern: ..." and says the signal is
weak. The UI shows `text`; researcher and technical views may also show
`probability` labelled uncalibrated.

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

Read-only registry entries, merged with the recorded approval state and history:

```json
{"model_id":"monai_density","version":"0.1","digest":"pending",
 "state":"candidate","state_source":"registry","approved_at":null,
 "task":"breast_density_classification",
 "modalities":["mammogram"],"regions":["breast"],
 "capabilities":["mammogram_density"],"degraded_capabilities":[],
 "demo":false,"validated_locally":false,
 "weights":"monai:breast_density_classification",
 "preprocess_profile":"monai_density_299",
 "input":{"size":[299,299],"channels":3,"crop":"resize","mean":[0,0,0],"std":[1,1,1]},
 "cam":{"method":"gradcam","target_layer":"Mixed_7c","reshape":null},
 "licence":{"spdx":"Apache-2.0","name":"MONAI Model Zoo","url":"...",
            "access_date":"2026-11-10"},
 "source":{"repo":"https://github.com/Project-MONAI/model-zoo",
           "weights_url":null,"sha256":null},
 "metrics":[], "approval":{"benchmark_path":"ml/benchmark/monai_density_benchmark.json"},
 "approvals":[], "card":{"intended_use":"...","validation":"...","limitations":["..."]}}
```

`approvals` is the newest-first decision history for that version. A recorded
decision outranks the registry `state` (`state_source="approval"`). Models with
`validated_locally: false` have no local benchmark and must be presented that
way. Candidate and rejected models stay visible but are refused for analysis
(`409 model_not_approved`). Registry entries marked `presentation: "internal"`
(routing and fallback classifiers) are omitted from this listing and from
`/models/{model_id}`; they remain available to inference and routing.

### `GET /models/{model_id}`

One entry, or `404 model_not_found`.

## Reports

Reports carry an audience (`clinician`, `researcher`, `governance`), a template
version, and the SHA-256 of the generated file. Stored result JSON stays
canonical; reports are rendered from it at request time.

### `POST /reports/{case_id}?job_id={job_id}&audience={audience}`

`201` → `{"report_id":"rp_...","case_id":"c_...","audience":"clinician",
"kind":"case","sha256":"...","template_version":"3.1","created_at":"...",
"url":"/api/v1/reports/rp_....pdf"}`.

`job_id` is optional; without it the latest completed analysis for the case is
used. `audience` defaults to `clinician` for clinicians and `researcher` for
researchers. Researchers may only request `researcher`; administrators get
`403`. Creating a clinician report reads the linked patient identity, and that
read is written to the audit chain before rendering.

- **Clinician** (case owner): identity banner, plain-language findings with
  qualitative bands, confirm/dismiss decisions and notes, CAM overlay, caveats,
  technical footer.
- **Researcher** (pseudonym only): technical labels, raw score, threshold, band,
  primary CAM, provenance/runtime, local review agreement counts. No identity,
  no notes.

### `POST /governance/reports?days=30`

Administrator only. `201` → same shape with `"audience":"governance"`,
`"kind":"governance"`, `"case_id":null`. The PDF contains account counts by
role, audit-chain verification, model approval decisions, retention runs and
storage totals — never patients, pseudonyms, pixels or findings.

### `GET /reports/{report_id}.pdf`

Role- and owner-checked. Clinicians fetch case reports for cases they own;
researchers only `researcher` audience reports for accessible cases;
administrators only governance reports. Each download appends
`report.downloaded` with the audience. `404 report_file_missing` if the file was
removed — the JSON result remains canonical. Reports created before audiences
existed keep `audience="legacy"` and render their stored file.

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

## Patients (clinician only)

Patient identity is stored out of band from the images: a case is linked to a
patient id, never the other way round. Identity is AES-256-GCM encrypted with
AAD bound to the patient id; the hospital number has a keyed blind index for
exact-match lookup. Only the clinically responsible owner sees it.

### `POST /patients`

```json
{"name": "Amina Nakato", "hospital_number": "H-1024", "sex": "female", "dob": "1979-04-12"}
```

`201` → `PatientDetail` = `{id, name, hospital_number, sex, dob, age,
case_count, created_at, updated_at, cases[]}`. A duplicate hospital number for
the same clinician → `409 patient_exists`. Researchers and administrators get
`403 identity_forbidden`.

### `GET /patients?query=&limit=50&offset=0`

Returns the caller's patients. `query` is an exact hospital-number match through
the blind index (no substring search). One `patient.list_viewed` event is
written per request.

### `GET /patients/lookup?hospital_number=H-1024`

`200` → `{"found": true, "patient": {...}}` or `{"found": false, "patient": null}`.
Exact normalised match only. Every lookup is audited, hit or miss.

### `GET /patients/{patient_id}` and `PATCH /patients/{patient_id}`

Owner only; non-owners get `404 patient_not_found`. Every successful identity
read writes `patient.identity_viewed` **before** the response is returned. If the
audit write fails the read fails closed with `503 audit_unavailable`. Password:
none of these routes ever accept or return one.

Decryption failures return `422 identity_decrypt_failed` with no detail and
append an `identity.decrypt_failed` event. Decrypted values are never logged.

## Finding reviews

### `POST /results/{result_id}/findings/{finding_index}/review`

Clinician owner only.

```json
{"decision": "confirmed", "note": "Left lower zone opacity; correlate clinically."}
```

`200` → `{finding_index, decision, has_note, note: null, reviewer_id, revision,
created_at, updated_at}`. `decision` is `confirmed` or `dismissed`. A repeat
decision increments `revision` and is audited as `finding.review_changed`. Notes
are encrypted with the same envelope as identity (AAD `review:{id}`) and never
leave the owner's session.

### `GET /results/{result_id}/reviews`

Owner → full list including decrypted notes (`notes_visible: true`, plus a
`finding.notes_viewed` audit event). Researcher with case access → aggregate
counts only (`items: []`, `notes_visible: false`). Administrators: `403`.

## Batch analysis

### `POST /analyses/batch`

Clinician or researcher with case access.

```json
{"case_id": "c_...", "image_ids": ["i_..."], "models": [{"model_id": null, "model_version": null}], "params": {}}
```

`image_ids` is optional (defaults to every image in the case). Each
`(image, model)` pair becomes its own job with an idempotency key
`batch:{batch}:{image}:{model}:{version}`. `202` → the batch object with
`items[]`. The plan is capped by the system `max_batch_images` setting
(`422 batch_too_large`), and only supported X-ray regions are accepted
(`409 analysis_not_supported`).

### `GET /analyses/batch/{batch_id}`

`{batch_id, case_id, model_id, model_version, state, total, counts, items[]}`.
Batch state is `queued`, `running`, `completed`, `partial` or `failed`, rolled
up after each job finishes. The requester or anyone with case access may read
it; administrators get `403`.

## Findings heatmaps

### `GET /results/{result_id}/findings/{finding_index}/heatmap.npy` / `.png`

The primary CAM is computed synchronously by the worker; every other finding's
CAM is computed lazily on first request and cached in `result_heatmaps` with a
per-result lock. Repeated requests serve the same file. Image readers only;
administrators get `403`.

## Dashboard, settings, users, system

### `GET /dashboard`

Role-specific landing payload.
- Clinician: `patients.mine`, `studies.{total,open}`, `ai.{flagged,
  awaiting_review}`, `recent_cases[5]`, `notices` (includes the TB notice).
- Researcher: `datasets.{own,research_consent}`, `batches.active`,
  `models.{approved,candidate}`, `recent_exports[5]`, `compute_warning`.
- Administrator: `queue`, `users.active`, `models.pending_approvals`,
  `retention.due`, live `audit.{ok,checked,first_bad_seq}`. No clinical content.

### `GET /settings/me`, `PATCH /settings/me`

Profile, preferences (`theme`, `viewer_overlay_opacity`, `viewer_split`,
`default_model`, `export_format`), `viewer_defaults`, notices, and the
server-computed `capabilities` map for the caller's role. The capability map is
the single source of truth for what the UI may show.

### `GET /settings/system`, `PATCH /settings/system` (administrator)

`retention_default_days`, `export_row_cap`, `max_batch_images`, `tb_notice`.
Changes are audited as `settings.updated` with field names only.

### `GET /users`, `POST /users`, `PATCH /users/{id}`, `POST /users/{id}/password-reset` (administrator)

Never returns password hashes. Self-deactivation or removing your own
administrator role → `422 self_lockout`. Audit actions: `user.created`,
`user.updated`, `user.activated`, `user.deactivated`, `user.password_reset`.

### `GET /system/health` (administrator)

Database size and schema version, storage use, queue depth, worker state, user
and case counts, model states, and a live audit-chain verification. No
pseudonyms, patients, images or findings.

## Retention (administrator)

### `GET /retention/preview`

`{due_cases, blobs, bytes_blobs, bytes_derived, bytes_reports, bytes_total,
cutoff}`. Counts and bytes only. Audited as `retention.previewed`.

### `POST /retention/run`

Body `{"confirm": true}` (otherwise `422 confirmation_required`). Deletes due
images, results, reviews, heatmaps, provenance and reports, purges unreferenced
blobs and derived directories, and archives the cases. The audit chain is
retained. Audited as `retention.run` with counts and bytes.

## Exports (researcher)

### `POST /exports`

```json
{"format": "csv", "consent": "research", "modality": "xray", "limit": 500}
```

Pseudonymised rows only (`case_id`, `pseudonym`, consent, modality, timestamps,
image count, latest result model id, findings with score/threshold/band). No
identity, no review notes, no pixels. Row cap comes from the system settings.
Audited as `export.created` with the row count and a digest of the filters
(never the filter values).

## Model approvals (administrator)

### `GET /models/approvals`

Full decision history, newest first.

### `POST /models/{model_id}/{version}/approve|reject|revoke`

```json
{"note": "Passed CPU benchmark", "benchmark_digest": "..."}
```

Records a `model_approvals` row and projects the decision onto
`model_versions.state` with `state_source: "approval"`, `approved_by`,
`approved_at`. `benchmark_digest` should be the `benchmark_digest` written by
`ml/benchmark/bench_model.py`, which hashes the model, fixture, input, latency,
CAM checks and gates but not timestamps. `seed_models` never overwrites a
recorded decision. Inference selection reads the projected state. Audited as
`model.approved`, `model.rejected` or `model.revoked`.

## Health

`GET /healthz` (no auth) → `{"status":"ok","service":"miap","version":"0.1.0"}`.
