import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  ApiError,
  type CaseDetail,
  type DeidReceipt,
  type ImageSummary,
  type Job,
  type MammogramExam,
  type XrayExam,
} from "../api/client";
import { useAuth, hasRole } from "../auth/AuthContext";
import { ImageViewer } from "../components/ImageViewer";
import { UploadPanel } from "../components/UploadPanel";
import { ViewerToolbar } from "../components/ViewerToolbar";
import { Badge, Card, ErrorNote, PageHeader, formatDate, shortDigest } from "../components/ui";
import type { ViewerTool } from "../lib/cornerstone";

const REGION_LABEL: Record<string, string> = {
  chest: "Chest",
  upper_limb: "Upper limb",
  fracture: "Long bone",
  unsupported: "Not supported",
  unrecognised: "Unrecognised",
};

export function CaseWorkspacePage() {
  const { caseId = "" } = useParams();
  const { user } = useAuth();
  const [study, setStudy] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tool, setTool] = useState<ViewerTool>("WindowLevel");
  const [resetSignal, setResetSignal] = useState(0);
  const [activeImageId, setActiveImageId] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Record<string, Job>>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(() => {
    api
      .getCase(caseId)
      .then((payload) => {
        setStudy(payload);
        setActiveImageId((current) => {
          if (current && payload.images.some((image) => image.id === current)) return current;
          return payload.images[0]?.id ?? null;
        });
      })
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Could not load this study"));
  }, [caseId]);

  useEffect(load, [load]);

  useEffect(() => {
    const pending = Object.values(jobs).filter((job) => job.state === "queued" || job.state === "running");
    if (pending.length === 0) return;
    const timer = window.setTimeout(() => {
      for (const job of pending) {
        api
          .getJob(job.job_id)
          .then((fresh) => setJobs((current) => ({ ...current, [fresh.image_id ?? ""]: fresh })))
          .catch(() => undefined);
      }
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [jobs]);

  const activeImage = useMemo(
    () => study?.images.find((image) => image.id === activeImageId) ?? study?.images[0] ?? null,
    [study, activeImageId],
  );

  async function submitAnalysis(image: ImageSummary) {
    setSubmitting(true);
    setSubmitError(null);
    try {
      const job = await api.submitAnalysis(
        { case_id: caseId, image_id: image.id },
        crypto.randomUUID(),
      );
      setJobs((current) => ({ ...current, [image.id]: job }));
    } catch (caught) {
      setSubmitError(caught instanceof ApiError ? caught.detail || caught.message : "Analysis could not be started");
    } finally {
      setSubmitting(false);
    }
  }

  if (error) {
    return (
      <div>
        <PageHeader title="Study" />
        <ErrorNote message={error} />
        <Link to="/" className="mt-4 inline-block text-sm text-clinical-700 hover:underline">
          Back to worklist
        </Link>
      </div>
    );
  }

  if (!study) {
    return <Card className="p-8 text-sm text-slate-500">Loading study…</Card>;
  }

  const mammogram = study.exam?.type === "mammogram_four_view" ? (study.exam as MammogramExam) : null;
  const xray = study.exam?.type === "xray" ? (study.exam as XrayExam) : null;
  const canUpload = hasRole(user, "clinician", "researcher");

  return (
    <div>
      <PageHeader
        title={study.pseudonym}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <Badge tone="info">{study.consent}</Badge>
            <span className="font-mono text-[11px] text-slate-400">{study.id}</span>
            <span className="text-xs text-slate-400">created {formatDate(study.created_at)}</span>
          </span>
        }
        actions={
          <Link to="/" className="text-sm font-medium text-slate-500 hover:text-slate-800">
            Back to worklist
          </Link>
        }
      />

      {user?.role === "administrator" ? (
        <Card className="mb-4 border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          Administrators see study metadata only. Image pixels and AI results are not available for this
          role by design.
        </Card>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="min-w-0 space-y-4">
          {study.images.length === 0 && canUpload ? (
            <UploadPanel caseId={caseId} onUploaded={load} />
          ) : null}

          {study.images.length > 0 && user?.role !== "administrator" ? (
            <Card className="overflow-hidden">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
                <ViewerToolbar
                  activeTool={tool}
                  onToolChange={setTool}
                  onReset={() => setResetSignal((value) => value + 1)}
                />
                {xray ? (
                  <div className="flex flex-wrap gap-1">
                    {xray.regions.map((region) => (
                      <button
                        key={region.image_id}
                        type="button"
                        onClick={() => setActiveImageId(region.image_id)}
                        className={`focus-ring rounded-md px-2.5 py-1.5 text-[11px] font-medium ${
                          activeImageId === region.image_id
                            ? "bg-slate-900 text-white"
                            : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                        }`}
                      >
                        {region.body_part ?? "image"}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>

              {mammogram ? (
                <MammogramGrid
                  exam={mammogram}
                  tool={tool}
                  resetSignal={resetSignal}
                />
              ) : activeImage ? (
                <ImageViewer
                  imageId={activeImage.id}
                  label={(activeImage.body_part_raw ?? activeImage.body_part ?? "Image").toUpperCase()}
                  caption={activeImage.mime === "application/dicom" ? "DICOM" : activeImage.mime.replace("image/", "").toUpperCase()}
                  activeTool={tool}
                  resetSignal={resetSignal}
                  className="h-[560px] w-full"
                />
              ) : null}
            </Card>
          ) : null}

          {mammogram ? <ExamNotes exam={mammogram} /> : null}

          {study.images.length > 0 && canUpload ? (
            <details className="rounded-xl border border-slate-200 bg-white">
              <summary className="cursor-pointer px-5 py-3 text-sm font-medium text-slate-700">
                Add more images to this study
              </summary>
              <div className="border-t border-slate-100 p-3">
                <UploadPanel caseId={caseId} onUploaded={load} />
              </div>
            </details>
          ) : null}
        </div>

        <div className="space-y-4">
          {activeImage ? <CapabilityCard image={activeImage} onSubmit={submitAnalysis} busy={submitting} error={submitError} /> : null}
          {activeImage && jobs[activeImage.id] ? <JobCard caseId={caseId} job={jobs[activeImage.id]} /> : null}
          {activeImage ? <DeidCard image={activeImage} /> : null}
          {study.images.length > 1 ? <ImageList images={study.images} activeId={activeImage?.id ?? null} onSelect={setActiveImageId} /> : null}
        </div>
      </div>
    </div>
  );
}

function MammogramGrid({
  exam,
  tool,
  resetSignal,
}: {
  exam: MammogramExam;
  tool: ViewerTool;
  resetSignal: number;
}) {
  const panes = [
    { key: "LCC", image: exam.by_view.LCC, position: "Left cranio-caudal" },
    { key: "RCC", image: exam.by_view.RCC, position: "Right cranio-caudal" },
    { key: "LMLO", image: exam.by_view.LMLO, position: "Left medio-lateral oblique" },
    { key: "RMLO", image: exam.by_view.RMLO, position: "Right medio-lateral oblique" },
  ];
  return (
    <div className="viewer-grid grid-cols-1 md:grid-cols-2">
      {panes.map((pane) => (
        <ImageViewer
          key={pane.key}
          imageId={pane.image?.id ?? null}
          label={pane.key}
          caption={pane.position}
          activeTool={tool}
          resetSignal={resetSignal}
          className="h-[300px] w-full lg:h-[360px]"
        />
      ))}
    </div>
  );
}

function ExamNotes({ exam }: { exam: MammogramExam }) {
  const notes: string[] = [];
  if (!exam.complete) notes.push(`Incomplete four-view study. Missing: ${exam.missing.join(", ") || "—"}.`);
  if (exam.duplicates.length > 0) notes.push(`Duplicate views uploaded: ${exam.duplicates.join(", ")}. Only one of each is shown.`);
  if (exam.unassigned.length > 0) notes.push(`${exam.unassigned.length} image(s) could not be assigned to a view.`);
  if (notes.length === 0) return null;
  return (
    <Card className="border-amber-200 bg-amber-50 p-4 text-xs leading-relaxed text-amber-800">
      {notes.map((note) => (
        <p key={note}>{note}</p>
      ))}
    </Card>
  );
}

function CapabilityCard({
  image,
  onSubmit,
  busy,
  error,
}: {
  image: ImageSummary;
  onSubmit: (image: ImageSummary) => void;
  busy: boolean;
  error: string | null;
}) {
  const validation = image.validation;
  const capability = validation?.capability;
  const region = validation?.region_or_view?.value ?? "unrecognised";
  const isMammogram = image.modality === "mammogram";
  const supported = Boolean(capability?.supported) && region === "chest";

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900">Analysis</h2>
        <Badge tone={supported ? "good" : "warn"}>{isMammogram ? "viewing only" : supported ? "available" : "not available"}</Badge>
      </div>

      <dl className="mt-3 space-y-2 text-xs">
        <Row label="Modality" value={validation?.modality?.value ?? image.modality ?? "—"} />
        <Row label="Region / view" value={regionLabel(region, image)} />
        <Row label="Model task" value={capability?.task?.replaceAll("_", " ") ?? "—"} />
      </dl>

      {isMammogram ? (
        <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs leading-relaxed text-slate-600">
          Mammograms are supported for four-view viewing and reporting. No mammography classifier is
          enabled in this release, so no diagnosis is generated.
        </p>
      ) : supported ? (
        <button
          type="button"
          onClick={() => onSubmit(image)}
          disabled={busy}
          className="focus-ring mt-4 w-full rounded-lg bg-clinical-600 px-3 py-2 text-sm font-semibold text-white hover:bg-clinical-700 disabled:opacity-60"
        >
          {busy ? "Starting…" : "Run chest analysis"}
        </button>
      ) : (
        <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-xs leading-relaxed text-slate-600">
          {image.body_part_raw ? (
            <>
              “{image.body_part_raw}” is outside this model’s validated scope. The image is stored and
              viewable, but no AI result is produced.
            </>
          ) : (
            <>The body region could not be resolved, so the analysis is disabled rather than guessing.</>
          )}
        </p>
      )}

      {error ? <p className="mt-3 text-xs text-rose-600">{error}</p> : null}
    </Card>
  );
}

function JobCard({ caseId, job }: { caseId: string; job: Job }) {
  const percent = Math.round((job.progress ?? 0) * 100);
  const tone = job.state === "failed" ? "bad" : job.state === "completed" ? "good" : "info";
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900">Analysis job</h2>
        <Badge tone={tone}>{job.state}</Badge>
      </div>
      <p className="mt-1 font-mono text-[11px] text-slate-400">{job.job_id}</p>
      {job.state !== "completed" && job.state !== "failed" ? (
        <div className="mt-3">
          <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-clinical-500 transition-all" style={{ width: `${percent}%` }} />
          </div>
          <p className="mt-1 text-[11px] text-slate-500">
            {job.state === "queued" ? "Queued — waiting for the CPU worker." : `Running · ${percent}%`}
          </p>
        </div>
      ) : null}
      {job.error ? (
        <p className="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">
          {job.error.code}: {job.error.detail}
        </p>
      ) : null}
      {job.state === "completed" ? (
        <Link
          to={`/cases/${caseId}/results/${job.job_id}`}
          className="focus-ring mt-3 block rounded-lg bg-slate-900 px-3 py-2 text-center text-sm font-semibold text-white hover:bg-slate-800"
        >
          View result and heatmap
        </Link>
      ) : null}
      <p className="mt-3 text-[10px] text-slate-400">
        Model {job.model_id} · {job.model_version}
      </p>
    </Card>
  );
}

function DeidCard({ image }: { image: ImageSummary }) {
  const receipt = image.deid_receipt as DeidReceipt | undefined;
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-900">De-identification</h2>
        <Badge tone="good">applied before storage</Badge>
      </div>
      {receipt?.pipeline ? (
        <>
          <dl className="mt-3 space-y-2 text-[11px]">
            <Row label="Pipeline" value={receipt.pipeline} mono />
            <Row label="Original sha256" value={shortDigest(receipt.sha256_in, 20)} mono />
            <Row label="Stored sha256" value={shortDigest(receipt.sha256_out, 20)} mono />
            <Row label="Removed" value={`${receipt.removed.length} attributes`} />
            <Row label="Replaced" value={`${receipt.replaced.length} attributes`} />
            <Row label="UIDs remapped" value={String(receipt.uids_remapped)} />
            <Row label="Re-identification key" value={receipt.reidentification_key_retained ? "retained" : "not retained"} />
          </dl>
          {receipt.warnings.length > 0 ? (
            <ul className="mt-3 list-disc space-y-1 pl-4 text-[11px] text-amber-700">
              {receipt.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          ) : null}
        </>
      ) : (
        <p className="mt-2 text-xs text-slate-500">No receipt available.</p>
      )}
    </Card>
  );
}

function ImageList({
  images,
  activeId,
  onSelect,
}: {
  images: ImageSummary[];
  activeId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <Card className="p-5">
      <h2 className="text-sm font-semibold text-slate-900">Images</h2>
      <ul className="mt-3 divide-y divide-slate-100">
        {images.map((image) => (
          <li key={image.id}>
            <button
              type="button"
              onClick={() => onSelect(image.id)}
              className={`focus-ring flex w-full items-center justify-between gap-2 py-2 text-left text-xs ${
                image.id === activeId ? "text-clinical-700" : "text-slate-600"
              }`}
            >
              <span className="truncate">
                {image.body_part_raw ?? image.body_part ?? "image"}
                {image.laterality ? ` · ${image.laterality}${image.view ?? ""}` : ""}
              </span>
              <span className="shrink-0 font-mono text-[10px] text-slate-400">
                {image.rows && image.cols ? `${image.cols}×${image.rows}` : ""}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Row({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="shrink-0 text-slate-400">{label}</dt>
      <dd className={`text-right text-slate-700 ${mono ? "font-mono text-[10px]" : ""}`}>{value}</dd>
    </div>
  );
}

function regionLabel(region: string, image: ImageSummary): string {
  if (image.laterality && image.view) return `${image.laterality}${image.view}`;
  return REGION_LABEL[region] ?? region;
}
