# ADR-015: MVP scope deviation from the Phase-2 design package

- Status: Accepted
- Date: 2026-11-10
- Supersedes: nothing. This ADR is appended; the Phase-2 records are not edited.
- Context: `C:\MIAP\MIAP_MVP_Pipeline.md` is the scope authority for this build.
  The Phase-2 package at `review/design/` (14 ADRs, OpenAPI 3.1 contract, 50
  traced requirements) describes a broader system (CT, MRI, pathology, tabular
  data) that was never built.

## Decision

Build the MVP described by `MIAP_MVP_Pipeline.md`, not the Phase-2 system, and
record the sections where the MVP deliberately narrows or changes Phase-2
decisions:

| Area | Phase-2 design | MVP decision | Reason |
| --- | --- | --- | --- |
| Modalities | CT, MRI, pathology, tabular | Chest X-ray end-to-end; mammography limited to four-view grouping and viewing | One modality validated end to end is defensible in the available time; multi-modality breadth without validation is not |
| Mammography AI | BIRADS, density, lesion detection | None in this cycle | Requires a validated model and a labelled dataset the team does not hold |
| Viewer | OHIF (Phase-2 ADR-011) | Cornerstone3D embedded in React | MVP Stage 9 names Cornerstone3D; OHIF adds a second deployable and a second auth surface |
| Inference | GPU serving | Local CPU, single-process worker | Hardware gate benchmarked the target laptop (M0); CPU inference meets the demo latency budget |
| Topology | Multi-service | Single FastAPI modular monolith, SQLite WAL, in-process worker | Solo developer, offline demo; a modular boundary preserves the option to split later |
| Roles | Broader role set | clinician, researcher, administrator | Matches MVP §Stage 2. Administrators still never receive image bytes |
| Governance | Full 50-requirement trace | Audit chain, provenance, receipts, reproducible model metadata | Cheap to keep, expensive to retrofit; the rest is out of scope |

## Consequences

- The Phase-2 OpenAPI contract is not implemented. This build's contract is
  described in `docs/API.md` and generated from the FastAPI app.
- Evaluation claims are limited to what was measured (see
  `docs/MILESTONES.md`): demo-model outputs carry no clinical meaning, and
  every result says so.
- Adding a modality later means adding a routing capability and a validated
  engine, not reworking the storage, audit or viewer layers.
- The decision is recorded rather than silently dropped, so a reviewer can
  compare this build against the older design package and see the delta.
