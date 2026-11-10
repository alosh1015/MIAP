import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  api,
  ApiError,
  downloadWithAuth,
  type ModelEntry,
  type Provenance,
  type ResultDocument,
} from "../api/client";
import { ImageViewer, type CamOverlay } from "../components/ImageViewer";
import { ViewerToolbar } from "../components/ViewerToolbar";
import { Badge, Card, ErrorNote, PageHeader, formatDate, shortDigest } from "../components/ui";
import type { ViewerTool } from "../lib/cornerstone";
import { parseNpy } from "../lib/npy";

export function ResultsPage() {
  const { caseId = "", jobId = "" } = useParams();
  const [result, setResult] = useState<ResultDocument | null>(null);
  const [provenance, setProvenance] = useState<Provenance | null>(null);
  const [model, setModel] = useState<ModelEntry | null>(null);
  const [cam, setCam] = useState<CamOverlay | null>(null);
  const [showHeatmap, setShowHeatmap] = useState(true);
  const [tool, setTool] = useState<ViewerTool>("WindowLevel");
  const [resetSignal, setResetSignal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<{ report_id: string; created_at: string; url: string } | null>(null);
  const [reportBusy, setReportBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [document, record] = await Promise.all([api.getResult(jobId), api.getProvenance(jobId)]);
        if (cancelled) return;
        setResult(document);
        setProvenance(record);

        const models = await api.listModels();
        if (cancelled) return;
        setModel(models.find((entry) => entry.model_id === document.model.name) ?? null);

        if (record.result_id && document.heatmap) {
          const buffer = await api.getHeatmap(record.result_id);
          if (cancelled) return;
          const parsed = parseNpy(buffer);
          if (parsed.shape.length === 2) {
            setCam({ data: parsed.data, width: parsed.shape[1], height: parsed.shape[0] });
          }
        }
      } catch (caught) {
        if (!cancelled) {
          setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not load the result");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  async function createReport() {
    setReportBusy(true);
    setError(null);
    try {
      const created = await api.createReport(caseId, jobId);
      setReport(created);
      await downloadReport(created.url, created.report_id);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail || caught.message : "Report could not be generated");
    } finally {
      setReportBusy(false);
    }
  }

  async function downloadReport(url: string, reportId: string) {
    await downloadWithAuth(url, `miap-report-${reportId}.pdf`);
  }

  if (error) {
    return (
      <div>
        <PageHeader title="Result" subtitle={jobId} />
        <ErrorNote message={error} />
        <Link to={`/cases/${caseId}`} className="mt-4 inline-block text-sm text-clinical-700 hover:underline">
          Back to the study
        </Link>
      </div>
    );
  }

  if (!result || !provenance) {
    return <Card className="p-8 text-sm text-slate-500">Loading result…</Card>;
  }

  const classification = result.classification as { label?: string; probability?: number };
  const probability = typeof classification.probability === "number" ? classification.probability : 0;
  const findings = [...result.findings].sort((a, b) => b.probability - a.probability);
  const topLabel = classification.label ?? findings[0]?.label ?? "—";

  return (
    <div>
      <PageHeader
        title="Analysis result"
        subtitle={
          <span className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-mono text-slate-400">{result.model.name} · {result.model.version}</span>
            {result.model.demo ? <Badge tone="bad">demo model</Badge> : <Badge tone="good">model {shortDigest(result.model.digest)}</Badge>}
            <span className="text-slate-400">{formatDate(result.created_at)}</span>
          </span>
        }
        actions={
          <>
            <Link to={`/cases/${caseId}`} className="text-sm font-medium text-slate-500 hover:text-slate-800">
              Back to study
            </Link>
            <button
              type="button"
              onClick={report ? () => downloadReport(report.url, report.report_id) : createReport}
              disabled={reportBusy}
              className="focus-ring rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-60"
            >
              {reportBusy ? "Generating…" : report ? "Download report" : "Create PDF report"}
            </button>
          </>
        }
      />

      <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-relaxed text-amber-900">
        <strong className="font-semibold">Decision support only.</strong> This output is not a diagnosis and
        must not replace review by a qualified clinician. The heatmap shows where the model looked, not
        proof of a finding.
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 space-y-4">
          <Card className="overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
              <ViewerToolbar
                activeTool={tool}
                onToolChange={setTool}
                onReset={() => setResetSignal((value) => value + 1)}
                extras={
                  <button
                    type="button"
                    onClick={() => setShowHeatmap((value) => !value)}
                    disabled={!cam}
                    className={`focus-ring ml-1 rounded-md px-3 py-1.5 text-xs font-medium ${
                      showHeatmap && cam ? "bg-amber-500 text-white" : "text-slate-600 hover:bg-slate-100"
                    } disabled:opacity-40`}
                    title={cam ? "Toggle the Grad-CAM overlay" : "This result has no heatmap"}
                  >
                    Heatmap {showHeatmap && cam ? "on" : "off"}
                  </button>
                }
              />
              <span className="text-[11px] text-slate-400">{result.image_id}</span>
            </div>
            <ImageViewer
              imageId={result.image_id}
              label={String(result.region_or_view.value).toUpperCase()}
              caption={`${result.modality.value} · ${result.region_or_view.method}`}
              activeTool={tool}
              resetSignal={resetSignal}
              cam={showHeatmap ? cam : null}
              className="h-[560px] w-full"
            />
            <p className="border-t border-slate-100 px-4 py-2 text-[10px] leading-relaxed text-slate-400">
              The overlay maps the model's 224×224 centre-cropped input back onto the image. Areas outside
              that square carry no heatmap and are not evidence of normality.
            </p>
          </Card>

          <Card className="p-5">
            <div className="flex items-baseline justify-between gap-4">
              <h2 className="text-sm font-semibold text-slate-900">Findings</h2>
              <span className="text-[11px] text-slate-400">threshold {resultsThreshold(findings)}</span>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              Highest probability: <span className="font-medium text-slate-800">{prettyLabel(topLabel)}</span>{" "}
              ({(probability * 100).toFixed(1)}%)
            </p>
            <ul className="mt-4 space-y-2.5">
              {findings.map((finding) => {
                const percent = Math.round(finding.probability * 100);
                const positive = finding.threshold != null && finding.probability >= finding.threshold;
                return (
                  <li key={finding.label} className="grid grid-cols-[9.5rem_1fr_3.2rem] items-center gap-3">
                    <span className="truncate text-xs text-slate-600">{prettyLabel(finding.label)}</span>
                    <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className={`h-full rounded-full ${positive ? "bg-rose-500" : "bg-slate-400"}`}
                        style={{ width: `${Math.max(2, percent)}%` }}
                      />
                    </div>
                    <span className="text-right font-mono text-[11px] text-slate-500">{percent}%</span>
                  </li>
                );
              })}
            </ul>
            {result.warnings.length > 0 ? (
              <ul className="mt-4 list-disc space-y-1 border-t border-slate-100 pl-4 pt-3 text-[11px] text-slate-500">
                {result.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            ) : null}
          </Card>

          {model ? (
            <Card className="p-5">
              <h2 className="text-sm font-semibold text-slate-900">Model card highlights</h2>
              <p className="mt-2 text-xs leading-relaxed text-slate-600">
                {String(model.card.intended_use ?? "No intended-use statement provided.")}
              </p>
              <p className="mt-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
                {String(model.card.validation ?? "No validation statement provided.")}
              </p>
              <ul className="mt-2 list-disc space-y-1 pl-4 text-[11px] text-slate-500">
                {(model.card.limitations as string[] | undefined)?.map((limitation) => (
                  <li key={limitation}>{limitation}</li>
                ))}
              </ul>
              <Link to="/models" className="mt-3 inline-block text-xs font-medium text-clinical-700 hover:underline">
                Open the full model library
              </Link>
            </Card>
          ) : null}
        </div>

        <div className="space-y-4">
          <Card className="p-5">
            <h2 className="text-sm font-semibold text-slate-900">Provenance</h2>
            <dl className="mt-3 space-y-2 text-[11px]">
              <Row label="Record" value={shortDigest(provenance.record_id, 18)} mono />
              <Row label="Job" value={provenance.job_id} mono />
              <Row label="Model" value={`${provenance.model.name} ${provenance.model.version}`} />
              <Row label="Model digest" value={shortDigest(provenance.model.digest, 18)} mono />
              <Row label="Code commit" value={provenance.code_commit} mono />
              <Row label="Runtime" value={`${provenance.runtime.backend} · Python ${provenance.runtime.python}`} />
              <Row label="Seed" value={String(provenance.seed)} />
              <Row
                label="Heatmap"
                value={String(provenance.parameters.heatmap_shape ?? "none").replaceAll(",", " × ").replaceAll("[", "").replaceAll("]", "")}
              />
            </dl>
            <div className="mt-3 border-t border-slate-100 pt-3">
              <p className="text-[10px] uppercase tracking-wide text-slate-400">Inputs</p>
              {provenance.inputs.map((input) => (
                <div key={input.role} className="mt-1.5 text-[11px]">
                  <p className="text-slate-600">
                    {input.role.replaceAll("_", " ")} {input.retained ? "(stored)" : "(not stored)"}
                  </p>
                  <p className="font-mono text-[10px] text-slate-400">{shortDigest(input.digest, 26)}</p>
                </div>
              ))}
            </div>
          </Card>

          <Card className="p-5">
            <h2 className="text-sm font-semibold text-slate-900">Report</h2>
            {report ? (
              <>
                <p className="mt-2 text-xs text-slate-600">
                  Generated {formatDate(report.created_at)}. The PDF carries the facts, findings, provenance
                  reference and the model's limitations.
                </p>
                <button
                  type="button"
                  onClick={() => downloadReport(report.url, report.report_id)}
                  className="focus-ring mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Download again
                </button>
              </>
            ) : (
              <>
                <p className="mt-2 text-xs leading-relaxed text-slate-500">
                  Generate an A4 PDF with the study facts, findings, heatmap and model limitations for the
                  clinical record.
                </p>
                <button
                  type="button"
                  onClick={createReport}
                  disabled={reportBusy}
                  className="focus-ring mt-3 w-full rounded-lg bg-clinical-600 px-3 py-2 text-xs font-semibold text-white hover:bg-clinical-700 disabled:opacity-60"
                >
                  {reportBusy ? "Generating…" : "Create PDF report"}
                </button>
              </>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function prettyLabel(label: string): string {
  return label.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function resultsThreshold(findings: { threshold: number | null }[]): string {
  const threshold = findings.find((finding) => finding.threshold != null)?.threshold;
  return threshold != null ? threshold.toFixed(2) : "0.50";
}

function Row({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="shrink-0 text-slate-400">{label}</dt>
      <dd className={`text-right text-slate-700 ${mono ? "font-mono text-[10px]" : ""}`}>{value}</dd>
    </div>
  );
}
