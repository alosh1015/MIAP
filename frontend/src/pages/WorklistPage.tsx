import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type CaseSummary } from "../api/client";
import { useAuth, hasRole } from "../auth/AuthContext";
import { Badge, Card, ErrorNote, PageHeader, formatDate } from "../components/ui";

const CONSENT_TONE: Record<string, "info" | "good" | "warn"> = {
  clinical: "info",
  research: "good",
  teaching: "warn",
};

export function WorklistPage() {
  const { user } = useAuth();
  const [cases, setCases] = useState<CaseSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listCases()
      .then(setCases)
      .catch((caught) => setError(caught instanceof ApiError ? caught.message : "Could not load cases"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <PageHeader
        title="Worklist"
        subtitle="De-identified studies visible to your role."
        actions={
          hasRole(user, "clinician", "researcher") ? (
            <Link
              to="/cases/new"
              className="focus-ring rounded-lg bg-clinical-600 px-3 py-2 text-sm font-semibold text-white hover:bg-clinical-700"
            >
              New study
            </Link>
          ) : null
        }
      />

      <ErrorNote message={error} />

      {loading ? (
        <Card className="p-8 text-sm text-slate-500">Loading studies…</Card>
      ) : cases.length === 0 ? (
        <Card className="p-10 text-center">
          <p className="text-sm font-medium text-slate-700">No studies yet</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
            {hasRole(user, "clinician", "researcher")
              ? "Create a study, upload a chest X-ray or mammogram set, and MIAP will de-identify it before storing it."
              : "Studies appear here once clinicians upload images."}
          </p>
          {hasRole(user, "clinician", "researcher") ? (
            <Link
              to="/cases/new"
              className="focus-ring mt-5 inline-block rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Create the first study
            </Link>
          ) : null}
        </Card>
      ) : (
        <div className="grid gap-3">
          {cases.map((study) => (
            <Link
              key={study.id}
              to={`/cases/${study.id}`}
              className="focus-ring group rounded-xl border border-slate-200 bg-white p-4 transition hover:border-clinical-500/40 hover:shadow-sm"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h2 className="truncate text-sm font-semibold text-slate-900 group-hover:text-clinical-700">
                      {study.pseudonym}
                    </h2>
                    <Badge tone={CONSENT_TONE[study.consent] ?? "neutral"}>{study.consent}</Badge>
                    {study.status === "archived" ? <Badge tone="neutral">archived</Badge> : null}
                  </div>
                  <p className="mt-1 font-mono text-[11px] text-slate-400">{study.id}</p>
                </div>
                <div className="flex items-center gap-6 text-xs text-slate-500">
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-slate-400">Modality</p>
                    <p className="mt-0.5 font-medium text-slate-700">{study.modality ?? "not yet resolved"}</p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-slate-400">Images</p>
                    <p className="mt-0.5 font-medium text-slate-700">{study.image_count}</p>
                  </div>
                  <div className="hidden sm:block">
                    <p className="text-[10px] uppercase tracking-wide text-slate-400">Created</p>
                    <p className="mt-0.5 font-medium text-slate-700">{formatDate(study.created_at)}</p>
                  </div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
