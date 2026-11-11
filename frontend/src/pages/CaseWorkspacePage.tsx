import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  api,
  ApiError,
  downloadWithAuth,
  type CaseDetail,
  type DeidReceipt,
  type ExamSummary,
  type Finding,
  type FindingReview,
  type ImageSummary,
  type Job,
  type MammogramExam,
  type ModelEntry,
  type Provenance,
  type ResultDocument,
  type ReviewDecision,
} from "../api/client";
import { hasRole, useAuth } from "../auth/AuthContext";
import { PatientBanner } from "../components/patient/PatientBanner";
import { StudyViewer, type CamState } from "../components/viewer/StudyViewer";
import { ViewStrip, type StudyView } from "../components/viewer/ViewStrip";
import type { CamOverlay } from "../components/viewer/cam";
import { cachedHeatmap, loadHeatmap, prefetchHeatmap } from "../components/viewer/heatmaps";
import { UploadPanel } from "../components/UploadPanel";
import { Icon } from "../components/icons";
import {
  DECISION_SUPPORT_NOTICE,
  DEID_NOTICE,
  OVERLAY_NOTICE,
  ScreenWarning,
  TB_NOTICE,
} from "../components/ScreenWarning";
import {
  Badge,
  Button,
  Dialog,
  EmptyState,
  ErrorNote,
  Expander,
  Notice,
  PageHeader,
  Panel,
  PanelHeader,
  Skeleton,
  Textarea,
  cx,
  formatDate,
  prettyLabel,
  relativeTime,
  shortDigest,
  useToast,
} from "../components/ui";

const MAMMOGRAM_VIEWS = ["LCC", "RCC", "LMLO", "RMLO"] as const;
const MAMMOGRAM_CAPTION: Record<string, string> = {
  LCC: "Left CC",
  RCC: "Right CC",
  LMLO: "Left MLO",
  RMLO: "Right MLO",
};

const BAND_TONE: Record<string, "signal" | "neutral" | "outline"> = {
  above_threshold: "signal",
  borderline: "neutral",
  below_threshold: "outline",
};

const GENERIC_WARNING = /^(Decision support only|The heatmap shows|Model:)/i;
const DENSITY_LABELS = new Set(["A", "B", "C", "D"]);

export function CaseWorkspacePage() {
  const { caseId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();
  const toast = useToast();

  const [study, setStudy] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeImageId, setActiveImageId] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [result, setResult] = useState<ResultDocument | null>(null);
  const [resultLoading, setResultLoading] = useState(false);
  const [resultError, setResultError] = useState<string | null>(null);
  const [provenance, setProvenance] = useState<Provenance | null>(null);
  const [selectedFinding, setSelectedFinding] = useState<number | null>(null);
  const [cam, setCam] = useState<CamOverlay | null>(null);
  const [camState, setCamState] = useState<CamState>("idle");
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [viewerDefaults, setViewerDefaults] = useState({ opacity: 0.85, split: false });
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [report, setReport] = useState<{ report_id: string; created_at: string; url: string } | null>(null);
  const [reportBusy, setReportBusy] = useState(false);
  const [includeIdentity, setIncludeIdentity] = useState(false);
  const [reviewBusy, setReviewBusy] = useState<number | null>(null);
  const [reviewError, setReviewError] = useState<{ index: number; message: string } | null>(null);
  const [noteTarget, setNoteTarget] = useState<number | null>(null);
  const [noteDraft, setNoteDraft] = useState("");
  const [noteBusy, setNoteBusy] = useState<number | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [findingsOpen, setFindingsOpen] = useState(false);
  const [examSummary, setExamSummary] = useState<ExamSummary | null>(null);
  const [examBusy, setExamBusy] = useState(false);
  const [examPolling, setExamPolling] = useState(false);
  const loadedCase = useRef<string | null>(null);

  const isAdmin = user?.role === "administrator";
  const canAnalyze = hasRole(user, "clinician", "researcher");
  const canReview = user?.role === "clinician";
  const canUpload = hasRole(user, "clinician", "researcher");

  const load = useCallback(
    async (jobOverride?: string) => {
      setError(null);
      try {
        const payload = await api.getCase(caseId);
        setStudy(payload);
        setActiveImageId((current) => {
          if (current && payload.images.some((image) => image.id === current)) return current;
          return payload.images[0]?.id ?? null;
        });

        if (isAdmin) {
          setJob(null);
          return;
        }
        const requested = jobOverride ?? searchParams.get("result");
        const jobId = requested || payload.last_job?.id;
        if (jobId) {
          api
            .getJob(jobId)
            .then(setJob)
            .catch(() => setJob(null));
        } else {
          setJob(null);
        }
      } catch (caught) {
        setError(caught instanceof ApiError ? caught.message : "Could not load this study");
      }
    },
    // The URL result is read once; later URL changes are handled by selectFinding.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [caseId, isAdmin],
  );

  useEffect(() => {
    if (loadedCase.current === caseId) return;
    loadedCase.current = caseId;
    void load();
  }, [caseId, load]);

  useEffect(() => {
    if (!caseId) return;
    window.localStorage.setItem("miap.last-case", caseId);
  }, [caseId]);

  useEffect(() => {
    api
      .listModels()
      .then(setModels)
      .catch(() => undefined);
    api
      .getSettings()
      .then((settings) => {
        setViewerDefaults({
          opacity: settings.viewer_defaults.overlay_opacity,
          split: settings.viewer_defaults.split_view,
        });
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!job || (job.state !== "queued" && job.state !== "running")) return;
    const timer = window.setInterval(() => {
      api
        .getJob(job.job_id)
        .then(setJob)
        .catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.state]);

  useEffect(() => {
    if (!job || job.state !== "completed") {
      if (job && job.state !== "completed") {
        setResult(null);
        setProvenance(null);
      }
      return;
    }
    let cancelled = false;
    setResultLoading(true);
    setResultError(null);
    Promise.all([api.getResult(job.job_id), api.getProvenance(job.job_id).catch(() => null)])
      .then(([document, record]) => {
        if (cancelled) return;
        setResult(document);
        setProvenance(record);
        setActiveImageId(document.image_id);
      })
      .catch((caught) => {
        if (cancelled) return;
        setResultError(caught instanceof ApiError ? caught.detail || caught.message : "Could not load the result");
      })
      .finally(() => {
        if (!cancelled) setResultLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [job?.job_id, job?.state]);

  useEffect(() => {
    if (!result) {
      setSelectedFinding(null);
      setCam(null);
      setCamState("idle");
      return;
    }
    const fromUrl = Number(searchParams.get("finding"));
    const valid = Number.isInteger(fromUrl) && fromUrl >= 0 && fromUrl < result.findings.length;
    setSelectedFinding(valid ? fromUrl : (result.primary_finding_index ?? 0));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result?.result_id]);

  useEffect(() => {
    if (!result || selectedFinding == null) {
      setCam(null);
      setCamState("idle");
      return;
    }
    const cached = cachedHeatmap(result.result_id, selectedFinding);
    if (cached) {
      setCam(cached);
      setCamState("ready");
      return;
    }
    let cancelled = false;
    setCam(null);
    setCamState("loading");
    loadHeatmap(result.result_id, selectedFinding, result.heatmap_mapping ?? "centre")
      .then((overlay) => {
        if (cancelled) return;
        setCam(overlay);
        setCamState("ready");
      })
      .catch(() => {
        if (cancelled) return;
        setCam(null);
        setCamState("none");
      });
    return () => {
      cancelled = true;
    };
  }, [result?.result_id, selectedFinding]);

  const images = study?.images ?? [];
  const mammogram = study?.exam?.type === "mammogram_four_view" ? (study.exam as MammogramExam) : null;
  const activeImage = useMemo(
    () => images.find((image) => image.id === activeImageId) ?? images[0] ?? null,
    [images, activeImageId],
  );
  const views = useMemo<StudyView[]>(() => {
    if (mammogram) {
      return MAMMOGRAM_VIEWS.map((label) => {
        const image = mammogram.by_view[label] ?? null;
        return { id: image?.id ?? `missing-${label}`, label, caption: MAMMOGRAM_CAPTION[label], image };
      });
    }
    return images.map((image, index) => ({
      id: image.id,
      label: viewLabel(image, index),
      caption: image.laterality ? `${image.laterality}${image.view ?? ""}` : (image.body_part ?? "X-ray"),
      image,
    }));
  }, [images, mammogram]);

  const model = useMemo(() => {
    if (!result) return null;
    return (
      models.find((entry) => entry.model_id === result.model.name && entry.version === result.model.version) ??
      null
    );
  }, [models, result]);

  useEffect(() => {
    if (!study || study.exam?.type !== "mammogram_four_view" || isAdmin) {
      setExamSummary(null);
      return;
    }
    let cancelled = false;
    api
      .getExamSummary(caseId)
      .then((summary) => {
        if (!cancelled) setExamSummary(summary);
      })
      .catch(() => {
        if (!cancelled) setExamSummary(null);
      });
    return () => {
      cancelled = true;
    };
  }, [caseId, isAdmin, study?.exam?.type, study?.images.length, job?.state]);

  useEffect(() => {
    if (!examPolling) return;
    const timer = window.setInterval(() => {
      api
        .getExamSummary(caseId)
        .then((summary) => {
          setExamSummary(summary);
          const pending = Object.values(summary.views).filter(
            (view) => view.result_id === null && view.view,
          );
          if (pending.length === 0) setExamPolling(false);
        })
        .catch(() => undefined);
    }, 2500);
    const stop = window.setTimeout(() => setExamPolling(false), 120000);
    return () => {
      window.clearInterval(timer);
      window.clearTimeout(stop);
    };
  }, [caseId, examPolling]);

  const capability = activeImage?.validation?.capability;
  const capabilityBucket =
    capability?.bucket ?? (activeImage?.modality === "mammogram" ? "mammogram_density" : undefined);
  const approvedForBucket = capabilityBucket
    ? models.some(
        (entry) => entry.state === "approved" && (entry.capabilities ?? []).includes(capabilityBucket),
      )
    : true;
  const analyzeSupported = Boolean(capability?.supported) && approvedForBucket;
  const examSupported = models.some(
    (entry) => entry.state === "approved" && (entry.capabilities ?? []).includes("mammogram_density"),
  );
  const toReview = result?.review_summary.findings_to_review ?? 0;
  const reviewed = result?.review_summary.reviewed ?? 0;
  const activeView = views.find((view) => view.image?.id === result?.image_id) ?? null;
  const jobActive = job?.state === "queued" || job?.state === "running";
  const examSingleView = Boolean(examSummary?.breasts.L.single_view || examSummary?.breasts.R.single_view);

  function selectFinding(index: number) {
    setSelectedFinding(index);
    const next = new URLSearchParams(searchParams);
    if (job) next.set("result", job.job_id);
    next.set("finding", String(index));
    setSearchParams(next, { replace: true });
  }

  function stepView(delta: number) {
    const present = views.filter((view) => view.image);
    if (present.length < 2) return;
    const from = present.findIndex((view) => view.image?.id === activeImage?.id);
    const next = present[(Math.max(0, from) + delta + present.length) % present.length];
    if (next.image) setActiveImageId(next.image.id);
  }

  async function submitAnalysis() {
    if (!activeImage) return;
    setSubmitting(true);
    setSubmitError(null);
    setReport(null);
    try {
      const created = await api.submitAnalysis(
        { case_id: caseId, image_id: activeImage.id },
        crypto.randomUUID(),
      );
      setJob(created);
      setResult(null);
      setProvenance(null);
      toast("Analysis queued", "info");
    } catch (caught) {
      setSubmitError(caught instanceof ApiError ? caught.detail || caught.message : "Analysis could not be started");
    } finally {
      setSubmitting(false);
    }
  }

  async function submitExamAnalysis() {
    setExamBusy(true);
    setSubmitError(null);
    setReport(null);
    try {
      const batch = await api.submitExam({ case_id: caseId });
      toast(`Exam queued: ${batch.total} view${batch.total === 1 ? "" : "s"}`, "info");
      setExamPolling(true);
    } catch (caught) {
      setSubmitError(
        caught instanceof ApiError ? caught.detail || caught.message : "Exam analysis could not be started",
      );
    } finally {
      setExamBusy(false);
    }
  }

  async function saveReview(
    finding: Finding,
    decision: ReviewDecision,
    note?: string,
    message?: string,
  ): Promise<boolean> {
    if (!result) return false;
    setReviewBusy(finding.index);
    setReviewError(null);
    try {
      const saved = await api.reviewFinding(result.result_id, finding.index, decision, note);
      setResult((current) => (current ? applyReview(current, saved, note) : current));
      toast(message ?? (decision === "confirmed" ? "Finding confirmed" : "Finding dismissed"), "success");
      setNoteTarget(null);
      return true;
    } catch (caught) {
      setReviewError({
        index: finding.index,
        message: caught instanceof ApiError ? caught.detail || caught.message : "Review could not be saved",
      });
      return false;
    } finally {
      setReviewBusy(null);
    }
  }

  function toggleNote(finding: Finding) {
    setReviewError(null);
    setNoteTarget((current) => (current === finding.index ? null : finding.index));
    setNoteDraft(finding.review?.note ?? "");
  }

  async function saveNote(finding: Finding) {
    if (!finding.review) return;
    setNoteBusy(finding.index);
    const text = noteDraft.trim();
    await saveReview(finding, finding.review.decision, text, text ? "Note saved" : "Note removed");
    setNoteBusy(null);
  }

  async function createReport() {
    setReportBusy(true);
    setSubmitError(null);
    try {
      const created = await api.createReport(caseId, job?.job_id, includeIdentity);
      setReport(created);
      await downloadWithAuth(created.url, `miap-report-${created.report_id}.pdf`);
    } catch (caught) {
      setSubmitError(caught instanceof ApiError ? caught.detail || caught.message : "Report could not be generated");
    } finally {
      setReportBusy(false);
    }
  }

  if (error) {
    return (
      <div>
        <PageHeader title="Study" />
        <ErrorNote message={error} />
        <Link to={backTo(user?.role)} className="mt-4 inline-block text-sm text-petrol hover:underline">
          Back to {backLabel(user?.role)}
        </Link>
      </div>
    );
  }

  if (!study) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-7 w-52" />
        <div className="grid gap-4 xl:grid-cols-[260px_minmax(0,1fr)_380px]">
          <Skeleton className="h-40 rounded-xl" />
          <Skeleton className="h-[26rem] rounded-xl" />
          <Skeleton className="h-72 rounded-xl" />
        </div>
      </div>
    );
  }

  return (
    <div className="xl:relative xl:z-40 xl:-mb-14 xl:-mt-7 xl:flex xl:h-[calc(100vh-1.75rem)] xl:flex-col">
      <div className="mb-4">
        <Link
          to={backTo(user?.role)}
          className="mb-2 inline-block text-xs text-muted transition-colors duration-150 ease-out hover:text-ink"
        >
          ← Back to {backLabel(user?.role)}
        </Link>
        <h1 className="text-2xl font-semibold leading-tight text-ink">Study workspace</h1>
      </div>

      <div
        className={cx(
          "grid gap-4 xl:min-h-0 xl:flex-1",
          isAdmin ? "xl:grid-cols-[260px_minmax(0,1fr)]" : "xl:grid-cols-[260px_minmax(0,1fr)_380px]",
        )}
      >
        <div className="flex min-w-0 flex-col gap-3 xl:min-h-0 xl:pr-1">
          <PatientBanner
            patient={study.patient}
            pseudonym={study.pseudonym}
            consent={study.consent}
            identityVisible={study.identity_visible}
          />
          <StudyFacts study={study} activeImage={activeImage} />
          <div className="min-w-0 space-y-3 xl:min-h-0 xl:flex-1 xl:overflow-y-auto xl:pb-4">
            {!isAdmin ? (
              <Panel className="p-4">
                <ViewStrip
                  views={views}
                  activeId={activeImage?.id ?? null}
                  onSelect={setActiveImageId}
                  onPrev={() => stepView(-1)}
                  onNext={() => stepView(1)}
                />
              </Panel>
            ) : null}
            {!isAdmin ? (
              <ScreenWarning
                items={[
                  DECISION_SUPPORT_NOTICE,
                  /chest|thorax/i.test(
                    `${activeImage?.body_part ?? ""} ${result?.region_or_view.value ?? ""}`,
                  )
                    ? TB_NOTICE
                    : null,
                  OVERLAY_NOTICE,
                  DEID_NOTICE,
                  ...(result?.warnings ?? []).filter((warning) => !GENERIC_WARNING.test(warning)),
                  examSummary?.caveat,
                  examSingleView
                    ? "One view carries this breast's category. Single-view density is less reliable than a complete four-view exam."
                    : null,
                ]}
              />
            ) : null}
          </div>
        </div>

        <div className="flex min-w-0 flex-col gap-3 xl:min-h-0">
          {isAdmin ? (
            <Notice tone="signal" icon="lock">
              Administrators see study metadata only. Image pixels, findings and clinical reports are not
              available for this role by design.
            </Notice>
          ) : images.length === 0 ? (
            canUpload ? (
              <UploadPanel caseId={caseId} onUploaded={() => void load()} />
            ) : (
              <Panel>
                <EmptyState icon="image" title="No images in this study" />
              </Panel>
            )
          ) : (
            <>
              <Panel className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
                <div className="pointer-events-none absolute inset-x-0 top-3 z-20 flex items-center justify-center gap-1.5 px-3">
                  <span className="pointer-events-auto truncate rounded-md bg-viewer/85 px-2.5 py-1 text-xs text-viewer-ink backdrop-blur">
                    {activeImage?.modality ? prettyLabel(activeImage.modality) : "Image"}
                    {result ? ` · ${activeView?.label ?? "result view"}` : ""}
                  </span>
                  {canUpload ? (
                    <button
                      type="button"
                      onClick={() => setUploadOpen(true)}
                      className="pointer-events-auto flex h-7 shrink-0 items-center gap-1 rounded-md bg-viewer/85 px-2 text-xs font-medium text-viewer-ink backdrop-blur transition-colors duration-150 ease-out hover:bg-viewer"
                    >
                      <Icon name="plus" size={13} />
                      Images
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => setFindingsOpen(true)}
                    className="pointer-events-auto flex h-7 shrink-0 items-center gap-1.5 rounded-md bg-viewer/85 px-2 text-xs font-medium text-viewer-ink backdrop-blur xl:hidden"
                  >
                    <Icon name="heat" size={13} />
                    Findings{toReview > 0 ? ` (${toReview - reviewed})` : ""}
                  </button>
                </div>
                <div className="min-h-0 flex-1 p-2">
                  <StudyViewer
                    fill
                    caseId={study.id}
                    views={views}
                    grid={Boolean(mammogram)}
                    activeImageId={activeImage?.id ?? null}
                    onActiveImage={setActiveImageId}
                    patientLabel={study.patient?.name ?? study.pseudonym}
                    modality={activeImage?.modality ?? "image"}
                    resultImageId={result?.image_id ?? null}
                    cam={cam}
                    camState={camState}
                    defaultOpacity={viewerDefaults.opacity}
                    defaultSplit={viewerDefaults.split}
                  />
                </div>
              </Panel>

              {result && activeImage && result.image_id !== activeImage.id ? (
                <Notice tone="neutral" icon="info">
                  This result belongs to the {activeView?.label ?? "analysed"} view.{" "}
                  <button
                    type="button"
                    className="font-medium text-petrol hover:underline"
                    onClick={() => setActiveImageId(result.image_id)}
                  >
                    Show that view
                  </button>
                </Notice>
              ) : null}
            </>
          )}
        </div>

        {!isAdmin ? (
          <>
            {findingsOpen ? (
              <div
                className="fixed inset-0 z-30 bg-viewer/40 xl:hidden"
                onClick={() => setFindingsOpen(false)}
                aria-hidden="true"
              />
            ) : null}
            <aside
              id="findings-panel"
              className={cx(
                "min-w-0 space-y-3",
                findingsOpen
                  ? "fixed inset-x-0 bottom-14 z-40 max-h-[74vh] overflow-y-auto rounded-t-xl border-t border-rule bg-paper px-4 py-4 shadow-2xl"
                  : "hidden",
                "xl:static xl:z-auto xl:block xl:max-h-none xl:min-h-0 xl:overflow-y-auto xl:rounded-none xl:border-0 xl:bg-transparent xl:p-0 xl:pr-1 xl:pb-4 xl:shadow-none",
              )}
            >
              <div className="flex items-center justify-between gap-2 xl:hidden">
                <h2 className="text-base font-semibold text-ink">Findings</h2>
                <button
                  type="button"
                  onClick={() => setFindingsOpen(false)}
                  aria-label="Close findings"
                  className="flex h-9 w-9 items-center justify-center rounded-md text-muted hover:bg-surface-2"
                >
                  <Icon name="close" size={18} />
                </button>
              </div>

              {mammogram ? (
                <ExamSummaryPanel
                  summary={examSummary}
                  supported={examSupported}
                  canAnalyze={canAnalyze}
                  busy={examBusy}
                  onAnalyse={submitExamAnalysis}
                  onSelectView={setActiveImageId}
                />
              ) : null}

              <Panel>
                <PanelHeader
                  title="Findings to review"
                  note={
                    result
                      ? `${reviewed} of ${toReview} reviewed${model ? ` · ${model.state}` : ""}`
                      : jobActive
                        ? "Analysis in progress"
                        : "No analysis yet"
                  }
                  actions={
                    canAnalyze && !jobActive && (analyzeSupported || result) ? (
                      <Button size="sm" icon="bolt" loading={submitting} onClick={submitAnalysis}>
                        {result ? "Re-run" : "Analyse"}
                      </Button>
                    ) : null
                  }
                />
                <div className="px-4 py-4">
                  {resultLoading ? (
                    <div className="space-y-3">
                      <Skeleton className="h-3.5 w-3/4" />
                      <Skeleton className="h-14 w-full" />
                      <Skeleton className="h-14 w-full" />
                    </div>
                  ) : jobActive && job ? (
                    <JobProgress job={job} />
                  ) : job?.state === "failed" ? (
                    <div className="space-y-3">
                      <ErrorNote message={job.error?.detail ?? "The analysis failed."} />
                      {analyzeSupported ? (
                        <Button variant="primary" icon="bolt" onClick={submitAnalysis} loading={submitting}>
                          Try again
                        </Button>
                      ) : null}
                    </div>
                  ) : result ? (
                    <FindingsList
                      result={result}
                      selected={selectedFinding}
                      canReview={canReview}
                      researcher={user?.role === "researcher"}
                      reviewed={reviewed}
                      toReview={toReview}
                      reviewBusy={reviewBusy}
                      reviewError={reviewError}
                      noteTarget={noteTarget}
                      noteDraft={noteDraft}
                      noteBusy={noteBusy}
                      onDraft={setNoteDraft}
                      onSelect={selectFinding}
                      onPrefetch={(index) => {
                        const finding = result.findings[index];
                        if (finding && finding.band !== "below_threshold") {
                          prefetchHeatmap(result.result_id, index, result.heatmap_mapping ?? "centre");
                        }
                      }}
                      onReview={(finding, decision) => void saveReview(finding, decision)}
                      onToggleNote={toggleNote}
                      onSaveNote={(finding) => void saveNote(finding)}
                    />
                  ) : (
                    <div className="space-y-3">
                      <EmptyState icon="heat" title="No analysis for this study yet" />
                      {analyzeSupported ? (
                        <Button
                          variant="primary"
                          icon="bolt"
                          loading={submitting}
                          onClick={submitAnalysis}
                          className="w-full"
                        >
                          Run {activeImage?.modality === "mammogram" ? "analysis" : "chest analysis"}
                        </Button>
                      ) : (
                        <Notice tone="neutral" icon="info">
                          {activeImage?.modality === "mammogram"
                            ? "No approved breast-density model is available in this release. The image is stored and can be reviewed."
                            : capabilityBucket === "unrecognised"
                              ? "No body region is recorded for this image, so no model can be selected. Re-upload it with a body part such as knee, wrist or chest."
                              : "No approved model covers this body region in this release. The image is stored and viewable, but no AI result is produced."}
                        </Notice>
                      )}
                    </div>
                  )}
                  <ErrorNote message={resultError} />
                  <ErrorNote message={submitError} />
                </div>
              </Panel>

              <TechnicalPanel result={result} provenance={provenance} image={activeImage} job={job} />

              {canAnalyze ? (
                <Panel className="px-4 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-ink">Report</p>
                      <p className="text-xs text-muted">
                        {report
                          ? `Created ${formatDate(report.created_at)}`
                          : user?.role === "researcher"
                            ? "Pseudonymised research PDF"
                            : includeIdentity
                              ? "Clinical PDF with identity"
                              : "De-identified clinical PDF"}
                      </p>
                    </div>
                    {report ? (
                      <Button
                        size="sm"
                        icon="download"
                        onClick={() => downloadWithAuth(report.url, `miap-report-${report.report_id}.pdf`)}
                      >
                        Download
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="primary"
                        icon="pdf"
                        loading={reportBusy}
                        disabled={!result}
                        onClick={createReport}
                      >
                        Create PDF
                      </Button>
                    )}
                  </div>
                  {!report && user?.role === "clinician" && study.identity_visible ? (
                    <label className="mt-3 flex items-start gap-2 border-t border-rule pt-3 text-xs leading-relaxed text-muted">
                      <input
                        type="checkbox"
                        checked={includeIdentity}
                        onChange={(event) => setIncludeIdentity(event.target.checked)}
                        className="mt-0.5 size-3.5 shrink-0 accent-petrol"
                      />
                      <span>
                        Include patient identity. This is audited; leave it off to keep the
                        report de-identified.
                      </span>
                    </label>
                  ) : null}
                </Panel>
              ) : null}
            </aside>
          </>
        ) : null}
      </div>

      <Dialog open={uploadOpen} onClose={() => setUploadOpen(false)} title="Add images">
        <UploadPanel
          caseId={caseId}
          onUploaded={() => {
            setUploadOpen(false);
            void load();
          }}
        />
      </Dialog>
    </div>
  );
}

/* ------------------------------------------------------------------ breast density */

function ExamSummaryPanel({
  summary,
  supported,
  canAnalyze,
  busy,
  onAnalyse,
  onSelectView,
}: {
  summary: ExamSummary | null;
  supported: boolean;
  canAnalyze: boolean;
  busy: boolean;
  onAnalyse: () => void;
  onSelectView: (imageId: string) => void;
}) {
  const views = summary ? Object.values(summary.views) : [];
  const scored = views.filter((view) => view.result_id).length;
  const pending = views.filter((view) => !view.result_id);

  return (
    <Panel>
      <PanelHeader
        title="Breast density"
        note={summary ? `${scored} of ${views.length} views scored · highest category per breast` : "Loading exam summary"}
        actions={
          canAnalyze ? (
            <Button
              size="sm"
              icon="bolt"
              loading={busy}
              disabled={!supported || pending.length === 0}
              onClick={onAnalyse}
            >
              {scored > 0 ? "Re-run exam" : "Analyse exam"}
            </Button>
          ) : null
        }
      />
      <div className="space-y-3 px-4 py-4">
        {summary ? (
          <>
            <div className="grid grid-cols-2 gap-x-5">
              {(["L", "R"] as const).map((side) => {
                const breast = summary.breasts[side];
                return (
                  <div key={side} className="border-t border-rule pt-2">
                    <p className="text-xs text-muted">{side === "L" ? "Left breast" : "Right breast"}</p>
                    <div className="mt-1 flex items-baseline gap-2">
                      <span className="text-2xl font-medium leading-none text-ink tabular-nums">
                        {breast.density ?? "—"}
                      </span>
                      {breast.density ? (
                        <Badge tone={breast.density === "C" || breast.density === "D" ? "signal" : "petrol"}>
                          {breast.density_text ?? "density"}
                        </Badge>
                      ) : (
                        <span className="text-xs text-muted">not scored</span>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-muted">
                      {breast.views_evaluated.length > 0
                        ? `from ${breast.views_evaluated.join(", ")}`
                        : breast.views_pending.length > 0
                          ? `pending ${breast.views_pending.join(", ")}`
                          : "no views in this exam"}
                    </p>
                  </div>
                );
              })}
            </div>

            {pending.length > 0 ? (
              <div className="flex flex-wrap gap-x-3 gap-y-1">
                {pending.map((view) => (
                  <button
                    key={view.image_id}
                    type="button"
                    onClick={() => onSelectView(view.image_id)}
                    className="text-xs text-petrol hover:underline"
                  >
                    {view.view || "view"} pending
                  </button>
                ))}
              </div>
            ) : null}

            {summary.missing.length > 0 ? (
              <p className="text-xs text-muted">Missing standard views: {summary.missing.join(", ")}.</p>
            ) : null}
          </>
        ) : (
          <p className="text-sm text-muted">The exam summary is not available yet.</p>
        )}

        {!supported ? (
          <Notice tone="neutral" icon="info">
            The breast-density model is registered as a candidate. Exam analysis stays disabled until it passes
            the local benchmark gate.
          </Notice>
        ) : null}
      </div>
    </Panel>
  );
}

/* ------------------------------------------------------------------ findings */

function FindingsList({
  result,
  selected,
  canReview,
  researcher,
  reviewed,
  toReview,
  reviewBusy,
  reviewError,
  noteTarget,
  noteDraft,
  noteBusy,
  onDraft,
  onSelect,
  onPrefetch,
  onReview,
  onToggleNote,
  onSaveNote,
}: {
  result: ResultDocument;
  selected: number | null;
  canReview: boolean;
  researcher: boolean;
  reviewed: number;
  toReview: number;
  reviewBusy: number | null;
  reviewError: { index: number; message: string } | null;
  noteTarget: number | null;
  noteDraft: string;
  noteBusy: number | null;
  onDraft: (value: string) => void;
  onSelect: (index: number) => void;
  onPrefetch: (index: number) => void;
  onReview: (finding: Finding, decision: ReviewDecision) => void;
  onToggleNote: (finding: Finding) => void;
  onSaveNote: (finding: Finding) => void;
}) {
  const percent = toReview > 0 ? Math.round((reviewed / toReview) * 100) : 0;
  const impression = result.impression;
  return (
    <div>
      {result.model.demo ? (
        <Notice tone="signal" icon="warn" className="mb-3">
          Demonstration model: not for clinical decisions.
        </Notice>
      ) : null}
      {result.degraded ? (
        <Notice tone="signal" icon="warn" className="mb-3">
          Experimental result outside the validated scope; treat it only as a prompt for review.
        </Notice>
      ) : null}
      {impression?.text ? (
        <div className="mb-4 border-l-2 border-petrol pl-3">
          <p className="text-xs font-medium text-petrol">Impression</p>
          <p className="mt-0.5 text-sm leading-snug text-ink">{impression.text}</p>
          {researcher && impression.probability != null ? (
            <p className="mt-1 font-mono text-xs text-muted">
              Top score {(impression.probability * 100).toFixed(1)}% · uncalibrated
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="mb-3">
        <div className="h-0.5 overflow-hidden rounded-full bg-surface-2">
          <div className="h-full rounded-full bg-petrol transition-[width] duration-200 ease-out" style={{ width: `${percent}%` }} />
        </div>
        <p className="mt-1.5 text-xs text-muted tabular-nums">
          {reviewed} of {toReview} flagged findings reviewed
          {reviewed >= toReview && toReview > 0 ? " · review complete" : ""}
        </p>
      </div>

      <ul className="border-t border-rule">
        {result.findings.map((finding) => (
          <li key={finding.index} className="border-b border-rule">
            <button
              type="button"
              onClick={() => onSelect(finding.index)}
              onMouseEnter={() => onPrefetch(finding.index)}
              onFocus={() => onPrefetch(finding.index)}
              aria-pressed={selected === finding.index}
              className={cx(
                "relative w-full px-1 py-3 text-left transition-colors duration-150 ease-out",
                selected === finding.index
                  ? "bg-petrol-soft/50 before:absolute before:inset-y-1 before:left-0 before:w-0.5 before:bg-petrol"
                  : "hover:bg-surface-2/60",
              )}
            >
              <span className="flex items-start justify-between gap-2">
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium text-ink">{finding.plain_label}</span>
                  {DENSITY_LABELS.has(finding.label) ? null : (
                    <span className="mt-0.5 block truncate text-xs text-muted">
                      suggests {finding.label.replace(/_/g, " ")}
                    </span>
                  )}
                  <span className="mt-0.5 block text-xs leading-snug text-muted">{finding.plain_sentence}</span>
                </span>
                <span className="flex shrink-0 flex-col items-end gap-1">
                  <Badge tone={BAND_TONE[finding.band] ?? "outline"}>{finding.band_label}</Badge>
                  {canReview && finding.review ? (
                    <Badge tone={finding.review.decision === "confirmed" ? "petrol" : "neutral"}>
                      {finding.review.decision === "confirmed" ? "Confirmed" : "Dismissed"}
                    </Badge>
                  ) : null}
                </span>
              </span>
              <span className="mt-2 flex items-center gap-2">
                <span className="h-1 flex-1 overflow-hidden rounded-full bg-surface-2">
                  <span
                    className={cx(
                      "block h-full rounded-full",
                      finding.band === "above_threshold"
                        ? "bg-signal"
                        : finding.band === "borderline"
                          ? "bg-petrol/60"
                          : "bg-petrol/25",
                    )}
                    style={{ width: `${Math.max(3, Math.round(finding.probability * 100))}%` }}
                  />
                </span>
                {researcher ? (
                  <span className="shrink-0 font-mono text-xs text-muted">
                    {(finding.probability * 100).toFixed(1)}% · T {finding.threshold.toFixed(2)}
                  </span>
                ) : null}
              </span>
            </button>

            {canReview ? (
              <div className="flex flex-wrap items-center gap-1 pb-2">
                <Button
                  size="sm"
                  variant="ghost"
                  icon="check"
                  loading={reviewBusy === finding.index}
                  onClick={() => onReview(finding, "confirmed")}
                >
                  Confirm
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  icon="close"
                  loading={reviewBusy === finding.index}
                  onClick={() => onReview(finding, "dismissed")}
                >
                  Dismiss
                </Button>
                {finding.review ? (
                  <Button size="sm" variant="ghost" icon="audit" onClick={() => onToggleNote(finding)}>
                    {finding.review.has_note ? "Note" : "Add note"}
                  </Button>
                ) : null}
                {finding.review?.note ? (
                  <span className="min-w-0 truncate pl-1 text-xs text-muted">“{finding.review.note}”</span>
                ) : null}
              </div>
            ) : null}

            {canReview && noteTarget === finding.index && finding.review ? (
              <div className="mb-3 space-y-1.5 pl-1">
                <Textarea
                  value={noteDraft}
                  maxLength={2000}
                  aria-label="Review note"
                  onChange={(event) => onDraft(event.target.value)}
                />
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-muted">Encrypted; visible only to you.</span>
                  <Button
                    size="sm"
                    variant="primary"
                    loading={noteBusy === finding.index}
                    onClick={() => onSaveNote(finding)}
                  >
                    Save note
                  </Button>
                </div>
              </div>
            ) : null}

            {reviewError?.index === finding.index ? (
              <div className="mt-1.5 pl-1">
                <ErrorNote message={reviewError.message} />
              </div>
            ) : null}
          </li>
        ))}
      </ul>

      {researcher ? (
        <p className="mt-3 border-t border-rule pt-3 text-xs leading-relaxed text-muted">
          Local agreement: {result.review_summary.confirmed} confirmed and {result.review_summary.dismissed}{" "}
          dismissed of {result.review_summary.findings_to_review} flagged findings. This measures reviewer
          agreement, not model accuracy. Review notes are not shown to research accounts.
        </p>
      ) : null}
    </div>
  );
}

/* --------------------------------------------------------------- study facts */

function StudyFacts({ study, activeImage }: { study: CaseDetail; activeImage: ImageSummary | null }) {
  return (
    <Panel>
      <PanelHeader title="Study" />
      <dl className="space-y-2 px-4 py-3 text-sm">
        <Row label="Status" value={study.status || "—"} />
        <Row label="Consent" value={study.consent.replaceAll("_", " ")} />
        <Row label="Modality" value={prettyLabel(study.modality ?? activeImage?.modality ?? "—")} />
        <Row label="Images" value={String(study.image_count)} />
        {activeImage?.rows && activeImage?.cols ? (
          <Row label="Matrix" value={`${activeImage.cols} × ${activeImage.rows}`} mono />
        ) : null}
        <Row label="AI status" value={study.ai_flag ?? "none"} />
        <Row label="Reviewed" value={`${study.reviewed} / ${study.findings_to_review}`} />
      </dl>
    </Panel>
  );
}

/* --------------------------------------------------------------- technical */

function TechnicalPanel({
  result,
  provenance,
  image,
  job,
}: {
  result: ResultDocument | null;
  provenance: Provenance | null;
  image: ImageSummary | null;
  job: Job | null;
}) {
  const receipt = image?.deid_receipt as DeidReceipt | undefined;
  const top = result?.findings.reduce<Finding | null>(
    (best, finding) => (!best || finding.probability > best.probability ? finding : best),
    null,
  );
  return (
    <Panel>
      <div className="px-4">
        <Expander title="Technical details">
          {result ? (
            <dl className="space-y-2 text-sm">
              <Row label="Model" value={`${result.model.name} ${result.model.version}`} />
              <Row label="Digest" value={shortDigest(result.model.digest, 20)} mono />
              <Row label="Top finding" value={top ? prettyLabel(top.label) : "—"} />
              <Row
                label="Raw score"
                value={
                  top ? `${(top.probability * 100).toFixed(1)}% · threshold ${top.threshold.toFixed(2)}` : "—"
                }
                mono
              />
              <Row label="Input region" value={String(result.region_or_view.value)} />
              <Row label="Result ID" value={result.result_id} mono />
              {provenance ? (
                <>
                  <Row label="Provenance" value={provenance.record_id} mono />
                  <Row
                    label="Runtime"
                    value={`${provenance.runtime.backend} · Python ${provenance.runtime.python}`}
                  />
                  <Row label="Code commit" value={provenance.code_commit} mono />
                  <Row label="Seed" value={String(provenance.seed)} />
                </>
              ) : null}
              <Row label="Job" value={job?.job_id ?? "—"} mono />
            </dl>
          ) : null}

          {result ? (
            <div className="mt-3 border-t border-rule pt-3">
              <p className="text-xs font-medium text-ink">Area maps</p>
              <ul className="mt-1.5 space-y-1 text-xs text-muted">
                {result.findings.map((finding) => (
                  <li key={finding.index} className="flex items-center justify-between gap-3">
                    <span className="truncate">
                      {finding.index}. {prettyLabel(finding.label)}
                    </span>
                    <span className="shrink-0 font-mono">
                      {finding.band === "below_threshold"
                        ? "not flagged"
                        : finding.heatmap?.path
                          ? "stored"
                          : "on demand"}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {receipt?.pipeline ? (
            <div className="mt-3 border-t border-rule pt-3">
              <p className="text-xs font-medium text-ink">De-identification</p>
              <dl className="mt-1.5 space-y-2 text-sm">
                <Row label="Pipeline" value={receipt.pipeline} mono />
                <Row label="Original hash" value={shortDigest(receipt.sha256_in, 20)} mono />
                <Row label="Stored hash" value={shortDigest(receipt.sha256_out, 20)} mono />
                <Row
                  label="Re-identification key"
                  value={receipt.reidentification_key_retained ? "retained" : "not retained"}
                />
                <Row label="Removed / replaced" value={`${receipt.removed.length} / ${receipt.replaced.length}`} />
              </dl>
              {receipt.warnings.length > 0 ? (
                <ul className="mt-2 space-y-1 text-xs text-signal">
                  {receipt.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </Expander>
      </div>
      <p className="border-t border-rule px-4 py-2 text-xs text-muted">
        Last updated {relativeTime(result?.created_at ?? job?.updated_at)}
      </p>
    </Panel>
  );
}

/* -------------------------------------------------------------------- misc */

function JobProgress({ job }: { job: Job }) {
  const percent = Math.round((job.progress ?? 0) * 100);
  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <Badge tone="petrol">{job.state}</Badge>
        <span className="font-mono text-xs text-muted">{percent}%</span>
      </div>
      <div className="mt-2 h-1 overflow-hidden rounded-full bg-surface-2">
        <div className="h-full rounded-full bg-petrol transition-[width] duration-200 ease-out" style={{ width: `${percent}%` }} />
      </div>
      <p className="mt-1 font-mono text-xs text-muted">{job.job_id}</p>
    </div>
  );
}

function Row({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className={cx("text-right text-ink", mono ? "font-mono text-xs" : "text-sm")}>{value}</dd>
    </div>
  );
}

function applyReview(document: ResultDocument, saved: FindingReview, note?: string): ResultDocument {
  const findings = document.findings.map((finding) =>
    finding.index === saved.finding_index
      ? {
          ...finding,
          review: {
            ...saved,
            note: note === undefined ? (finding.review?.note ?? null) : note || null,
            has_note: saved.has_note,
          },
        }
      : finding,
  );
  const flagged = findings.filter((finding) => finding.band !== "below_threshold");
  const decisions = flagged.filter((finding) => finding.review);
  return {
    ...document,
    findings,
    review_summary: {
      findings_to_review: flagged.length,
      reviewed: decisions.length,
      confirmed: decisions.filter((finding) => finding.review?.decision === "confirmed").length,
      dismissed: decisions.filter((finding) => finding.review?.decision === "dismissed").length,
    },
  };
}

function viewLabel(image: ImageSummary, index: number): string {
  if (image.laterality && image.view) return `${image.laterality}${image.view}`;
  if (image.body_part) return titleCase(image.body_part.replaceAll("_", " "));
  if (image.modality) return titleCase(`${image.modality} ${index + 1}`);
  return `View ${index + 1}`;
}

function titleCase(text: string): string {
  return text.replace(/\b[a-z]/g, (letter) => letter.toUpperCase());
}

function backTo(role: string | undefined): string {
  return role === "researcher" ? "/research" : "/worklist";
}

function backLabel(role: string | undefined): string {
  return role === "researcher" ? "dataset" : "worklist";
}
