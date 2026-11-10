const BASE = "/api/v1";
const TOKEN_KEY = "miap.token";

export type Role = "clinician" | "researcher" | "administrator";

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: Role;
}

export interface CaseSummary {
  id: string;
  pseudonym: string;
  consent: string;
  status: string;
  modality: string | null;
  created_at: string;
  image_count: number;
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
  capability: { area: string | null; task: string | null; supported: boolean };
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
    capability: { area: string | null; task: string | null; supported: boolean };
  }[];
}

export interface CaseDetail extends CaseSummary {
  images: ImageSummary[];
  exam: MammogramExam | XrayExam | null;
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

export interface ResultDocument {
  case_id: string;
  image_id: string;
  modality: { value: string; method: string; confidence: number };
  region_or_view: { value: string; method: string; confidence: number };
  model: { name: string; version: string; digest: string | null; demo: boolean };
  classification: Record<string, string | number>;
  findings: { label: string; probability: number; threshold: number | null }[];
  detections: { label: string; box: number[]; score: number }[];
  heatmap: { format: string; path: string; overlay_png: string | null; shape: number[] | null } | null;
  warnings: string[];
  provenance_id: string;
  degraded: boolean;
  created_at: string;
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

export interface ModelEntry {
  model_id: string;
  version: string;
  digest: string;
  state: string;
  task: string;
  modalities: string[];
  regions: string[];
  demo: boolean;
  weights: string | null;
  card: Record<string, unknown>;
}

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

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; user: User }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<User>("/auth/me"),

  listCases: () => request<CaseSummary[]>("/cases"),
  createCase: (payload: { pseudonym: string; consent: string; retention_days?: number | null }) =>
    request<CaseDetail>("/cases", { method: "POST", body: JSON.stringify(payload) }),
  getCase: (caseId: string) => request<CaseDetail>(`/cases/${caseId}`),
  archiveCase: (caseId: string) => request<void>(`/cases/${caseId}`, { method: "DELETE" }),

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

  getPixels: async (imageId: string): Promise<{ meta: PixelMeta; buffer: ArrayBuffer }> => {
    const headers = new Headers();
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(`${BASE}/images/${imageId}/pixels`, { headers });
    if (!response.ok) throw new ApiError(response.status, "pixels_unavailable", "Pixels unavailable", "");
    const raw = response.headers.get("X-MIAP-Meta");
    if (!raw) throw new ApiError(500, "pixels_unavailable", "Pixel metadata missing", "");
    return { meta: JSON.parse(raw) as PixelMeta, buffer: await response.arrayBuffer() };
  },

  submitAnalysis: (payload: { case_id: string; image_id: string; params?: Record<string, unknown> }, idempotencyKey: string) =>
    request<Job>("/analyses", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(payload),
    }),

  getJob: (jobId: string) => request<Job>(`/analyses/${jobId}`),
  getResult: (jobId: string) => request<ResultDocument>(`/analyses/${jobId}/result`),
  getProvenance: (jobId: string) => request<Provenance>(`/analyses/${jobId}/provenance`),
  heatmapUrl: (resultId: string) => `${BASE}/results/${resultId}/heatmap.png`,
  getHeatmap: async (resultId: string): Promise<ArrayBuffer> => {
    const headers = new Headers();
    const token = getToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(`${BASE}/results/${resultId}/heatmap.npy`, { headers });
    if (!response.ok) throw new ApiError(response.status, "heatmap_unavailable", "Heatmap unavailable", "");
    return response.arrayBuffer();
  },

  listModels: () => request<ModelEntry[]>("/models"),
  getModel: (modelId: string) => request<{ model_id: string; versions: ModelEntry[] }>(`/models/${modelId}`),

  createReport: (caseId: string, jobId?: string) =>
    request<{ report_id: string; case_id: string; created_at: string; url: string }>(
      `/reports/${caseId}${jobId ? `?job_id=${encodeURIComponent(jobId)}` : ""}`,
      { method: "POST" },
    ),
  reportUrl: (reportId: string) => `${BASE}/reports/${reportId}.pdf`,

  verifyAudit: () => request<{ ok: boolean; checked: number; first_bad_seq: number | null }>("/audit/verify"),
  auditExportUrl: () => `${BASE}/audit/export`,
};

export async function downloadWithAuth(url: string, filename: string): Promise<void> {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(url, { headers });
  if (!response.ok) throw new ApiError(response.status, "download_failed", "Download failed", "");
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(objectUrl);
}
