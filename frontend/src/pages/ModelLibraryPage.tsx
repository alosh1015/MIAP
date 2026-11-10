import { useEffect, useState } from "react";
import { api, ApiError, type ModelEntry } from "../api/client";
import { Badge, Card, ErrorNote, PageHeader, shortDigest } from "../components/ui";

export function ModelLibraryPage() {
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listModels()
      .then(setModels)
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Could not load models"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <PageHeader
        title="Model library"
        subtitle="Read-only registry of every model MIAP can route an image to. Each result names the version and digest it used."
      />
      <ErrorNote message={error} />

      {loading ? (
        <Card className="p-8 text-sm text-slate-500">Loading registry…</Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {models.map((model) => (
            <Card key={`${model.model_id}-${model.version}`} className="p-5">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h2 className="font-mono text-sm font-semibold text-slate-900">{model.model_id}</h2>
                  <p className="mt-0.5 text-xs text-slate-500">version {model.version}</p>
                </div>
                <div className="flex flex-wrap gap-1">
                  <Badge tone={model.state === "approved" ? "good" : "warn"}>{model.state}</Badge>
                  {model.demo ? <Badge tone="bad">demo</Badge> : null}
                </div>
              </div>

              <dl className="mt-4 space-y-1.5 text-xs">
                <Row label="Task" value={model.task.replaceAll("_", " ")} />
                <Row label="Modalities" value={model.modalities.join(", ") || "—"} />
                <Row label="Regions" value={model.regions.join(", ") || "—"} />
                <Row label="Weights" value={model.weights ?? "—"} />
                <Row label="Digest" value={shortDigest(model.digest, 22)} mono />
              </dl>

              <div className="mt-4 border-t border-slate-100 pt-3">
                <p className="text-[10px] uppercase tracking-wide text-slate-400">Intended use</p>
                <p className="mt-1 text-xs leading-relaxed text-slate-600">
                  {String(model.card.intended_use ?? "No statement provided.")}
                </p>
                <p className="mt-3 text-[10px] uppercase tracking-wide text-slate-400">Validation</p>
                <p className="mt-1 rounded-md bg-amber-50 px-2.5 py-2 text-xs leading-relaxed text-amber-800">
                  {String(model.card.validation ?? "No statement provided.")}
                </p>
                <p className="mt-3 text-[10px] uppercase tracking-wide text-slate-400">Limitations</p>
                <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-slate-600">
                  {(model.card.limitations as string[] | undefined)?.map((limitation) => (
                    <li key={limitation}>{limitation}</li>
                  )) ?? <li>None recorded.</li>}
                </ul>
                {model.card.training_data ? (
                  <>
                    <p className="mt-3 text-[10px] uppercase tracking-wide text-slate-400">Training data</p>
                    <p className="mt-1 text-xs leading-relaxed text-slate-600">{String(model.card.training_data)}</p>
                  </>
                ) : null}
              </div>
            </Card>
          ))}
        </div>
      )}

      <p className="mt-6 max-w-3xl text-xs leading-relaxed text-slate-500">
        A model being listed here does not mean it is validated for your population. MIAP records this
        registry in every provenance record so a result can be traced back to the exact weights and card
        that produced it.
      </p>
    </div>
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
