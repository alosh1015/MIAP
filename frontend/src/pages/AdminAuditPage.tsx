import { useState } from "react";
import { api, ApiError, downloadWithAuth } from "../api/client";
import { AdminSubnav } from "../components/shell/AppShell";
import { Badge, Button, ErrorNote, Notice, Panel, PanelHeader, PageHeader } from "../components/ui";

interface Verification {
  ok: boolean;
  checked: number;
  first_bad_seq: number | null;
}

export function AdminAuditPage() {
  const [verification, setVerification] = useState<Verification | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [governanceBusy, setGovernanceBusy] = useState(false);

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

  async function governanceReport() {
    setGovernanceBusy(true);
    setError(null);
    try {
      const created = await api.createGovernanceReport(30);
      await downloadWithAuth(created.url, `miap-governance-${created.report_id}.pdf`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail || caught.message : "Report failed");
    } finally {
      setGovernanceBusy(false);
    }
  }

  return (
    <div className="max-w-5xl">
      <PageHeader
        title="Audit chain"
        actions={
          <>
            <Button icon="pdf" loading={governanceBusy} onClick={governanceReport}>
              Governance PDF
            </Button>
            <Button icon="download" loading={exporting} onClick={exportLog}>
              Export NDJSON
            </Button>
          </>
        }
      />
      <AdminSubnav />

      <Panel>
        <PanelHeader
          title="Chain integrity"
          actions={
            <Button variant="primary" icon="shield" loading={busy} onClick={verify}>
              Verify chain
            </Button>
          }
        />
        <div className="p-5">
          <ErrorNote message={error} />
          {verification ? (
            <div
              className={`rounded-md border px-4 py-3 text-sm ${
                verification.ok
                  ? "border-petrol/40 bg-petrol-soft text-petrol"
                  : "border-danger/40 bg-danger/10 text-danger"
              }`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={verification.ok ? "petrol" : "danger"}>
                  {verification.ok ? "intact" : "broken"}
                </Badge>
                <span>
                  {verification.checked} event{verification.checked === 1 ? "" : "s"} checked
                  {verification.first_bad_seq != null
                    ? ` · first bad sequence ${verification.first_bad_seq}`
                    : ""}
                  .
                </span>
              </div>
            </div>
          ) : null}

          <Notice icon="info" className="mt-4">
            Identity views, review decisions, approvals, retention runs and exports are recorded. Detail
            contains identifiers, field names and counts — never patient values, notes or pixels.
          </Notice>
        </div>
      </Panel>
    </div>
  );
}
