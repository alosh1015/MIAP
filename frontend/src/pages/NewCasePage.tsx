import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";
import { Card, ErrorNote, PageHeader } from "../components/ui";

export function NewCasePage() {
  const navigate = useNavigate();
  const [pseudonym, setPseudonym] = useState("");
  const [consent, setConsent] = useState("clinical");
  const [retentionDays, setRetentionDays] = useState("365");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const study = await api.createCase({
        pseudonym: pseudonym.trim(),
        consent,
        retention_days: retentionDays ? Number(retentionDays) : null,
      });
      navigate(`/cases/${study.id}`, { replace: true });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not create the study");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title="New study"
        subtitle="Create a pseudonymous container first; images are attached to it next."
      />
      <Card className="p-6">
        <form className="space-y-5" onSubmit={submit}>
          <label className="block">
            <span className="text-xs font-medium text-slate-600">Pseudonym</span>
            <input
              required
              maxLength={120}
              value={pseudonym}
              onChange={(event) => setPseudonym(event.target.value)}
              placeholder="e.g. Study-2026-014"
              className="focus-ring mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <span className="mt-1 block text-[11px] text-slate-400">
              Do not enter a patient name, hospital number or date of birth.
            </span>
          </label>

          <label className="block">
            <span className="text-xs font-medium text-slate-600">Consent basis</span>
            <select
              value={consent}
              onChange={(event) => setConsent(event.target.value)}
              className="focus-ring mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
            >
              <option value="clinical">Clinical care</option>
              <option value="research">Research — shared with researchers</option>
              <option value="teaching">Teaching</option>
            </select>
            <span className="mt-1 block text-[11px] text-slate-400">
              “Research” makes the study visible to other researcher accounts. Clinical studies stay with
              their owner.
            </span>
          </label>

          <label className="block">
            <span className="text-xs font-medium text-slate-600">Retention (days)</span>
            <input
              type="number"
              min={1}
              max={3650}
              value={retentionDays}
              onChange={(event) => setRetentionDays(event.target.value)}
              className="focus-ring mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <span className="mt-1 block text-[11px] text-slate-400">
              A purge script enforces this later; leave blank to keep until manually archived.
            </span>
          </label>

          <ErrorNote message={error} />

          <div className="flex items-center justify-end gap-2 border-t border-slate-100 pt-4">
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="focus-ring rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={busy || !pseudonym.trim()}
              className="focus-ring rounded-lg bg-clinical-600 px-3 py-2 text-sm font-semibold text-white hover:bg-clinical-700 disabled:opacity-60"
            >
              {busy ? "Creating…" : "Create study"}
            </button>
          </div>
        </form>
      </Card>
    </div>
  );
}
