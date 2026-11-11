# Milestones and evidence

Cycle dates: 2026-11-09 to 2026-11-10 (Africa/Kampala). Every claim below names
the command or artifact it comes from. Screenshots and the report PDF are in
`docs/evidence/`; benchmark and audit data are reproducible from the scripts
named.

## M0 — Hardware gate and repository scaffold (2026-11-09)

| Check | Result | Source |
| --- | --- | --- |
| Python / Node / git present | Python 3.13.1, Node 24.22.1 | `python --version`, `node --version` |
| CPU PyTorch | torch 2.15.0+cpu, torchvision 0.29.2+cpu, torchxrayvision 1.5.7 | `ml/benchmark/m0_report.json` (2026-11-09T22:18:39+0300) |
| Inference mean latency | 665.5 ms (12 images, DenseNet-121, 224×224) | same report, `timing.total_ms_mean` |
| Inference p95 latency | 689.0 ms | same report, `timing.total_ms_p95` |
| Peak RSS | 852.0 MB | same report, `peak_rss_mb` |
| Grad-CAM resolution | 7×7 grid upsampled to 224×224 | same report, `checks.gradcam_7x7_to_224` |
| Occlusion sanity | masking the CAM hotspot drops "Lung Opacity" 0.8694 → 0.6767 (−22.2 %) | same report, `checks.occlusion_drop_10pct` |
| Gate | passed | `ml/benchmark/m0_report.json` → `"passed": true` |

Limits: 12 images, one machine, one model. This is a latency/feasibility gate,
not a clinical evaluation. Reproduce with
`python ml/benchmark/bench_infer.py`.

## M1 — Backend, auth, RBAC, upload, de-identification (2026-11-09)

Delivered: FastAPI app with modular layout, SQLite WAL schema, argon2 + HS256
JWT auth, three roles, case/image upload, PS3.15 subset de-identification,
content-addressed blob store, append-only hash-chained audit log, RFC 9457
error shape, pytest suite.

Verification: `backend/tests/test_auth.py`, `test_cases.py`, `test_ingest.py`,
`test_deid.py`, `test_deid_tags.py`, `test_audit.py`. Full suite result on
2026-11-10: **160 passed** in 37.68 s (`pytest -q` from `backend/`).

Security checks exercised by tests: administrators get 403 on image bytes and
report downloads; researchers see own cases plus research-consent cases only;
uploaded DICOM has patient tags replaced/removed and UIDs remapped.

## M2 — Modality and body-region routing, mammogram grouping (2026-11-09)

Delivered: modality detection for DICOM (`Modality` tag) with raster fallback,
body-region/view normalisation, mammogram four-view grouping keyed by laterality
× view, capability table deciding which analyses are offered.

Verification: `backend/tests/test_routing.py`, `test_ingest.py`. UI evidence:
`docs/evidence/2026-11-10-m3-mammo-four-view.png`,
`-mammo-missing-view.png`, `-mammo-synced-zoom-pan.png`.

## M3 — Cornerstone3D viewer (2026-11-10)

Delivered: React viewer with single shared RenderingEngine and refcount, custom
`miap:` image loader for server-decoded pixels (handles JPEG/J2K-compressed
DICOM the browser cannot decode), window/level, zoom/pan tools, four-view
mammogram layout with linked pan/zoom and a "missing view" state.

Verification: `frontend` typecheck clean; browser screenshots
`2026-11-10-m3-chest-viewer.png`, `-mammo-four-view.png`,
`-mammo-synced-zoom-pan.png`, `-mammo-missing-view.png`.
Known defect found and fixed during M4: Cornerstone 3.33 removed
`indexToWorld` from `getImageData()`; the overlay now derives world
coordinates from `origin`/`direction`/`spacing`.

## M4 — Chest inference end to end with Grad-CAM (2026-11-10)

Delivered: analysis job queue (in-process worker, crash recovery), stub and
torch engines, chest DenseNet-121 via TorchXRayVision, Grad-CAM heatmap,
immutable result documents with provenance and warnings, heatmap overlay in the
viewer, job progress in the case workspace.

Verification, 2026-11-10:
- UI-triggered job `j_9d44dc00-8e51-48b0-84c7-18eaaf21dbea` completed; result
  and provenance payloads fetched from the API.
- Overlay alignment measured in-browser: rendered hotspot at (0.497, 0.212)
  vs heatmap argmax (0.496, 0.214), difference ≈ 0.002 of image width.
- Overlay stays registered through zoom in (camera scale 281 → 90) and out
  (→ 777).
- Screenshots: `2026-11-10-m4-result-overlay.png`, `-result-no-overlay.png`,
  `-result-zoomed.png`, `-case-job-completed.png`.

## M5 — Report, model library, audit export (2026-11-10)

Delivered: two-page A4 PDF report (ReportLab) with embedded 224×224 heatmap,
findings, limitations and provenance; model library page from
`ml/registry.json`; audit verification endpoint and NDJSON export; standalone
verifier `scripts/verify_audit.py`.

Verification, 2026-11-10:
- PDF created and downloaded through the UI: 2 pages, 37 KB, embedded
  heatmap, limitation text present (text extracted with pypdf);
  `docs/evidence/2026-11-10-m5-chest-report.pdf`.
- Model library lists both registry models with digests and intended use:
  `2026-11-10-m5-model-library.png`.
- Audit chain verified intact at 70 events; NDJSON export 35,886 bytes;
  `2026-11-10-m5-audit-verified.png`.
- `scripts/verify_audit.py` re-verified the exported file independently and
  rejected a deliberately tampered copy (mismatch reported at seq 3).
- Administrator denied image bytes and report download (403) through the API.

## M6 — Hardening and end-to-end verification (2026-11-10)

| Item | State | Evidence |
| --- | --- | --- |
| Full backend test suite | 160 passed, 37.68 s | `pytest -q`, this date |
| Frontend typecheck | clean | `npm run typecheck` |
| Schema snapshot | `migrations/001_init.sql`, 9 tables, foreign keys clean | validated in-memory with `foreign_key_check` |
| Data purge script | dry-run by default, resolves `C:\MIAP\data`, reports audit tail and inventory | `scripts/purge_data.py` |
| Independent audit verifier | accepts valid export, rejects tampered export | `scripts/verify_audit.py` |
| Dev launcher | starts backend + frontend, polls `/healthz`, cleans up | `scripts/dev.ps1` (tested on ports 8011/5175) |
| Docs | `ARCHITECTURE.md`, `API.md`, `DEID.md`, `MILESTONES.md`, `adr/ADR-015-mvp-scope.md` | `docs/` |
| Config path fix | relative `MIAP_` paths resolve against `backend/`, not CWD | `backend/app/core/config.py`, verified from repo root: `data_dir = C:\MIAP\data` |
| Seed script | fixed import-order bug and aligned demo passwords with the login page; runs on a fresh database | `scripts/seed_users.py` |
| Disk space | 21 GB free on the system drive; runtime data 6.1 MB | `df -h /c`, `du -sh data` |
| Crash recovery | server killed mid-job; on restart the job requeued and completed | `2026-11-10-m6-crash-recovery.txt` |
| Full demo flow | see below | `2026-11-10-m6-demo-*.png`, `-demo-report.pdf` |

### Final demo run (2026-11-10)

Browser-driven, headless Edge, against the restarted backend and the live
frontend. Script: `.scratch/e2e-demo.js` (local harness, gitignored).

| Step | Result |
| --- | --- |
| Clinician signs in | ok |
| Creates study `DEMO-E2E-MW9WHKY2` (`c_3a4a71e5-…`) | ok |
| Uploads `chest_pa.dcm` | de-identified, UIDs remapped, "not retained" shown |
| Runs chest analysis | job `j_b9be2e22-3c2e-4278-91da-54ae56e4904a` completed |
| Result page | disclaimer, model id and provenance present, heatmap rendered |
| Creates PDF report | 2 pages, 37,047 bytes, contains disclaimer, model id, limitations, provenance |
| Administrator verifies audit | intact, 87 events |
| Administrator exports NDJSON | 45,407 bytes |
| Administrator requests image pixels | **403** |
| Page errors | none |

Independent checks on the same demo run:

- `scripts/verify_audit.py` on the exported NDJSON: `OK: 87 events, chain
  intact (genesis -> c213998d83a7...)`.
- Crash recovery: a throwaway server was killed while a job was `running`,
  restarted, and the job was requeued and completed (states
  `running → completed`, attempts 2). Log:
  `docs/evidence/2026-11-10-m6-crash-recovery.txt`.
- PDF text extraction: 2 pages, disclaimer, model id, limitations and
  provenance all present.

### Gaps still open (reported, not hidden)

- No automated frontend E2E suite in CI; browser checks were run manually via
  Playwright and their screenshots are the evidence.
- Mammography AI analysis is out of scope; four-view viewing only.
- The demo model carries no clinical meaning and every result says so.
- The audit chain is tamper-evident, not tamper-proof: someone with write
  access to the database file can replace the whole chain.
- De-identification is a fixed PS3.15 subset and cannot detect burned-in text
  or identifiers in unexpected free text (see `docs/DEID.md`).

### Amendment — report image overlays the heatmap (2026-11-10, later)

The M5 report embedded the stored 224×224 RGBA `heatmap.png` directly, so the
download showed a floating heatmap on a white page. This contradicted the
report's wording and the viewer, both of which show the heatmap over the
image. Changed `backend/app/modules/reporting/service.py`:

- `_display_gray` maps stored pixels to 8-bit display values using the DICOM
  window if present, otherwise the 0.5/99.5 percentile stretch used by
  `to_model_input`, with MONOCHROME1 inversion.
- `_overlay_preview` decodes the retained de-identified blob, resizes the
  heatmap to the centre square (the model input is `XRayCenterCrop` +
  `XRayResizer(224)`) and alpha-composites it. The report now embeds a ~100 mm
  composite with a caption stating the centre-square mapping; if decoding
  fails it falls back to the previous heatmap-only image and says so.

Evidence, same day:
- `backend/tests/test_report_overlay.py`: compositing and window/MONOCHROME1
  unit tests. Full backend suite: 162 passed.
- Regenerated through the live API on `ARDSSevere.png` (sample set):
  2 pages, 1,138,386 bytes,
  `docs/evidence/2026-11-10-report-overlay.pdf`; extracted page image
  `docs/evidence/2026-11-10-report-overlay-p1-img1.png` shows the X-ray with
  the heatmap composited and untouched grey bands where the centre crop does
  not reach.
- Caption text in the PDF reads "Heatmap overlaid on the de-identified
  image…" (pypdf extraction), confirming the composite path ran rather than
  the fallback.

## Foundation phase — identity, RBAC, workspace APIs (2026-11-10)

Delivered and tested:
- Numbered SQL migration runner (`backend/app/core/migrations.py`,
  `migrations/001–004`), legacy baseline, checksum refusal, and a dry-run
  script. `python scripts/migrate.py --status` on the live database reports:
  `legacy database, will be baselined at version 1`, pending `002`, `003`,
  `004`. `python scripts/migrate.py --dry-run` on a copy reports
  `applied [2, 3, 4]` and `integrity_check: ok` (run 2026-11-10).
- AES-256-GCM identity envelope with AAD binding, a separate HMAC blind index
  for hospital numbers, key versioning, key generation and batch rotation
  scripts. The app refuses to start without `MIAP_PII_KEY`.
- Patient APIs (create/list/lookup/detail/update/link) restricted to the
  clinician owner; researchers and administrators get `403`.
- Audit-before-read identity views (`write_audit_now`, own session,
  `BEGIN IMMEDIATE`), fail-closed on audit failure, detail-free decryption
  failures.
- Finding reviews (confirm/dismiss, encrypted notes, owner-only note reads),
  per-finding lazy CAM caching with per-result locks.
- Role-specific dashboards, personal/system settings, user administration,
  system health, retention preview/run, pseudonymised researcher export, batch
  analysis with per-item idempotency keys and batch roll-up, and model
  approval history projected onto `model_versions` without being overwritten by
  re-seeding.
- Result v2 presenter (bands, plain language, per-finding heatmap and review)
  computed at read time; stored documents remain immutable.

Evidence: `cd backend && ../.venv/Scripts/python.exe -m pytest -q` →
**223 passed** (2026-11-10). New coverage includes migrations (fresh, legacy
copy, checksum tamper), crypto round-trip and AAD swap, DB-byte and audit-detail
scans for identity values, the RBAC matrix, identity-view audit plus chain
verification, review lifecycle and note visibility, presenter v1→v2, distinct
per-finding CAM caching, batch idempotency and roll-up, approval persistence
across re-seeding, dashboard/settings capability separation, and report-free
administrator health output.

Open at this checkpoint:
- The live `data/miap.db` has **not** been migrated yet; only the copy rehearsal
  has run. Apply with `python scripts/migrate.py` after reviewing the dry run.
- Report audiences (clinician / researcher / governance), the design system,
  role screens, unified workspace and the viewer overhaul are the next phases
  and are not started.
- Frontend tests/typecheck have not been run against these APIs yet.

## Design system, role screens, workspace and viewer (2026-11-10)

Delivered:
- Token-based light/dark design system (Newsreader, Schibsted Grotesk,
  JetBrains Mono; petrol accent, amber signal, 12 px minimum type), inline SVG
  icon sprite, aperture logo, persisted theme with pre-paint `data-theme`.
- 84 px icon rail on desktop and a bottom tab bar below 1024 px; role-filtered
  navigation and client route guards backed by server enforcement.
- Role dashboards (clinician worklist summary and TB notice; researcher dataset,
  batch and model state; administrator governance with audit status), settings
  with a server-provided capability panel, worklist with server-side
  sort/filter and AI flag, patient creation/detail, and researcher dataset.
- Unified three-column study workspace: pinned patient banner (owner sees
  identity, other roles see the pseudonym and a restriction or no-link note),
  study facts and view thumbnails, viewer, findings with plain-language bands,
  trust strip (uncalibrated, TB notice, model state), confirm/dismiss dialog
  with encrypted note, technical expander, report action last. Administrators
  receive metadata only and the client no longer requests result payloads for
  them.
- Viewer overhaul: wheel zoom, primary-drag pan, secondary-drag window/level,
  double-click/double-tap reset, measurement only in M mode, floating
  auto-hiding controls, DICOM-style corners, before/after split handle, overlay
  opacity and H toggle, view chips with previous/next, keyboard shortcuts and
  help. No basic tool buttons and no stack scrolling for single images.

Fixes made during verification:
- Worklist consent filters now send `clinical/research/teaching` (they sent the
  pre-rename `treatment/education` values).
- Case summary `reviewed` now counts only reviews on findings that need review,
  so the worklist can no longer show `8/4`; guarded by an assertion in
  `tests/test_case_summary.py`.
- Zoom readout uses `viewport.getZoom()` instead of a camera baseline, so a
  fitted image reads 100% rather than 1%.

Evidence:
- Live `data/miap.db` migrated after a copy rehearsal: backup in
  `data/backups/`, `applied [2, 3, 4]`, dashboard audit status intact
  (207 events at capture time).
- Backend: `../.venv/Scripts/python.exe -m pytest -q` → **224 passed**
  (2026-11-10), including the new `GET /analyses/batches` role/limit test.
- Frontend: `npm run typecheck` clean and `npm run build` succeeds.
- Headless Chrome checks at 1440, 768 and 360 px across clinician, researcher
  and administrator routes: no horizontal overflow, no console errors, and no
  computed font below 12 px. Screenshots in `docs/evidence/phase2-*.png`.
- Viewer interactions driven through CDP: wheel zoom 100→104%, double-click
  reset to 100%, H toggles the overlay (0.85 → 0), M activates measurement,
  split sets a 50% clip with a draggable handle, finding selection updates
  `?result=&finding=` and loads the per-finding CAM.
- Reviewer flow in the UI stored a confirmed decision with note and rendered
  the badge without console errors; clinician report generated and downloaded
  (`docs/evidence/phase2-report-clinician.pdf`, 2.6 MB).

Open at this checkpoint:
- Phase 3 is not started: role-specific report templates (clinician,
  researcher, governance), model registry/cards/approvals metadata, MONAI
  density and SigLIP bone engines, mammography exam summary, and benchmark
  scripts.
- Per-finding CAMs are only stored for the primary finding; selecting another
  finding shows "No area map is stored for this finding" until Phase 3 adds
  on-demand computation.

## Role-specific reports (2026-11-10)

Delivered:
- `migrations/005_reports_governance.sql` rebuilds `reports` with a nullable
  `case_id` so governance reports need no case, preserving existing rows and
  the audience index. `Report.case_id` is nullable in the ORM.
- `reporting/templates/` with three renderers over one `ReportContext`:
  **clinician** (identity banner, plain-language bands, confirm/dismiss and
  notes, CAM overlay, TB and model caveats, technical footer), **researcher**
  (pseudonym only, raw score/threshold/band, primary CAM, provenance/runtime,
  local agreement counts, no notes), **governance** (account counts, audit-chain
  verification, approval decisions with benchmark digests, retention runs,
  storage totals; no patients, pixels or findings).
- `reporting/service.py` resolves the audience by role (clinician defaults to
  clinician, researcher to researcher, researcher may not request clinician,
  administrators are refused), presents the v2 document, decrypts identity only
  for the owner and audits that view before rendering, records `sha256`,
  `template_version=3.1`, `kind` and `audience`, and appends `report.created`.
  `get_report` is role- and owner-aware and appends `report.downloaded` with the
  audience.
- `POST /governance/reports?days=30` (administrator) and a **Governance PDF**
  action on the admin audit page.
- Stored result JSON remains canonical; old rows keep `audience=legacy` and
  their existing file.

Evidence:
- Fresh migration suite updated for version 5; report overlay tests now import
  the moved compositing helpers. Backend:
  `../.venv/Scripts/python.exe -m pytest -q` → **232 passed** (2026-11-10).
- `scripts/migrate.py --status` showed 005 pending; `--dry-run` on a copy
  applied `[5]` with `integrity_check: ok`; the live database then applied 005.
- Live flow on a linked patient (`DEMO-0001`, case `DEMO-004`, 8 findings, one
  confirmed with a note):
  - clinician PDF contains the name, hospital number and note;
  - researcher PDF contains none of them, and includes score/threshold,
    provenance and agreement counts;
  - researcher fetching the clinician report → 404; administrator fetching a
    case report → 403;
  - governance PDF contains audit and approval sections with no patient or
    case identifiers;
  - `GET /audit/verify` → `ok: true`, 249 events.
- `npm run typecheck` clean; `npm run build` succeeds.
- Evidence: `docs/evidence/phase3-report-clinician.pdf`,
  `phase3-report-researcher.pdf`, `phase3-report-governance.pdf`.

Open at this checkpoint:
- Phase 3.2–3.4 remain: registry/cards/approvals metadata, engine factory with
  MONAI density and SigLIP bone, capability routing, mammography exam summary,
  lazy per-finding CAMs, and model fetch/benchmark scripts.
- Per-finding CAMs are still primary-only; other findings show "No area map is
  stored for this finding" until Phase 3.3.

## Model registry, cards and approvals (2026-11-10)

Delivered:
- `ml/registry.json` now carries governance metadata for every entry: licence
  (SPDX, name, URL, access date), source repo/weights URL/SHA-256,
  `preprocess_profile`, `input`, `cam`, `metrics`, `capabilities`,
  `degraded_capabilities`, `validated_locally` and an approval benchmark path.
  Inline prose moved to `ml/cards/<model_id>.json` and is merged at load time.
- Registered **monai_density** (MONAI breast density, 299×299, Mixed_7c),
  **siglip_bone** (SigLIP 2 zero-shot limb; hip/pelvis marked degraded) and
  **mammoscreen** (proprietary candidate). The two new runnable-later models
  enter as `candidate` until their benchmarks and approval decisions exist.
- `seed_models` is insert-only for state; descriptive fields refresh. Approval
  decisions remain in `model_approvals` and are projected onto
  `model_versions` with `state_source='approval'`.
- `GET /models` now returns merged state, approval history, licence/source,
  input/CAM, capabilities and metrics. The model library shows Approved /
  Candidate and a "not validated locally" badge, licence and access date,
  approval history, technical input and an explicit "no local benchmark"
  statement.

Evidence:
- New `tests/test_registry_metadata.py`: every entry has metadata and a card;
  MammoScreen is an unselectable candidate; approval outranks registry and
  survives re-seeding; revoking keeps both decisions in history; a candidate is
  refused for analysis with `409 model_not_approved`.
- Backend: `../.venv/Scripts/python.exe -m pytest -q` → **238 passed**
  (2026-11-10). Frontend `npm run typecheck` clean.
- Live backend reseeded the new registry; `GET /models` lists five entries with
  licence and capability metadata.
- Screenshot: `docs/evidence/phase3-models-1440.png` (1440 px, no console
  errors, no computed font below 12 px).

Open at this checkpoint:
- MONAI density and SigLIP bone remain candidate until Phase 3.3 adds their
  engines and Phase 3.4 produces benchmark JSON; approval is then an explicit
  administrator decision.

## Recognition engines, capability routing and mammography summary (2026-11-10)

Delivered:
- `inference/engines/` factory keyed by `(model_id, version)` with
  `lru_cache(maxsize=4)` and registry digest verification:
  `StubEngine`, `XrvChestEngine` (chest), `MonaiDensityEngine` (BI-RADS density
  A–D via InceptionV3 NetAdapter layout, CAM at `features.Mixed_7c`),
  `SiglipBoneEngine` (zero-shot normal vs abnormal, CAM on the last ViT block)
  and `MammoScreenEngine`, which refuses selection until benchmarked.
- Preprocessing profiles in `preprocessing/profiles.py`
  (`xrv_chest_224`, `monai_density_299`, `siglip_bone_224`); the worker and the
  lazy CAM path both build inputs from the registry profile and record it in
  provenance. Torch/transformers remain lazily imported so the stub path runs
  without them.
- Capability routing: one `resolve_model_for_image()` replaces the three
  duplicated chest/modality gates. Buckets are `chest`, `bone_limb`,
  `bone_hip_pelvis` (experimental, `degraded`), `mammogram_density`,
  `unsupported` and `unrecognised`; a missing bucket returns `409
  analysis_not_supported` naming it, an explicit out-of-scope model returns
  `409 model_scope_mismatch`, and candidates are never auto-selected.
- Mammography: `POST /analyses/exam` queues one job per view (never a mosaic)
  and `GET /cases/{id}/exam-summary` aggregates the highest density per breast
  with evaluated/pending views, `single_view` and a caveat. The workspace shows
  a breast-density panel with pending-view chips and disables the exam action
  until an approved model covers the bucket.
- Per-finding CAMs are lazy and cached in `result_heatmaps`; the primary CAM is
  stored under its real `primary_finding_index` instead of assuming index 0.
  CAM passes are serialised per engine by `engine_lock`.
- New synthetic fixtures `hand_pa.dcm` and `hip_ap.dcm`; weights directories
  and `*.safetensors` are gitignored.

Evidence:
- New tests: `test_engines.py` (8), `test_exam_summary.py` (9),
  `test_monai_worker.py` (end to end, 7.8 s), `test_siglip_worker.py`
  (hand + hip, 16.5 s), plus bucket/routing/capability assertions.
- MONAI end to end on a four-view fixture LCC: density category in A–D,
  299×299 primary CAM, provenance `monai_density_299` / `Mixed_7c` /
  `mammogram_density`, exam summary reports the same category for the left
  breast as `single_view`.
- SigLIP on `hand_pa.dcm`: normal/abnormal findings, `degraded: false`;
  `hip_ap.dcm` returns `degraded: true` with the experimental-scope warning.
- Backend: `../.venv/Scripts/python.exe -m pytest -q` → **267 passed**
  (2026-11-10, 40 s). Frontend `npm run typecheck` clean.
- Browser check (1440 px, clinician): four-view study uploaded through the UI
  shows the breast-density panel as "0 of 4 views scored", both breasts
  "not scored" with pending chips, the caveat and the candidate notice; the
  "Analyse exam" action is disabled. Screenshot:
  `docs/evidence/phase3-mammogram-exam-summary-1440.png`.

Open at this checkpoint (addressed by the next section):
- Phase 3.4: fetch/verify/benchmark scripts, benchmark JSON and the approval
  decisions for MONAI density and SigLIP bone. MammoScreen stays candidate.
- Approving a model is a data decision, not a code one: until an administrator
  approves it, the exam and single-view actions stay disabled and the API
  returns `409 analysis_not_supported`.

## Model delivery gate: fetch, verify, benchmark, approval (2026-11-10)

Delivered:
- `scripts/fetch_models.py` downloads the declared files into `ml/weights/`,
  checks every SHA-256, writes `ml/weights/manifest.json` and supports
  `--check`/`--offline` for hosts with no network. Library-managed
  (`torchxrayvision`) and vendor weights are reported, not downloaded.
- `scripts/verify_models.py` re-hashes installed weights, requires a model card
  per registry entry, and requires any declared benchmark to exist, pass and
  carry the same model digest as the registry.
- `ml/benchmark/bench_model.py` runs the real engine, preprocessing profile and
  CAM through the registry digest check and writes latency, peak RSS, CAM
  sanity, prediction and a stable `benchmark_digest`. The MONAI gate covers both
  mean inference and first result including the CAM.
- The SigLIP registry entry now declares every required file with its own hash,
  so a directory model can be fetched and verified like a single file.
- Live approvals recorded through the administrator API for `monai_density`
  0.1 and `siglip_bone` 0.1, each storing the benchmark digest. MammoScreen
  remains candidate and its benchmark record is an explicit refusal.

Evidence:
- MONAI: 0.109 s mean per view, 2.652 s first result with a 299×299 CAM,
  465 MB peak RSS; all gates passed (`ml/benchmark/monai_density_benchmark.json`,
  digest `cffedc26…`).
- SigLIP: 0.331 s mean, 3.429 s first result with a 224×224 CAM, 2.08 GB peak
  RSS; all gates passed (`ml/benchmark/siglip_bone_benchmark.json`, digest
  `390bcb5c…`).
- MammoScreen: `409 model_not_approved`; recorded as unselectable
  (`ml/benchmark/mammoscreen_benchmark.json`).
- `scripts/verify_models.py` → all checks passed; `fetch_models.py --offline`
  verifies 8 installed files.
- End to end in the UI after approval: four-view mammogram scored 4 of 4,
  left and right breast both B, findings and confirm/dismiss visible
  (`docs/evidence/phase3-mammogram-exam-scored-1440.png`); the pre-approval
  state is `docs/evidence/phase3-mammogram-exam-summary-1440.png`. The model
  library shows MONAI and SigLIP approved and MammoScreen as an unselectable
  candidate (`docs/evidence/phase3-models-approved-1440.png`).
- Command log and numbers: `docs/evidence/2026-11-10-phase3-models.txt`.
- Backend tests and frontend typecheck re-run clean after the registry and card
  edits: **267 passed** (37 s), `npm run typecheck` clean. The live audit chain
  verifies after the approvals and exam runs: 345 events, genesis intact.

Not claimed:
- The benchmark proves speed, memory and CAM sanity only. Neither model has any
  local clinical validation, threshold tuning or accuracy estimate, and the
  model cards say so. Approvals are deployment decisions for decision support,
  not certifications.
- Weights are not committed; a fresh checkout must run `fetch_models.py` once.
  There is no startup auto-download, and the stub engine remains available when
  weights are absent.

## Copy pass, first-run tour and internal model visibility (2026-11-10)

Delivered: instructional copy removed across all role screens while retaining
clinical and security statements; a role-aware five-step tour with Next, Back,
Done and Skip, reopenable from Settings; and a registry `presentation:
"internal"` flag that hides routing/fallback classifiers (`stub_classifier`)
from `/models`, `/models/{id}`, `/system/health` and dashboard counts without
removing them from inference, routing or approval history.

Evidence: `docs/evidence/2026-11-10-copy-tour-models.txt`. Backend suite
**268 passed** (52 s) including `test_internal_router_models_are_not_listed`;
`npm run typecheck` clean. Live API listing after restarting the local server
(which had been running pre-change code) contains four presented models and
`/models/stub_classifier` returns 404. DOM checks confirm the tour opens once
per account, Skip and Done persist, Settings reopens it, and the removed viewer
help and instructional phrases are gone.

Not claimed: no screenshots for this pass (the in-app browser had no visible
surface); checks were structural (DOM text, localStorage, API responses). Copy
changes do not alter RBAC, de-identification, audit ordering or administrator
image denial, which remain covered by the backend suite.


## Consolidated warnings, decluttered workspace and model impression (2026-11-10)

Delivered: one bottom safety notice per screen from a shared `ScreenWarning`
component (dashboard, new study, new patient, workspace), with critical or
functional notices kept inline; a decluttered study workspace whose viewer is
the sticky centre column at >=1280 px and whose image upload moved into a
dialog; inline Confirm/Dismiss and inline notes with no review modal; and a
server-computed `impression` that names the leading condition (or density
category, or the absence of a review-band finding) in the workspace and both
PDF audiences.

Evidence: `docs/evidence/2026-11-10-disclaimers-workspace-impression.txt`.
Backend suite **271 passed** (42 s) including three new impression tests;
`npm run typecheck` clean. Live API result has `document_version: 2` and
`impression.text = "Most likely pattern: Lung Opacity (a cloudy patch in the
lung). Worth reviewing."` for the leading finding. DOM checks confirm the
combined safety notice, the three-column workspace grid, inline review with
`dialogs: 0`, and one warning block on the new-study and new-patient pages.

Not claimed: no screenshots this pass (in-app browser had no visible surface);
the sticky desktop layout was verified structurally, not visually. Researcher
visual check was not possible because no research-consent case with a completed
result was available; role filters and the researcher PDF remain covered by
tests. No RBAC, de-identification or audit rule changed.


## Project explainer and handover PDF (2026-11-10)

Delivered `docs/MIAP-Project-Explainer-2026-11-10.pdf`, a 45-page A4 handover
for group members who did not take part in the build. It records the original
requirements baseline, the delivered system, architecture, security and privacy
boundaries, role workflows, models and measured gates, the three report
audiences, requirement-by-requirement and build-order change tables, verification
evidence, limits, a runbook and appendices. Seven current-UI screenshots are
embedded; the contents page, document outline and page footers are generated.

Evidence: `docs/evidence/2026-11-10-project-explainer.txt`. The repository state
was re-checked for the document: backend suite **271 passed** (36.8 s;
re-run 10 November 2026), 19 backend modules, 16 runtime tables plus
`schema_migrations`, four presented models (three approved, one candidate) and
one hidden router classifier. Benchmark figures in the PDF match
`ml/benchmark/*.json` (M0 665.5 ms / 852 MB; MONAI 0.109 s mean, 2.652 s first,
465.4 MB; SigLIP 0.331 s mean, 3.429 s first, 2081.6 MB).

The PDF has 45 pages, 7 embedded screenshots, 17 internal contents links and
matching bookmarks, embedded subset fonts and extractable text. No page is
empty; the cover carries no footer and pages 2–45 are numbered.

Not claimed: the document has not been externally reviewed, and it is not a
clinical or regulatory submission. Its numbers and screenshots describe the
10 November 2026 build only. It contains no patient data, keys or environment
values.
