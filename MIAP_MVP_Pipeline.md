# MIAP MVP: Pipeline, Screens, Roles and Tools

Scope: Specific Objective 3, Phase 1 (MVP). Modalities: **X-ray** and **mammogram** only.
Draft date: 9 November 2026.

## How to read this document

Every tool carries a tag showing where it came from:

| Tag | Meaning |
|---|---|
| [S1] to [S8] | Appears in one of your 8 screenshots (S1 screen architecture, S2 X-ray pipeline, S3 body regions, S4 mammogram pipeline, S5 engineering considerations, S6 roadmap, S7 final selection, S8 Cornerstone connection) |
| [GUIDE] | Appears in the previous team's guide |
| [ADDED] | Not in your material. I think you need it. Challenge it if you disagree |

"Verify" notes mean: I am not certain, so check before committing to it.

Every pipeline stage in Section 5 uses the same layout: purpose, tools, X-ray path, mammogram path, output, failure handling, MVP status.

---

## 1. Scope and principles

**In the MVP**
- X-ray: three capability areas (chest, upper limb, fracture/long bone). Other body regions are recognised but answered with "not supported yet".
- Mammogram: four-view exam handling first, AI models after the plumbing works.
- Three roles with different screens: clinician, researcher, administrator.
- Architecture B2 (your earlier decision): one modality router, then specialist models. A fusion layer comes later.

**Out of the MVP**
- CT, MRI, pathology, dermoscopy.
- PACS/EHR integration, federated learning, clinical validation, regulatory approval.
- Real multi-view fusion (specified later in S6 Phase 5).

**Principles**
1. Decision-support only, never an autonomous diagnosis [S7].
2. BI-RADS category and supporting findings are reported separately from any malignancy probability [S7].
3. Preserve DICOM orientation, laterality, view and pixel information from the first step [S5].
4. Patients are split at patient level, never image level, when training and testing [S5].
5. Hiding a button is not security. The backend enforces roles too.

---

## 2. Users and screens

### 2.1 Roles

| Role | Who | Main goal |
|---|---|---|
| Clinician | Doctor, radiographer, clinical officer | Upload a case, get a clear result and a report quickly. Few settings, no jargon |
| Researcher | Student, lab member, supervisor | Control models and settings, compare models, run batches, export data, measure performance |
| Administrator | Lab or system manager | Manage users, roles, models and audit. By default does not see patient images (my suggestion, [ADDED]) |

### 2.2 The 12 screens from S1, and who sees what

F = full access. L = limited (see notes). Dash = no access.

| # | Screen | Clinician | Researcher | Administrator | Build priority |
|---|---|---|---|---|---|
| 01 | Dashboard | F: own recent cases, pending analyses | F: own cases plus experiments and batch jobs | F: system health, queue, user activity | P2 |
| 02 | New Case | F: single study upload | F: single and batch upload | Dash | P1 |
| 03 | Case Library | L: own cases only | L: own plus cases shared for research, bulk export | L: metadata only (counts, status), no images | P1 |
| 04 | Image Workspace | F: viewer, window/level, zoom, measure | F: same, plus raw output layers | Dash | P1 |
| 05 | Analysis | L: model auto-selected, one "Run" button | F: choose model, thresholds, preprocessing options, batch | Dash | P1 |
| 06 | Results | F: findings, confidence, heatmap, BI-RADS support | F: same, plus raw JSON, masks, CSV export | Dash | P1 |
| 07 | Reports | F: generate and export PDF | F: PDF plus research export | L: manage report templates | P2 |
| 08 | Model Library | L: read-only (what each model does, limits) | F: view, compare, model cards, performance | F: enable/disable, versions, register new weights | P2 |
| 09 | Dataset Manager | Dash | F: register datasets, splits, labels | L: storage use, access approvals | P3 |
| 10 | Evaluation | Dash | F: run evaluations, view metrics | L: view only | P2 |
| 11 | Settings | L: account and viewer defaults | L: account plus default parameters | F: system settings | P2 |
| 12 | Administration | Dash | Dash | F: users, permissions, audit log | P1-lite (login and roles), rest P2 |

### 2.3 What differs inside the shared screens

- **Analysis:** the clinician sees the case, the auto-chosen model name and a Run button. The researcher sees the same screen with an "Advanced" panel (model choice, confidence threshold, preprocessing toggles, batch queue).
- **Results:** the clinician sees a plain summary, overlay toggles and a one-click report. The researcher gets the same plus raw outputs and export buttons.
- **Case Library:** a clinician's list is filtered to their own cases by the backend. The administrator's list shows counts and status only.
- **Navigation:** one codebase, with menu items filtered by the role in the login token. The same filter is repeated on every API call.

---

## 3. End-to-end pipeline (overview)

```
 UPLOAD  (DICOM / PNG / JPEG)                                   [S2, S4]
    |
 1  INGESTION            store file safely, record case
    |
 2  VALIDATION + DE-IDENTIFICATION
    |
 3  ROUTER 1: modality   X-ray  |  Mammogram
    |                       |            |
 4  ROUTER 2 / ORGANISER    |            |
    X-ray: body region      |   Mammo: laterality + view
    chest / limb / bone     |   -> LCC  LMLO  RCC  RMLO
    |                       |            |
 5  PREPROCESSING        (X-ray: standard size)  (Mammo: keep high resolution)
    |
 6  SPECIALIST INFERENCE
    |   X-ray: chest | upper-limb | fracture
    |   Mammo: classification, detection, segmentation
    |
 7  EXPLAINABILITY + POST-PROCESSING   (heatmap, boxes, masks, confidence)
    |
 8  RESULTS STORE        (JSON + masks + heatmap arrays)            [S8]
    |
 9  VIEWER + RESULTS SCREENS   (Cornerstone.js)                     [S8]
    |
 10 REPORT               (PDF / JSON / CSV)

 Offline:       11 MODEL DEVELOPMENT + EVALUATION
 Cross-cutting: 12 SECURITY, USERS, AUDIT     13 DEPLOYMENT + COMPUTE
```

---

## 4. X-ray scope for the MVP

S3 lists seven regions. Building all of them is unrealistic. The MVP takes three capability areas, and the router recognises the rest.

| Area | Regions covered | Task | Model and data | MVP |
|---|---|---|---|---|
| A. Chest | Chest PA/AP | Multi-finding classification | TorchXRayVision DenseNet-121 [S2, S3] (pretrained weights available) | Yes |
| B. Upper limb | Wrist, hand, elbow, shoulder (MURA also has finger, forearm, humerus) | Normal vs abnormal | MURA dataset [S3] | Yes |
| C. Fracture / long bone | Bones in hand, leg, hip, shoulder | Fracture detection with boxes | FracAtlas dataset [S3] plus YOLO [S6] | Yes |
| D. Spine, pelvis | Recognised only | Later: segmentation then pathology | "FleXray + dedicated datasets" [S3] | Later |
| E. Head/skull, abdomen | Recognised only | Later: dedicated models | Dedicated datasets [S3] | Later |

Things you need to know about this table:
- **MURA covers the upper limb only** (verify exact classes). It does not cover legs. The label "Limbs" in S2 overstates it.
- **MURA and FracAtlas are datasets, not ready-made models.** Areas B and C probably need training or fine-tuning on Colab or Kaggle. Area A is the only one with pretrained weights ready to use. Budget time for this.
- **FleXray (S3):** I could not confirm it is a suitable X-ray dataset for spine or pelvis. That is why D is not in the MVP. Verify before anyone plans around it.
- **Dataset terms:** MURA needs agreement to the dataset terms, and the licence of every dataset needs a check.

When the router detects D or E regions, Results shows: "Body region recognised: [name]. Analysis for this region is not available yet."

---

## 5. Pipeline stages in detail

### Stage 1. Ingestion

**Purpose:** accept the file, store it safely, create a case record.

**Tools**
- FastAPI and Uvicorn (web backend) [ADDED]
- python-multipart (file upload handling) [ADDED]
- pydicom (read DICOM) [ADDED, supports S5 "DICOM handling"]
- Pillow (read PNG/JPEG) [ADDED]
- `filetype` or magic-byte check (confirm the file is really what its extension says) [ADDED]
- SQLAlchemy plus SQLite (case records; PostgreSQL later) [ADDED, PostgreSQL was in the previous team's design]

**X-ray path:** accepts DICOM, PNG or JPEG [S2]. One image or several per case.
**Mammogram path:** accepts DICOM images plus examination metadata [S4]. Expects up to four images per exam.
**Output:** stored file with hashed filename, a case ID, and a raw-metadata record.
**If it goes wrong:** wrong file type, corrupt file or over the size limit returns a clear message. Set a size limit (the previous team used 500 MB) [GUIDE].
**MVP:** P1.

### Stage 2. Validation and de-identification

**Purpose:** confirm the image is usable and remove patient identity.

**Tools**
- pydicom (check required tags, pixel data readable) [ADDED]
- pylibjpeg or GDCM (decode compressed DICOM; mammograms are often compressed) [ADDED]
- OpenCV and NumPy (blank, too dark, too small checks) [ADDED]
- DICOM anonymisation using pydicom tag removal or the `deid` / `dicom-anonymizer` packages (verify which) [ADDED]
- Pseudonymisation (random study ID replaces patient ID) [GUIDE]

**X-ray path:** validate size, pixel data, photometric interpretation (MONOCHROME1 or 2). JPEG/PNG have no metadata to strip, but filenames and any EXIF are removed.
**Mammogram path:** adds image quality checks [S4] and checks the exam is complete (four views present, or flag as partial).
**Output:** a validated, de-identified image plus a validation report (pass, warn, fail with reasons).
**If it goes wrong:** fail with a human-readable reason. Warnings (for example a missing view) still allow the user to continue.
**MVP:** P1.

### Stage 3. Router 1: modality detection

**Purpose:** decide whether the image is an X-ray or a mammogram.

**Tools**
- DICOM metadata auto-detection [S2, S4, your earlier decision]. Useful tags: Modality (MG for mammography, DX or CR for radiography) [ADDED, tag details]
- Small image classifier as fallback (a lightweight ResNet or EfficientNet through `timm` or torchvision, trained on X-ray vs mammogram) [ADDED]
- Manual override dropdown in the UI [ADDED]

**X-ray path:** Modality is DX or CR, or the fallback classifier says X-ray.
**Mammogram path:** Modality is MG, or the fallback classifier says mammogram.
**Output:** modality label plus how it was decided (metadata, classifier, manual) plus confidence.
**If it goes wrong:** low confidence or conflicting signals asks the user to confirm. Images from phones, scanned film or exported JPEGs have no metadata, so the fallback is essential, not optional.
**MVP:** P1.

### Stage 4. Router 2 and exam organiser

**Purpose:** X-ray: find the body region. Mammogram: find laterality and view, and group images into one exam.

**Tools**
- Xp-Bodypart-Checker (X-ray body-part classifier) [S2]. Verify its source, licence and the list of classes it supports.
- DICOM BodyPartExamined tag as a first hint [ADDED]
- DICOM laterality and view position tags for mammography [S4 "Laterality, CC/MLO"]; tag names are [ADDED]
- Mapping table from region to supported capability area (A, B, C, or "not supported") [ADDED]

**X-ray path:** region goes to area A, B or C. Anything else gets the "not supported yet" message.
**Mammogram path:** assign each image to LCC, LMLO, RCC or RMLO [S4], group into left and right breast, flag missing or duplicate views.
**Output:** region label for X-ray, or the four-view exam structure for mammography.
**If it goes wrong:** the metadata and the image disagree (for example the tag says chest but the classifier says hand). Show both and ask the user to confirm.
**MVP:** P1.

### Stage 5. Preprocessing

**Purpose:** prepare pixels for the model without losing clinically important detail.

**Tools**
- NumPy and OpenCV (windowing, normalisation, resizing, cropping) [ADDED]
- scikit-image (extra image operations) [GUIDE Appendix A]
- pydicom VOI LUT and rescale functions (correct brightness from DICOM) [ADDED]
- Albumentations (augmentation, training only, never at inference) [GUIDE Appendix A]
- SimpleITK (optional, only if needed) [GUIDE Appendix A]

**X-ray path:** invert MONOCHROME1 images, apply windowing, resize and normalise to what each model expects. TorchXRayVision expects a specific input size and intensity range (verify in its documentation).
**Mammogram path:** keep **high resolution** because microcalcifications can vanish when downscaled [S5]. Standardise breast orientation, crop away background, create model-input copies and patches while keeping the original full-resolution image.
**Output:** model-ready arrays, plus the original kept untouched for the viewer.
**If it goes wrong:** images that look wrong after processing (all black, inverted) trigger a validation warning rather than silent bad predictions.
**MVP:** P1 for X-ray. Mammogram handling P1 for loading and orientation, P2 for patches.

### Stage 6. Specialist inference

**Purpose:** run the right model for the region or view.

**Tools: X-ray**
- TorchXRayVision with DenseNet-121 (chest) [S2, S3]
- A MURA-trained classifier (DenseNet or EfficientNet through `timm`) [S3 for MURA; model choice ADDED]
- A FracAtlas-trained YOLO detector with the Ultralytics package [S3 for FracAtlas, S6 for YOLO; package ADDED]

**Tools: Mammogram**
- Mammo-CLIP and MAM-CLIP for benign/malignant and BI-RADS classification [S4, S6, S7]. Verify that public weights exist, the licence, and the exact input requirements.
- Mammo-FM as a foundation-model comparison [S7]. Later, verify availability.
- YOLO or Faster R-CNN for mass and calcification localisation [S6, S7]; Faster R-CNN through torchvision [ADDED]
- U-Net or nnU-Net for lesion outlining [S6, S7]; `segmentation_models_pytorch` for a lighter U-Net [ADDED]
- Multi-view feature fusion for combined breast assessment [S6 Phase 5], later

**Shared tools**
- PyTorch and torchvision [GUIDE Appendix A]
- ONNX Runtime (runs exported models efficiently on CPU, useful on a weak PC) [ADDED]
- A simple model registry file (name, version, input size, classes, limits) feeding the Model Library [ADDED]

**X-ray path:** one of three specialists, chosen by Stage 4.
**Mammogram path:** MVP first delivers loading and four-view display only (S6 Phase 1). Classification follows (Phase 2), then detection (Phase 3) and segmentation (Phase 4).
**Output:** raw predictions, probabilities, boxes, masks.
**If it goes wrong:** model load failure or timeout returns "analysis failed" with a logged reason. Never show a partial or guessed result.
**MVP:** P1 for chest, P2 for upper limb and fracture, P2 to P3 for mammogram models.

### Stage 7. Explainability and post-processing

**Purpose:** turn raw outputs into something a person can inspect and trust appropriately.

**Tools**
- Grad-CAM heatmaps [S8], through `pytorch-grad-cam` or Captum [GUIDE Appendix A, packages ADDED]
- OpenCV morphology (clean masks) [ADDED]
- highdicom (write DICOM SEG files) [ADDED, supports S8 "DICOM SEG" output]
- Confidence handling and thresholds [S1 "Confidence"]; Monte Carlo dropout for uncertainty is possible later [GUIDE]
- BI-RADS support and breast density reported as separate fields [S4, S7]

**X-ray path:** heatmap for classifiers, boxes for the fracture detector, per-finding probability for chest.
**Mammogram path:** lesion boxes, outlines, density, BI-RADS category with supporting findings [S4]. Treated as research and decision-support, not diagnosis [S7].
**Output formats (from S8):** classification as JSON; segmentation mask as PNG, NPY or DICOM SEG; Grad-CAM as a 2D array; detection coordinates as JSON.
**If it goes wrong:** a heatmap that looks unrelated to the finding is a known weakness of post-hoc explanations, so label heatmaps "where the model looked, not proof of a finding".
**MVP:** P2.

### Stage 8. Results store and data contract

**Purpose:** save everything in one predictable structure so the viewer, reports and evaluation all read the same thing.

**Tools**
- SQLAlchemy with SQLite (PostgreSQL later); Alembic for migrations [ADDED]
- Files on disk for masks and arrays, referenced from the database [ADDED]
- Pydantic (validates the JSON structure) [ADDED]

**X-ray path:** one result record per image.
**Mammogram path:** one result record per view, plus one exam-level record per breast.
**Output:** see the data contract in Section 7.
**If it goes wrong:** every result records the model name and version so old results remain interpretable after models change.
**MVP:** P1.

### Stage 9. Visualisation and results screens

**Purpose:** show the image and the AI outputs together, interactively.

**Tools**
- Cornerstone.js (current Cornerstone3D packages: core, tools, DICOM image loader) [S8]. Verify the current package names in its documentation.
- React with Vite and Tailwind CSS (frontend app) [ADDED]
- OHIF Viewer as a reference design [GUIDE Appendix A]
- Hanging layout for mammography: CC and MLO side by side, left against right [ADDED]

**X-ray path:** one viewport with window/level, zoom, pan, measure, and toggles for heatmap, mask and boxes [S8: render, blend, toggle, inspect].
**Mammogram path:** four-view layout with synchronised zoom and pan where practical, same toggles per view.
**Output:** what the user sees on Image Workspace and Results.
**If it goes wrong:** JPEG/PNG load through the image loader without DICOM metadata, so the viewer must work without it.
**MVP:** P1 (plain viewer), P2 (overlays).

### Stage 10. Report generation

**Purpose:** a downloadable summary of the case.

**Tools**
- ReportLab or WeasyPrint with Jinja2 templates (PDF) [ADDED]
- Matplotlib (small charts) [ADDED]
- JSON and CSV export for researchers [GUIDE]

**X-ray path:** one page: image with overlay, findings, probabilities, region, model and version.
**Mammogram path:** exam report: four views, per-breast findings, density, BI-RADS support, clearly separated from any malignancy probability [S7].
**Output:** PDF, JSON, CSV. Every report carries a "decision support, not a diagnosis" statement.
**If it goes wrong:** report generation failure must not lose the stored results.
**MVP:** P2.

### Stage 11. Model development and evaluation (offline)

**Purpose:** train or adapt models and measure them honestly. This feeds the Evaluation and Model Library screens.

**Tools**
- Google Colab or Kaggle notebooks (training compute) [GUIDE]
- PyTorch, `timm`, Ultralytics, `segmentation_models_pytorch` (training) [ADDED, see Stage 6]
- Albumentations for augmentation [GUIDE Appendix A]
- scikit-learn: metrics (AUC, sensitivity, specificity) and `StratifiedGroupKFold` for patient-level splits [S5; library ADDED]
- Dice and IoU for segmentation and boxes (MONAI metrics or your own code) [ADDED]
- MLflow or Weights & Biases for experiment tracking (optional) [ADDED]
- Model cards (a short document per model: data, performance, limits) [GUIDE]

**Datasets**
- Mammogram: VinDr-Mammo (primary), CBIS-DDSM and CMMD (secondary) [S7]. VinDr-Mammo needs credentialed access on PhysioNet. Plan for the wait.
- X-ray: MURA and FracAtlas [S3]; for chest, test on a dataset that was **not** in the model's training data (check which datasets TorchXRayVision used).

**Rules from S5**
- Patient-level splitting, so images from one patient never sit in both training and test.
- External validation on a different source to see whether performance transfers [S5, S6 Phase 6].
- Dense breast tissue lowers lesion visibility, so report results by density where data allows [S5].

**X-ray path:** per-area metrics (A, B, C reported separately).
**Mammogram path:** per-task metrics (classification, detection, segmentation) and per-density.
**Output:** a results table for your report and model cards for the Model Library.
**If it goes wrong:** a great score on one dataset proves nothing about patients elsewhere. Say so in the write-up.
**MVP:** P2. The scripts matter more than a screen.

### Stage 12. Security, users and audit

**Purpose:** make sure only the right people see the right things, and everything is traceable.

**Tools**
- JWT login tokens (PyJWT) and role-based access control [GUIDE]
- Password hashing with argon2 or bcrypt [ADDED]
- Audit log table (who did what, when, to which case) [GUIDE]
- Pseudonymisation of identifiers [GUIDE]
- HTTPS/TLS at deployment [GUIDE]

**X-ray path and mammogram path:** identical. Role checks on every endpoint.
**Output:** login, token with role, audit entries.
**If it goes wrong:** deny by default. If a role is unclear, no access.
**MVP:** P1-lite (login, three roles, basic audit). The rest P2.

### Stage 13. Deployment and compute

**Purpose:** run it reliably on limited hardware.

**Tools**
- Docker and Docker Compose [ADDED, the previous team also used Docker]
- Nginx (reverse proxy, TLS) [ADDED]
- Git and GitHub (code, shared by all three team members) [ADDED]
- pytest and httpx (tests) [ADDED]
- Orthanc (DICOM server) is optional and later, only if hospital connection becomes a goal [ADDED]

**X-ray path and mammogram path:** same deployment. Inference runs on CPU through ONNX Runtime, or on a Colab/Kaggle-hosted endpoint during development.
**Output:** one command that starts the whole app.
**If it goes wrong:** your PC (Celeron, 4 GB RAM, no AVX) already broke Open3D once. Before building around PyTorch, test `import torch` and one DenseNet-121 inference. If it fails, develop the backend on a better machine or on Colab and keep the local app light.
**MVP:** P0 (hardware test first), then P2.

---

## 6. Master tool list

| Tool | Stage | Source | Note |
|---|---|---|---|
| FastAPI, Uvicorn, python-multipart | 1 | ADDED | Backend |
| pydicom | 1, 2, 5 | ADDED | DICOM reading and tags |
| Pillow | 1 | ADDED | PNG/JPEG |
| SQLAlchemy, SQLite, Alembic | 1, 8 | ADDED | PostgreSQL later (GUIDE) |
| pylibjpeg / GDCM | 2 | ADDED | Compressed DICOM |
| DICOM anonymiser (`deid` or similar) | 2 | ADDED | Verify package |
| OpenCV, NumPy | 2, 5, 7 | ADDED | Core image handling |
| scikit-image | 5 | GUIDE | |
| SimpleITK | 5 | GUIDE | Optional |
| Albumentations | 5, 11 | GUIDE | Training only |
| DICOM metadata (modality, laterality, view) | 3, 4 | S2, S4 | Needs fallback for JPEG/PNG |
| Fallback modality classifier (timm / torchvision) | 3 | ADDED | For files without metadata |
| Xp-Bodypart-Checker | 4 | S2 | Verify classes and licence |
| TorchXRayVision | 6 | S2, S3 | Chest, pretrained |
| DenseNet-121 | 6 | S2 | Chest backbone |
| MURA | 6, 11 | S3 | Dataset, upper limb only |
| FracAtlas | 6, 11 | S3 | Dataset, fracture detection |
| FleXray + dedicated datasets | later | S3 | Verify before use |
| `timm` | 3, 6, 11 | ADDED | Backbones |
| Mammo-CLIP | 6 | S4, S6, S7 | Verify weights and licence |
| MAM-CLIP | 6 | S6, S7 | Verify weights and licence |
| Mammo-FM | 6 | S7 | Comparison, later |
| YOLO (Ultralytics) | 6 | S6, S7 | Detection |
| Faster R-CNN (torchvision) | 6 | S6 | Detection alternative |
| U-Net / nnU-Net | 6 | S6, S7 | Segmentation |
| `segmentation_models_pytorch` | 6 | ADDED | Lighter U-Net route |
| Multi-view feature fusion | 6 | S6 | Later |
| PyTorch, torchvision | 6, 11 | GUIDE | |
| ONNX Runtime | 6 | ADDED | CPU inference |
| Model registry file | 6, 8 | ADDED | Feeds Model Library |
| Grad-CAM (`pytorch-grad-cam` / Captum) | 7 | S8, GUIDE | |
| highdicom | 7 | ADDED | DICOM SEG output |
| Pydantic | 8 | ADDED | Validate JSON |
| Cornerstone.js (Cornerstone3D) | 9 | S8 | Viewer |
| React, Vite, Tailwind | 9 | ADDED | Frontend |
| OHIF Viewer | 9 | GUIDE | Reference only |
| ReportLab / WeasyPrint, Jinja2, Matplotlib | 10 | ADDED | PDF reports |
| Colab / Kaggle | 11 | GUIDE | Training compute |
| scikit-learn | 11 | ADDED | Metrics, group splits |
| MLflow / Weights & Biases | 11 | ADDED | Optional |
| VinDr-Mammo | 11 | S7 | Primary mammography dataset |
| CBIS-DDSM, CMMD | 11 | S7 | Secondary datasets |
| PyJWT, argon2/bcrypt | 12 | GUIDE, ADDED | Login |
| Docker, Docker Compose, Nginx | 13 | ADDED | |
| Git, GitHub, pytest, httpx | 13 | ADDED | |
| Orthanc | later | ADDED | Optional |

---

## 7. Data contract (what every result looks like)

One JSON record per image, aligned with the output formats in S8.

```json
{
  "case_id": "c_000123",
  "image_id": "i_000123_1",
  "modality": {"value": "xray", "method": "dicom_metadata", "confidence": 0.99},
  "region_or_view": {"value": "wrist", "method": "bodypart_checker", "confidence": 0.93},
  "model": {"name": "upper_limb_classifier", "version": "0.1"},
  "classification": {"label": "abnormal", "probability": 0.81},
  "detections": [{"label": "fracture", "box": [x1, y1, x2, y2], "score": 0.74}],
  "segmentation": {"format": "png", "path": "masks/i_000123_1.png"},
  "heatmap": {"format": "npy", "path": "heatmaps/i_000123_1.npy"},
  "birads": {"category": null, "supporting_findings": []},
  "density": null,
  "warnings": [],
  "created_at": "2026-11-09T10:00:00Z"
}
```

For mammograms, the `birads` and `density` fields are filled at exam level, and `region_or_view` holds LCC, LMLO, RCC or RMLO.

---

## 8. MVP build order

| Step | What | Matches S6 phase | Done when |
|---|---|---|---|
| 0 | Hardware test: PyTorch import, one DenseNet-121 inference | none | You know where inference will run |
| 1 | Ingestion, validation, de-identification, login with three roles | Phase 1 | Upload works for DICOM, PNG, JPEG, and roles are enforced |
| 2 | Router 1 plus Router 2 (X-ray regions, mammogram four-view grouping) | Phase 1 | A four-view exam groups correctly; X-rays route to a region |
| 3 | Cornerstone viewer, plain images | Phase 1 | Both modalities display, mammogram in four-view layout |
| 4 | Chest X-ray inference end to end (area A) with heatmap | none | Upload to result to PDF works for chest |
| 5 | Upper-limb and fracture models (areas B and C) | none | Trained, exported, plugged into the same pipeline |
| 6 | Mammogram classification (Mammo-CLIP / MAM-CLIP) | Phase 2 | Per-view and per-breast results appear |
| 7 | Evaluation scripts, Model Library, reports polish | Phase 6 | Metrics table and model cards exist |
| 8 | Mammogram detection and segmentation | Phases 3 and 4 | Boxes and outlines show in the viewer |

Fusion (S6 Phase 5) is explicitly after this MVP.

---

## 9. Risks and things to verify before building

1. **Hardware.** Test PyTorch on your PC first (Stage 13).
2. **Mammography models are the least certain part.** The recommendations in S6 and S7 came from ChatGPT. Confirm for each: public weights, licence, input size, hardware needed.
3. **Two of three X-ray areas need training.** MURA and FracAtlas are datasets, not models.
4. **Dataset access.** VinDr-Mammo needs credentialed access; MURA needs terms agreement. Start the requests early.
5. **Xp-Bodypart-Checker and FleXray** need verification (classes, licence, suitability).
6. **No metadata, no router.** Plan the fallback classifier and manual override from the start.
7. **Public datasets do not represent local patients.** Scores on them are about those datasets.
8. **BI-RADS is not a cancer probability** [S7]. Keep them separate in the UI, the JSON and the report.
9. **The previous team's reported numbers are unverified** [GUIDE]. Do not reuse them.

---

## 10. Uganda-specific context

- **Chest X-ray and fractures are the most realistic entry points.** X-ray is far more available than mammography in many facilities, and injuries (including road trauma) make fracture detection relevant. Mammography is scarcer, which is why it sits second in the MVP.
- **Expect imperfect inputs:** scanned film, phone photos of films and JPEG exports without DICOM metadata. This is why Stage 3 needs the fallback classifier and manual override.
- **Unstable power and limited bandwidth** favour a local-first, CPU-capable design, which is why ONNX Runtime and a light frontend are in the stack.
- **Data protection:** any local patient images will need ethics approval and compliance with the Data Protection and Privacy Act (2019). Check requirements with the department before collecting anything.
- **Skin and population bias:** public datasets come from other countries (for example VinDr-Mammo is Vietnamese). Report that limitation honestly.

---

## 11. Open decisions

1. Confirm the X-ray areas A, B, C as the MVP set, or swap C for another.
2. Decide where inference runs: your PC, a teammate's machine, or Colab.
3. Decide how much of mammography is in the MVP: grouping and viewing only, or classification too.
4. Decide whether the administrator may ever see images (my suggestion: no by default).
5. Decide who on the team (you, Herbert, Mariam) owns backend, frontend and models.
