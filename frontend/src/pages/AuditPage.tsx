import { useState } from "react";
import { api, ApiError, downloadWithAuth } from "../api/client";
import { Badge, Card, ErrorNote, PageHeader } from "../components/ui";

interface Verification {
  ok: boolean;
  checked: number;
  first_bad_seq: number | null;
}

export function AuditPage() {
  const [verification, setVerification] = useState<Verification | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);

  async function verify() {
    setBusy(true);
    setError(null);
    try {
      setVerification(await api.verifyAudit());
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail || caught.message : "Verification failed");
    } finally {
      setBusy(false);
    }
  }

  async function exportLog() {
    setExporting(true);
    setError(null);
    try {
      await downloadWithAuth(api.auditExportUrl(), "miap-audit.ndjson");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail || caught.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="max-w-3xl">
      <PageHeader
        title="Audit trail"
        subtitle="Every action is appended as an event whose hash covers the previous event. Editing or deleting a row breaks the chain."
        actions={
          <button
            type="button"
            onClick={exportLog}
            disabled={exporting}
            className="focus-ring rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
          >
            {exporting ? "Exporting…" : "Export NDJSON"}
          </button>
        }
      />

      <Card className="p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Chain integrity</h2>
            <p className="mt-1 text-xs text-slate-500">
              Recomputes every SHA-256 link from sequence 1 upward.
            </p>
          </div>
          <button
            type="button"
            onClick={verify}
            disabled={busy}
            className="focus-ring rounded-lg bg-clinical-600 px-3 py-2 text-sm font-semibold text-white hover:bg-clinical-700 disabled:opacity-60"
          >
            {busy ? "Verifying…" : "Verify chain"}
          </button>
        </div>

        <ErrorNote message={error} />

        {verification ? (
          <div
            className={`mt-4 rounded-lg border px-4 py-3 text-sm ${
              verification.ok
                ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border-rose-200 bg-rose-50 text-rose-800"
            }`}
          >
            <div className="flex items-center gap-2">
              <Badge tone={verification.ok ? "good" : "bad"}>{verification.ok ? "intact" : "broken"}</Badge>
              <span>
                {verification.checked} event{verification.checked === 1 ? "" : "s"} checked
                {verification.first_bad_seq != null ? ` · first bad sequence ${verification.first_bad_seq}` : ""}.
              </span>
            </div>
          </div>
        ) : null}
      </Card>

      <Card className="mt-4 p-6">
        <h2 className="text-sm font-semibold text-slate-900">What is recorded</h2>
        <ul className="mt-2 list-disc space-y-1.5 pl-5 text-xs leading-relaxed text-slate-600">
          <li>Case creation and archival, with the consent basis.</li>
          <li>Every upload, including the original digest and the de-identification receipt reference.</li>
          <li>Analysis submission and completion, naming the model version.</li>
          <li>Result and report creation.</li>
        </ul>
        <p className="mt-3 text-xs leading-relaxed text-slate-500">
          The export is one JSON object per line, in sequence order, including each event's previous hash and
          its own hash. It can be verified independently of MIAP using SHA-256 over the canonical JSON
          payload.
        </p>
      </Card>
    </div>
  );
}
