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
