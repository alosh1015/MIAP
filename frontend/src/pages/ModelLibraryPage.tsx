import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type ModelEntry } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Icon } from "../components/icons";
import {
  Badge,
  Dialog,
  EmptyState,
  ErrorNote,
  Notice,
  Panel,
  PageHeader,
  Select,
  Skeleton,
  Stat,
  formatDate,
  shortDigest,
  prettyLabel,
} from "../components/ui";

const STATE_ORDER = ["approved", "candidate", "experimental", "revoked", "archived"];

function stateTone(state: string): "petrol" | "signal" | "danger" | "neutral" {
  if (state === "approved") return "petrol";
  if (state === "candidate") return "signal";
  if (state === "revoked" || state === "archived") return "neutral";
  return "neutral";
}

function modelImage(model: ModelEntry): string {
  if (model.modalities.includes("mammogram")) {
    return model.task.includes("screen")
      ? "/models/mammogram-screen.jpg"
      : "/models/mammogram-density.jpg";
  }
  if (model.regions.some((region) => region.startsWith("bone"))) return "/models/bone-xray.jpg";
  return "/models/chest-xray.jpg";
}

export function ModelLibraryPage() {
  const { user } = useAuth();
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [stateFilter, setStateFilter] = useState("");
  const [selected, setSelected] = useState<ModelEntry | null>(null);

  useEffect(() => {
    api
      .listModels()
      .then(setModels)
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Could not load models"))
      .finally(() => setLoading(false));
  }, []);

  const states = Array.from(new Set(models.map((model) => model.state))).sort(
    (a, b) => STATE_ORDER.indexOf(a) - STATE_ORDER.indexOf(b),
  );
  const visible = models.filter((model) => !stateFilter || model.state === stateFilter);

  return (
    <div>
      <PageHeader
        title="Model library"
        actions={
          user?.role === "administrator" ? (
            <Link
              to="/admin/models"
              className="inline-flex h-10 items-center gap-2 rounded-lg px-3 text-sm font-medium text-petrol transition-colors duration-150 ease-out hover:bg-surface-2"
            >
              <Icon name="shield" size={17} />
              Approvals
            </Link>
          ) : null
        }
      />

      <ErrorNote message={error} />

      {loading ? (
        <div className="mb-6 grid gap-x-8 gap-y-6 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((index) => (
            <div key={index} className="border-t border-rule pt-3">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="mt-3 h-8 w-14" />
            </div>
          ))}
        </div>
      ) : (
        <div className="mb-6 grid gap-x-8 gap-y-6 sm:grid-cols-2 xl:grid-cols-4">
          <Stat label="Registered models" value={models.length} />
          <Stat
            label="Approved"
            value={models.filter((model) => model.state === "approved").length}
            tone="petrol"
          />
          <Stat
            label="Candidates"
            value={models.filter((model) => model.state === "candidate").length}
            tone={models.some((model) => model.state === "candidate") ? "signal" : "neutral"}
          />
          <Stat
            label="Not validated locally"
            value={models.filter((model) => !model.validated_locally).length}
            tone={models.some((model) => !model.validated_locally) ? "signal" : "neutral"}
          />
        </div>
      )}

      <Notice tone="signal" icon="warn" className="mb-5">
        A model being listed here does not mean it is validated for your population. Scores are not
        calibrated. MIAP does not screen for tuberculosis.
      </Notice>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Select
          aria-label="Filter by state"
          value={stateFilter}
          onChange={(event) => setStateFilter(event.target.value)}
          className="w-auto max-w-[12rem]"
        >
          <option value="">All states</option>
          {states.map((state) => (
            <option key={state} value={state}>
              {prettyLabel(state)}
            </option>
          ))}
        </Select>
        <span className="text-xs text-muted">
          {visible.length} of {models.length} entries
        </span>
      </div>

      {loading ? (
        <div className="grid items-start gap-4 xl:grid-cols-2">
          {Array.from({ length: 4 }).map((_, index) => (
            <Panel key={index} className="space-y-3 p-5">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-24 w-full" />
            </Panel>
          ))}
        </div>
      ) : visible.length === 0 ? (
        <Panel>
          <EmptyState icon="models" title="No models match" />
        </Panel>
      ) : (
        <div className="grid items-start gap-4 xl:grid-cols-2">
          {visible.map((model) => (
            <ModelCard key={`${model.model_id}-${model.version}`} model={model} onOpen={setSelected} />
          ))}
        </div>
      )}

      <ModelDetailDialog model={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

function ModelCard({ model, onOpen }: { model: ModelEntry; onOpen: (model: ModelEntry) => void }) {
  const card = model.card ?? {};

  return (
    <Panel className="flex flex-col overflow-hidden">
      <button
        type="button"
        onClick={() => onOpen(model)}
        aria-label={`View details for ${model.model_id}`}
        className="group relative block aspect-[16/9] w-full overflow-hidden bg-viewer"
      >
        <img
          src={modelImage(model)}
          alt=""
          className="h-full w-full object-cover opacity-85 transition-opacity duration-200 ease-out group-hover:opacity-100"
        />
      </button>

      <div className="flex flex-1 flex-col p-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="truncate font-mono text-sm font-semibold text-ink">{model.model_id}</h2>
            <p className="mt-0.5 text-xs text-muted">
              version {model.version} · {prettyLabel(model.task)}
            </p>
          </div>
          <div className="flex flex-wrap gap-1">
            <Badge tone={stateTone(model.state)}>{prettyLabel(model.state)}</Badge>
            {model.demo ? <Badge tone="danger">demo weights</Badge> : null}
            {!model.validated_locally ? <Badge tone="signal">not validated locally</Badge> : null}
          </div>
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
          <Row label="Modalities" value={model.modalities.map(prettyLabel).join(", ") || "—"} />
          <Row label="Regions" value={model.regions.map(prettyLabel).join(", ") || "—"} />
          <Row label="Capabilities" value={model.capabilities.map(prettyLabel).join(", ") || "—"} />
          <Row label="Weights" value={model.weights ?? "—"} />
        </dl>

        <div className="mt-4 border-t border-rule pt-3">
          <p className="text-xs font-medium text-ink">Findings it can raise</p>
          <p className="mt-1 text-xs leading-relaxed text-muted">
            {String(card.intended_use ?? "No intended-use statement recorded for this entry.")}
          </p>
        </div>

        <div className="mt-auto flex items-center justify-between gap-3 pt-4">
          {model.state !== "approved" ? (
            <p className="flex min-w-0 items-center gap-1.5 text-xs text-muted">
              <Icon name="warn" size={14} className="shrink-0 text-signal" />
              <span className="truncate">Local validation required</span>
            </p>
          ) : (
            <span />
          )}
          <button
            type="button"
            onClick={() => onOpen(model)}
            className="flex shrink-0 items-center gap-1.5 text-sm font-medium text-petrol transition-colors duration-150 ease-out hover:text-ink"
          >
            View model
            <Icon name="arrow-right" size={15} />
          </button>
        </div>
      </div>
    </Panel>
  );
}

function ModelDetailDialog({ model, onClose }: { model: ModelEntry | null; onClose: () => void }) {
  return (
    <Dialog
      open={model !== null}
      onClose={onClose}
      title={model ? `${model.model_id} ${model.version}` : ""}
      width="max-w-2xl"
    >
      <div className="max-h-[70vh] overflow-y-auto pr-1">
        {model ? <ModelDetailBody model={model} /> : null}
      </div>
    </Dialog>
  );
}

function ModelDetailBody({ model }: { model: ModelEntry }) {
  const card = model.card ?? {};
  const limitations = (card.limitations as string[] | undefined) ?? [];
  const metrics = model.metrics ?? [];
  const approvals = model.approvals ?? [];
  const licence = model.licence ?? {};
  const source = model.source ?? {};
  const input = model.input ?? {};
  const cam = model.cam ?? {};

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone={stateTone(model.state)}>{prettyLabel(model.state)}</Badge>
        <Badge tone="outline">{prettyLabel(model.task)}</Badge>
        {model.demo ? <Badge tone="danger">demo weights</Badge> : null}
        {!model.validated_locally ? <Badge tone="signal">not validated locally</Badge> : null}
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 border-t border-rule pt-4 text-xs sm:grid-cols-3">
        <Row label="Modalities" value={model.modalities.map(prettyLabel).join(", ") || "—"} />
        <Row label="Regions" value={model.regions.map(prettyLabel).join(", ") || "—"} />
        <Row label="Capabilities" value={model.capabilities.map(prettyLabel).join(", ") || "—"} />
        <Row label="Weights" value={model.weights ?? "—"} />
        <Row label="Digest" value={shortDigest(model.digest, 16)} mono />
        <Row
          label="Licence"
          value={
            licence.name || licence.spdx
              ? `${licence.name ?? licence.spdx}${licence.spdx ? ` · ${licence.spdx}` : ""}`
              : "—"
          }
        />
      </dl>

      <section>
        <h3 className="text-xs font-medium text-ink">Findings it can raise</h3>
        <p className="mt-1 text-xs leading-relaxed text-muted">
          {String(card.intended_use ?? "No intended-use statement recorded for this entry.")}
        </p>
      </section>

      <section className="space-y-3 border-t border-rule pt-4 text-xs leading-relaxed text-muted">
        <div>
          <p className="font-medium text-ink">Validation</p>
          <p className="mt-0.5">{String(card.validation ?? "No validation statement provided.")}</p>
        </div>
        <div>
          <p className="font-medium text-ink">Reported metrics</p>
          {metrics.length > 0 ? (
            <ul className="mt-1 space-y-1">
              {metrics.map((metric, index) => (
                <li key={`${metric.name}-${index}`} className="flex justify-between gap-3 font-mono text-xs">
                  <span>{metric.name ?? "metric"}</span>
                  <span className="text-right text-ink">
                    {String(metric.value ?? "—")}
                    {metric.dataset ? <span className="text-muted"> · {metric.dataset}</span> : null}
                    {metric.source ? <span className="text-muted"> · {metric.source}</span> : null}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-0.5">No local benchmark has been recorded for this model.</p>
          )}
        </div>
        <div>
          <p className="font-medium text-ink">Approval history</p>
          {approvals.length > 0 ? (
            <ul className="mt-1 space-y-1">
              {approvals.map((approval) => (
                <li key={approval.id}>
                  {prettyLabel(approval.decision)} · {formatDate(approval.decided_at)}
                  {approval.benchmark_digest ? ` · benchmark ${shortDigest(approval.benchmark_digest, 12)}` : ""}
                  {approval.note ? ` · ${approval.note}` : ""}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-0.5">No approval decision recorded; the registry state applies.</p>
          )}
        </div>
        <div>
          <p className="font-medium text-ink">Source and licence</p>
          <p className="mt-0.5">
            {licence.name ?? licence.spdx ?? "—"}
            {licence.access_date ? ` · accessed ${licence.access_date}` : ""}
          </p>
          {licence.url ? (
            <p className="mt-0.5 break-all">
              <a href={licence.url} target="_blank" rel="noreferrer" className="text-petrol hover:underline">
                {licence.url}
              </a>
            </p>
          ) : null}
          {source.repo ? <p className="mt-0.5 break-all">Repo: {source.repo}</p> : null}
          {source.sha256 ? <p className="mt-0.5 break-all font-mono">Weights SHA-256: {source.sha256}</p> : null}
        </div>
        <div>
          <p className="font-medium text-ink">Technical input</p>
          <p className="mt-0.5">
            {model.preprocess_profile ?? "no profile"} · {input.size ? `${input.size[0]}×${input.size[1]}` : "vendor size"} ·{" "}
            {input.channels ? `${input.channels} ch` : "channels n/a"} · {input.crop ?? "crop n/a"}
          </p>
          <p className="mt-0.5">
            CAM {cam.method ?? "n/a"}
            {cam.target_layer ? ` · ${cam.target_layer}` : ""}
            {cam.reshape ? ` · ${cam.reshape}` : ""}
          </p>
        </div>
        <div>
          <p className="font-medium text-ink">Limitations</p>
          {limitations.length > 0 ? (
            <ul className="mt-1 list-disc space-y-1 pl-4">
              {limitations.map((limitation) => (
                <li key={limitation}>{limitation}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-0.5">None recorded.</p>
          )}
        </div>
        {card.training_data ? (
          <div>
            <p className="font-medium text-ink">Training data</p>
            <p className="mt-0.5">{String(card.training_data)}</p>
          </div>
        ) : null}
      </section>

      {model.state !== "approved" ? (
        <p className="flex items-start gap-2 border-l-2 border-signal py-0.5 pl-2.5 text-xs text-ink">
          <Icon name="warn" size={15} className="mt-px shrink-0 text-signal" />
          Not selectable for analysis until approved against a benchmark.
        </p>
      ) : null}
    </div>
  );
}

function Row({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className={`mt-0.5 break-words text-ink ${mono ? "font-mono text-xs" : ""}`}>{value}</dd>
    </div>
  );
}
