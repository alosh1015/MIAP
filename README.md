# MIAP

Multimodal Image Analysis Pipeline — decision-support prototype for chest X-ray and mammogram images.

This repository is the build for Specific Objective 3, Phase 1 (MVP), as specified in
[`MIAP_MVP_Pipeline.md`](MIAP_MVP_Pipeline.md). The cycle covers chest X-ray end to end:
hardware benchmark, ingestion with de-identification, modality/region routing, a
Cornerstone3D viewer, chest inference with Grad-CAM, PDF reports, a model library and audit
export. Mammography is supported for four-view grouping and viewing, not analysis.

MIAP is **decision support only**. It does not diagnose, and no output should be read as a
diagnosis.

## Requirements

- Python 3.13 (3.12 also supported if a dependency needs it)
- Node.js 22+
- No GPU, no Docker, no internet connection at runtime

## Setup

```bash
python -m venv .venv
.venv/Scripts/python -m pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu
.venv/Scripts/python -m pip install --no-cache-dir -r backend/requirements.txt -r backend/requirements-dev.txt
cd frontend && npm ci
```

## Develop

```bash
scripts/dev.ps1          # backend on :8000, frontend on :5173
```

## Verify

```bash
python scripts/make_fixtures.py
cd backend && ../.venv/Scripts/python -m pytest -q
python ml/benchmark/bench_infer.py
python scripts/verify_audit.py path/to/audit.ndjson   # exported through the admin UI
```

## Demo

```bash
python scripts/seed_users.py        # clinician, researcher, administrator
scripts/dev.ps1
```

The demo is fully offline. Open `http://localhost:5173`, sign in as the clinician,
create a case, upload a chest DICOM (or a PNG), run the analysis, inspect the
heatmap, download the PDF report, then sign in as the administrator to verify and
export the audit chain. Weights for the chest model are downloaded once by
`torchxrayvision` during setup and cached locally, so the demo itself needs no
network. Without cached weights the explicitly-labelled stub engine is used.
Every result states it is decision support, not a diagnosis.

## Documentation

| Document | Contents |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Topology, modules, storage, security model |
| [`docs/API.md`](docs/API.md) | Endpoints, roles, examples, error shapes |
| [`docs/DEID.md`](docs/DEID.md) | De-identification profile, UID remapping, limits |
| [`docs/MILESTONES.md`](docs/MILESTONES.md) | Dated evidence per milestone, open gaps |
| [`docs/adr/ADR-015-mvp-scope.md`](docs/adr/ADR-015-mvp-scope.md) | Scope deviation from the Phase-2 design |

## Maintain

```bash
python scripts/purge_data.py        # dry run: inventory + audit tail
python scripts/purge_data.py --yes  # delete runtime data (stop the server first)
```

`migrations/001_init.sql` is the schema snapshot. `backend/.env` and `data/` are
development-only and gitignored.

## Layout

| Path | Contents |
|---|---|
| `backend/` | FastAPI API, Tier-0 worker, SQLite schema, tests |
| `frontend/` | React + Vite + TypeScript + Tailwind, Cornerstone3D viewer |
| `ml/` | Model registry, model cards, benchmark scripts |
| `data/` | Runtime blobs, derived artefacts, database (gitignored) |
| `docs/` | Architecture, API, de-identification notes, ADRs |
| `scripts/` | Fixture generator, seeding, audit verification, dev runner |
