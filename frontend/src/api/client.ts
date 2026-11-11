const BASE = "/api/v1";
const TOKEN_KEY = "miap.token";

export type Role = "clinician" | "researcher" | "administrator";

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: Role;
}

export interface LastJob {
  id: string;
  state: "queued" | "running" | "completed" | "failed";
  progress: number;
  error_code: string | null;
  updated_at: string;
}

export type AiFlag = "flagged" | "clear" | "pending" | "failed";

export interface CaseSummary {
  id: string;
  pseudonym: string;
  consent: string;
  status: string;
  modality: string | null;
  created_at: string;
  image_count: number;
  patient_id: string | null;
  patient_display: string;
  identity_visible: boolean;
  ai_flag: AiFlag | null;
  findings_to_review: number;
  reviewed: number;
  latest_result_id: string | null;
  last_job: LastJob | null;
}

export interface ValidationCheck {
  code: string;
  status: "pass" | "fail" | "warn";
  detail: string;
}

export interface Validation {
  status: "pass" | "warn";
  passed: boolean;
  checks: ValidationCheck[];
  modality: { value: string; method: string; confidence: number };
  region_or_view: { value: string; method: string; confidence: number };
  capability: {
    area: string | null;
    task: string | null;
    supported: boolean;
    experimental?: boolean;
    bucket?: string;
  };
  warnings: string[];
}

export interface DeidReceipt {
  pipeline: string;
  sha256_in: string;
  sha256_out: string;
  removed: string[];
  replaced: string[];
  retained: string[];
  uids_remapped: number;
  reidentification_key_retained: boolean;
  warnings: string[];
}

export interface ImageSummary {
  id: string;
  modality: string | null;
  laterality: string | null;
  view: string | null;
  body_part: string | null;
  body_part_raw: string | null;
  mime: string;
  rows: number | null;
  cols: number | null;
  created_at: string;
  validation: Validation;
  deid_receipt: DeidReceipt;
}

export interface MammogramExam {
  type: "mammogram_four_view";
  layout: {
    top_left: ImageSummary | null;
    top_right: ImageSummary | null;
    bottom_left: ImageSummary | null;
    bottom_right: ImageSummary | null;
  };
  by_view: Record<string, ImageSummary | null>;
  missing: string[];
  duplicates: string[];
  unassigned: string[];
  complete: boolean;
}

export interface XrayExam {
  type: "xray";
  regions: {
    image_id: string;
    body_part: string | null;
    region: string | null;
    capability: {
      area: string | null;
      task: string | null;
      supported: boolean;
      experimental?: boolean;
      bucket?: string;
    };
  }[];
}

export interface ExamViewSummary {
  image_id: string;
  view: string;
  laterality: "L" | "R" | null;
  position: string | null;
  result_id: string | null;
  job_id: string | null;
  density: string | null;
  density_text: string | null;
  probability: number | null;
  model: { name: string; version: string } | null;
  degraded: boolean;
}

export interface ExamBreastSummary {
  density: string | null;
  density_text: string | null;
  views_evaluated: string[];
  views_pending: string[];
  single_view: boolean;
}

export interface ExamSummary {
  case_id: string;
  exam: string;
  complete: boolean;
  missing: string[];
  duplicates: string[];
  unassigned: string[];
  views: Record<string, ExamViewSummary>;
  breasts: Record<"L" | "R", ExamBreastSummary>;
  any_result: boolean;
  caveat: string;
}

export interface PatientSummary {
  id: string;
  name: string;
  hospital_number: string;
  sex: string;
  dob: string | null;
  age: number | null;
  case_count: number;
  created_at: string;
  updated_at: string;
}

export interface PatientCaseRef {
  id: string;
  pseudonym: string;
  status: string;
  modality: string | null;
  created_at: string;
}

export interface PatientDetail extends PatientSummary {
  cases: PatientCaseRef[];
}

export interface LookupResult {
  found: boolean;
  patient: PatientSummary | null;
}

export interface CaseDetail extends CaseSummary {
  images: ImageSummary[];
  exam: MammogramExam | XrayExam | null;
  patient: PatientSummary | null;
}

export interface CaseQuery {
  limit?: number;
  offset?: number;
  sort?: string;
  order?: "asc" | "desc";
  ai_flag?: AiFlag | "none";
  modality?: string;
  consent?: string;
  q?: string;
}

export interface Job {
  job_id: string;
  case_id: string;
  image_id: string | null;
  state: "queued" | "running" | "completed" | "failed";
  progress: number;
  model_id: string;
  model_version: string;
  error: { code: string; detail: string } | null;
  created_at: string;
  updated_at: string;
}

export type FindingBand = "below_threshold" | "borderline" | "above_threshold";
export type ReviewDecision = "confirmed" | "dismissed";

export interface HeatmapRef {
  format: string;
  path: string;
  overlay_png: string | null;
  shape: number[] | null;
  mapping?: "centre" | "full";
}

export interface FindingReview {
  finding_index: number;
  decision: ReviewDecision;
  has_note: boolean;
  note: string | null;
  reviewer_id: string;
  revision: number;
  created_at?: string;
  updated_at: string;
}

export interface Finding {
  label: string;
  probability: number;
  threshold: number;
  index: number;
  band: FindingBand;
  band_label: string;
  plain_label: string;
  plain_sentence: string;
  heatmap?: HeatmapRef;
  review?: FindingReview;
}

export interface FindingDetection {
  label: string;
  box: number[];
  score: number;
}

export interface ImageAnnotation {
  id: string;
  image_id: string;
  points: [number, number][];
  created_at: string;
}

export interface ReviewSummary {
  findings_to_review: number;
  reviewed: number;
  confirmed: number;
  dismissed: number;
  with_notes: number;
  items: FindingReview[];
  notes_visible: boolean;
}

export interface Impression {
  kind: "finding" | "density" | "none";
  label: string | null;
  plain_label: string | null;
  band: FindingBand | null;
  band_label: string | null;
  probability: number | null;
  text: string;
}

export interface ResultDocument {
  document_version: number;
  result_id: string;
  case_id: string;
  image_id: string;
  modality: { value: string; method: string; confidence: number };
  region_or_view: { value: string; method: string; confidence: number };
  model: { name: string; version: string; digest: string | null; demo: boolean };
  classification: Record<string, string | number>;
  findings: Finding[];
  detections: FindingDetection[];
  segmentation: Record<string, unknown> | null;
  heatmap: HeatmapRef | null;
  heatmap_mapping?: "centre" | "full";
  birads: { category: string | null; supporting_findings: string[] } | null;
  density: string | null;
  warnings: string[];
  provenance_id: string;
  degraded: boolean;
  created_at: string;
  primary_finding_index: number | null;
  impression: Impression;
  plain_language_note: string;
  review_summary: { findings_to_review: number; reviewed: number; confirmed: number; dismissed: number };
}

export interface Provenance {
  record_id: string;
  result_id: string | null;
  job_id: string;
  inputs: { role: string; digest: string; retained: boolean }[];
  model: { name: string; version: string; digest: string | null; demo: boolean };
  runtime: { python: string; platform: string; backend: string };
  parameters: Record<string, unknown>;
  code_commit: string;
  seed: number;
  operator: string;
  created_at: string;
}

export interface ModelApprovalEntry {
  id: string;
  decision: string;
  decided_by: string;
  decided_at: string;
  note: string | null;
  benchmark_digest: string | null;
}

export interface ModelInput {
  size?: number[] | null;
  channels?: number | null;
  crop?: string | null;
  mean?: number[] | string | null;
  std?: number[] | string | null;
}

export interface ModelEntry {
  model_id: string;
  version: string;
  digest: string;
  state: string;
  state_source: string;
  approved_at: string | null;
  approved_by: string | null;
  task: string;
  modalities: string[];
  regions: string[];
  capabilities: string[];
  degraded_capabilities: string[];
  demo: boolean;
  validated_locally: boolean;
  weights: string | null;
  preprocess_profile: string | null;
  input: ModelInput;
  cam: { method?: string; target_layer?: string | null; reshape?: string | null };
  licence: { spdx?: string; name?: string; url?: string | null; access_date?: string };
  source: { repo?: string | null; weights_url?: string | null; sha256?: string | null };
  metrics: { name?: string; value?: unknown; dataset?: string; source?: string }[];
  approval: { benchmark_path?: string | null };
  approvals: ModelApprovalEntry[];
  card: Record<string, unknown>;
}

export interface ModelApproval {
  id: string;
  model_id: string;
  version: string;
  decision: "approved" | "rejected" | "revoked";
  decided_by: string;
  decided_at: string;
  note: string;
  benchmark_digest: string | null;
}

export interface BatchItem {
  job_id: string;
  image_id: string | null;
  state: Job["state"];
  progress: number;
  model_id: string;
  model_version: string;
  error: { code: string; detail: string } | null;
  created_at: string;
  updated_at: string;
}

export interface Batch {
  batch_id: string;
  case_id: string;
  model_id: string;
  model_version: string | null;
  state: "queued" | "running" | "completed" | "partial" | "failed";
  total: number;
  counts: Record<string, number>;
  created_at: string;
  updated_at: string;
  items: BatchItem[];
}

export interface Preferences {
  theme: "system" | "light" | "dark";
  viewer_overlay_opacity: number;
  viewer_split: boolean;
  default_model: string | null;
  export_format: "csv" | "json";
}

export interface SettingsResponse {
  profile: { id: string; email: string; display_name: string; role: Role };
  preferences: Preferences;
  capabilities: Record<string, boolean>;
  viewer_defaults: { overlay_opacity: number; split_view: boolean; theme: string };
  notices: string[];
}

export interface SystemSettings {
  retention_default_days: number;
  export_row_cap: number;
  max_batch_images: number;
  tb_notice: string;
}

export interface AdminUser {
  id: string;
  email: string;
  display_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export interface RetentionPreview {
  due_cases: number;
  blobs: number;
  bytes_blobs: number;
  bytes_derived: number;
  bytes_reports: number;
  bytes_total: number;
  cutoff: string;
}

export interface RetentionResult {
  archived: number;
  deleted_results: number;
  deleted_reports: number;
  deleted_images: number;
  freed_bytes: number;
}

export interface SystemHealth {
  status: "ok" | "degraded";
  version: string;
  generated_at: string;
  database: { file: string; size_bytes: number; schema_version: number };
  storage: { data_size_bytes: number; free_bytes: number; total_bytes: number };
  queue: { queued: number; running: number; failed_today: number };
  worker: { running: boolean; engine_cache: number[] };
  users: { active: number; total: number };
  cases: { total: number; archived: number; due_for_retention: number };
  results: { total: number };
  models: {
    approved: number;
    candidate: number;
    versions: {
      model_id: string;
      version: string;
      state: string;
      state_source: string;
      approved_at: string | null;
    }[];
  };
  audit: { ok: boolean; checked: number; first_bad_seq: number | null };
}

export interface ClinicianDashboard {
  role: "clinician";
  patients: { mine: number };
  studies: { total: number; open: number };
  ai: { flagged: number; awaiting_review: number };
  recent_cases: CaseSummary[];
  notices: string[];
}

export interface ResearcherDashboard {
  role: "researcher";
  datasets: { own: number; research_consent: number };
  batches: { active: number };
  models: { approved: number; candidate: number };
  recent_exports: { at: string; detail: Record<string, unknown> }[];
  compute_warning: string;
}

export interface AdminDashboard {
  role: "administrator";
  queue: { queued: number; running: number };
  users: { active: number };
  models: { pending_approvals: number };
  retention: { due: number };
  audit: { ok: boolean; checked: number; first_bad_seq: number | null; verified_at: string };
}

export type Dashboard = ClinicianDashboard | ResearcherDashboard | AdminDashboard;

export interface PixelMeta {
  rows: number;
  cols: number;
  samples_per_pixel: number;
  photometric: string;
  slope: number;
  intercept: number;
  window_center: number | null;
  window_width: number | null;
  column_pixel_spacing: number;
  row_pixel_spacing: number;
  frames: number;
  voi_lut_function: string;
  dtype: "uint8" | "uint16" | "int16" | "float32";
  min: number;
  max: number;
}

export class ApiError extends Error {
  status: number;
  code: string;
  detail: string;

  constructor(status: number, code: string, title: string, detail: string) {
    super(title || code || `HTTP ${status}`);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(): Headers {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the MIAP server", "Start the backend on port 8000.");
  }

  if (response.status === 401 && getToken()) {
    setToken(null);
    window.dispatchEvent(new Event("miap:unauthenticated"));
  }

  if (!response.ok) {
    let code = "http_error";
    let title = response.statusText;
    let detail = "";
    try {
      const problem = await response.json();
      code = problem.code ?? code;
      title = problem.title ?? title;
      detail = typeof problem.detail === "string" ? problem.detail : "";
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, code, title, detail);
  }

  if (response.status === 204) return undefined as T;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) return (await response.json()) as T;
  return (await response.text()) as T;
}

async function getBytes(path: string): Promise<ArrayBuffer> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { headers: authHeaders() });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the MIAP server", "Start the backend on port 8000.");
  }
  if (!response.ok) {
    throw new ApiError(response.status, "file_unavailable", "File unavailable", "");
  }
  return response.arrayBuffer();
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; user: User }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<User>("/auth/me"),

  dashboard: () => request<Dashboard>("/dashboard"),

  listCases: (query: CaseQuery = {}) => {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
    }
    const suffix = params.toString();
    return request<CaseSummary[]>(`/cases${suffix ? `?${suffix}` : ""}`);
  },
  createCase: (payload: { pseudonym: string; consent: string; retention_days?: number | null; patient_id?: string | null }) =>
    request<CaseDetail>("/cases", { method: "POST", body: JSON.stringify(payload) }),
  getCase: (caseId: string) => request<CaseDetail>(`/cases/${caseId}`),
  linkPatient: (caseId: string, patientId: string) =>
    request<CaseDetail>(`/cases/${caseId}/patient`, {
      method: "POST",
      body: JSON.stringify({ patient_id: patientId }),
    }),
  archiveCase: (caseId: string) => request<void>(`/cases/${caseId}`, { method: "DELETE" }),

  listPatients: (query?: string, limit = 50) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (query) params.set("query", query);
    return request<PatientSummary[]>(`/patients?${params.toString()}`);
  },
  createPatient: (payload: { name: string; hospital_number: string; sex: string; dob?: string | null }) =>
    request<PatientDetail>("/patients", { method: "POST", body: JSON.stringify(payload) }),
  getPatient: (patientId: string) => request<PatientDetail>(`/patients/${patientId}`),
  updatePatient: (
    patientId: string,
    payload: { name?: string; hospital_number?: string; sex?: string; dob?: string | null },
  ) => request<PatientDetail>(`/patients/${patientId}`, { method: "PATCH", body: JSON.stringify(payload) }),
  lookupPatient: (hospitalNumber: string) =>
    request<LookupResult>(`/patients/lookup?hospital_number=${encodeURIComponent(hospitalNumber)}`),

  uploadImage: (caseId: string, file: File, overrides: Record<string, string> = {}) => {
    const form = new FormData();
    form.append("file", file);
    for (const [key, value] of Object.entries(overrides)) {
      if (value) form.append(key, value);
    }
    return request<{ image: ImageSummary; validation: Validation; deid_receipt: DeidReceipt }>(
      `/cases/${caseId}/images`,
      { method: "POST", body: form },
    );
  },

  previewUrl: (imageId: string) => `${BASE}/images/${imageId}/preview.png`,
  fileUrl: (imageId: string) => `${BASE}/images/${imageId}/file`,

  getPixels: async (imageId: string): Promise<{ meta: PixelMeta; buffer: ArrayBuffer }> => {
    const response = await fetch(`${BASE}/images/${imageId}/pixels`, { headers: authHeaders() });
    if (!response.ok) throw new ApiError(response.status, "pixels_unavailable", "Pixels unavailable", "");
    const raw = response.headers.get("X-MIAP-Meta");
    if (!raw) throw new ApiError(500, "pixels_unavailable", "Pixel metadata missing", "");
    return { meta: JSON.parse(raw) as PixelMeta, buffer: await response.arrayBuffer() };
  },

  preview: (imageId: string) => getBytes(`/images/${imageId}/preview.png`),

  listAnnotations: (caseId: string, imageId: string) =>
    request<ImageAnnotation[]>(`/cases/${caseId}/images/${imageId}/annotations`),
  createAnnotation: (caseId: string, imageId: string, points: [number, number][]) =>
    request<ImageAnnotation>(`/cases/${caseId}/images/${imageId}/annotations`, {
      method: "POST",
      body: JSON.stringify({ points }),
    }),
  clearAnnotations: (caseId: string, imageId: string) =>
    request<{ removed: number }>(`/cases/${caseId}/images/${imageId}/annotations`, {
      method: "DELETE",
    }),

  submitAnalysis: (
    payload: { case_id: string; image_id: string; model_id?: string | null; model_version?: string | null; params?: Record<string, unknown> },
    idempotencyKey: string,
  ) =>
    request<Job>("/analyses", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    }),

  submitBatch: (payload: {
    case_id: string;
    image_ids?: string[] | null;
    models?: { model_id?: string | null; model_version?: string | null }[];
    params?: Record<string, unknown>;
  }) => request<Batch>("/analyses/batch", { method: "POST", body: JSON.stringify(payload) }),

  submitExam: (payload: { case_id: string; image_ids?: string[] | null }) =>
    request<Batch>("/analyses/exam", { method: "POST", body: JSON.stringify(payload) }),

  getExamSummary: (caseId: string) => request<ExamSummary>(`/cases/${caseId}/exam-summary`),

  getBatch: (batchId: string) => request<Batch>(`/analyses/batch/${batchId}`),
  listBatches: (limit = 25) => request<Batch[]>(`/analyses/batches?limit=${limit}`),
  getJob: (jobId: string) => request<Job>(`/analyses/${jobId}`),
  getResult: (jobId: string) => request<ResultDocument>(`/analyses/${jobId}/result`),
  getProvenance: (jobId: string) => request<Provenance>(`/analyses/${jobId}/provenance`),

  getFindingHeatmap: (resultId: string, findingIndex: number) =>
    getBytes(`/results/${resultId}/findings/${findingIndex}/heatmap.npy`),
  primaryHeatmap: (resultId: string) => getBytes(`/results/${resultId}/heatmap.npy`),

  reviewFinding: (resultId: string, findingIndex: number, decision: ReviewDecision, note?: string) =>
    request<FindingReview>(`/results/${resultId}/findings/${findingIndex}/review`, {
      method: "POST",
      body: JSON.stringify({ decision, note: note ?? null }),
    }),
  listReviews: (resultId: string) => request<ReviewSummary>(`/results/${resultId}/reviews`),

  listModels: () => request<ModelEntry[]>("/models"),
  getModel: (modelId: string) => request<{ model_id: string; versions: ModelEntry[] }>(`/models/${modelId}`),
  listApprovals: () => request<ModelApproval[]>("/models/approvals"),
  decideModel: (
    modelId: string,
    version: string,
    decision: "approve" | "reject" | "revoke",
    payload: { note?: string; benchmark_digest?: string | null },
  ) =>
    request<{ model_id: string; version: string; state: string; decided_at: string }>(
      `/models/${modelId}/${version}/${decision}`,
      { method: "POST", body: JSON.stringify({ note: payload.note ?? "", benchmark_digest: payload.benchmark_digest ?? null }) },
    ),

  createReport: (caseId: string, jobId?: string, includeIdentity = false) => {
    const params = new URLSearchParams();
    if (jobId) params.set("job_id", jobId);
    if (includeIdentity) params.set("include_identity", "true");
    const query = params.toString();
    return request<{
      report_id: string;
      case_id: string;
      audience: string;
      sha256: string | null;
      created_at: string;
      url: string;
    }>(`/reports/${caseId}${query ? `?${query}` : ""}`, {
      method: "POST",
    });
  },
  createGovernanceReport: (days = 30) =>
    request<{
      report_id: string;
      audience: string;
      kind: string;
      title: string | null;
      sha256: string | null;
      created_at: string;
      url: string;
    }>(`/governance/reports?days=${days}`, { method: "POST" }),
  reportUrl: (reportId: string) => `${BASE}/reports/${reportId}.pdf`,

  getSettings: () => request<SettingsResponse>("/settings/me"),
  updateSettings: (patch: Partial<Preferences>) =>
    request<SettingsResponse>("/settings/me", { method: "PATCH", body: JSON.stringify(patch) }),
  getSystemSettings: () => request<SystemSettings>("/settings/system"),
  updateSystemSettings: (patch: Partial<SystemSettings>) =>
    request<SystemSettings>("/settings/system", { method: "PATCH", body: JSON.stringify(patch) }),

  listUsers: () => request<AdminUser[]>("/users"),
  createUser: (payload: { email: string; display_name: string; password: string; role: Role }) =>
    request<AdminUser>("/users", { method: "POST", body: JSON.stringify(payload) }),
  updateUser: (userId: string, patch: { display_name?: string; role?: Role; is_active?: boolean }) =>
    request<AdminUser>(`/users/${userId}`, { method: "PATCH", body: JSON.stringify(patch) }),
  resetPassword: (userId: string, password: string) =>
    request<void>(`/users/${userId}/password-reset`, {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

  health: () => request<SystemHealth>("/system/health"),
  retentionPreview: () => request<RetentionPreview>("/retention/preview"),
  retentionRun: () => request<RetentionResult>("/retention/run", {
    method: "POST",
    body: JSON.stringify({ confirm: true }),
  }),

  createExport: async (payload: { format: "csv" | "json"; consent?: string | null; modality?: string | null; limit?: number | null }) => {
    const response = await fetch(`${BASE}/exports`, {
      method: "POST",
      headers: (() => {
        const headers = authHeaders();
        headers.set("Content-Type", "application/json");
        return headers;
      })(),
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      let code = "export_failed";
      let title = "Export failed";
      let detail = "";
      try {
        const problem = await response.json();
        code = problem.code ?? code;
        title = problem.title ?? title;
        detail = typeof problem.detail === "string" ? problem.detail : "";
      } catch {
        /* non-JSON */
      }
      throw new ApiError(response.status, code, title, detail);
    }
    return response.blob();
  },

  verifyAudit: () => request<{ ok: boolean; checked: number; first_bad_seq: number | null }>("/audit/verify"),
  auditExportUrl: () => `${BASE}/audit/export`,
};

export async function downloadWithAuth(url: string, filename: string): Promise<void> {
  const response = await fetch(url, { headers: authHeaders() });
  if (!response.ok) throw new ApiError(response.status, "download_failed", "Download failed", "");
  const blob = await response.blob();
  saveBlob(blob, filename);
}

export function saveBlob(blob: Blob, filename: string): void {
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(objectUrl);
}
