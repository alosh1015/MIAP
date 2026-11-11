import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type RetentionPreview, type RetentionResult } from "../api/client";
import { AdminSubnav } from "../components/shell/AppShell";
import { Icon } from "../components/icons";
import {
  Badge,
  Button,
  Dialog,
  ErrorNote,
  Notice,
  Panel,
  PanelHeader,
  PageHeader,
  Stat,
  formatBytes,
  formatDate,
} from "../components/ui";

export function AdminRetentionPage() {
  const [preview, setPreview] = useState<RetentionPreview | null>(null);
  const [result, setResult] = useState<RetentionResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [running, setRunning] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    api
      .retentionPreview()
      .then((data) => {
        setPreview(data);
        setError(null);
      })
      .catch((caught) => setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not load the retention preview"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      const outcome = await api.retentionRun();
      setResult(outcome);
      setConfirmOpen(false);
      load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail || caught.message : "Retention run failed");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Retention"
        actions={
          <Button icon="reset" loading={loading} onClick={load}>
            Refresh preview
          </Button>
        }
      />
      <AdminSubnav />
      <ErrorNote message={error} />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Cases due" value={preview?.due_cases ?? "—"} tone={(preview?.due_cases ?? 0) > 0 ? "signal" : "neutral"} />
        <Stat label="Image blobs" value={preview?.blobs ?? "—"} />
        <Stat label="Total reclaimable" value={preview ? formatBytes(preview.bytes_total) : "—"} />
        <Stat label="Cutoff" value={preview ? formatDate(preview.cutoff) : "—"} />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader title="Preview" />
          <dl className="space-y-3 p-5 text-sm">
            <Row label="Cases due" value={String(preview?.due_cases ?? 0)} />
            <Row label="Image blobs" value={String(preview?.blobs ?? 0)} />
            <Row label="Image bytes" value={formatBytes(preview?.bytes_blobs)} />
            <Row label="Derived results" value={formatBytes(preview?.bytes_derived)} />
            <Row label="Reports" value={formatBytes(preview?.bytes_reports)} />
            <Row label="Total" value={formatBytes(preview?.bytes_total)} />
          </dl>
        </Panel>

        <Panel>
          <PanelHeader title="Run retention" />
          <div className="space-y-4 p-5">
            <Notice tone="signal" icon="warn">
              Running retention deletes image pixels, heatmaps, results and reports for due cases, then
              archives the case rows. Audit events are never deleted, so the chain stays verifiable.
            </Notice>
            <Button
              variant="danger"
              icon="trash"
              disabled={!preview || preview.due_cases === 0}
              onClick={() => setConfirmOpen(true)}
            >
              Run retention now
            </Button>
            {preview && preview.due_cases === 0 ? (
              <p className="text-xs text-muted">Nothing is due under the current retention policy.</p>
            ) : null}

            {result ? (
              <div className="rounded-md border border-petrol/40 bg-petrol-soft px-3 py-2.5 text-sm text-petrol">
                <p className="flex items-center gap-1.5 font-medium">
                  <Icon name="check" size={15} />
                  Retention completed
                </p>
                <p className="mt-1 text-xs">
                  {result.archived} cases archived · {result.deleted_images} images ·{" "}
                  {result.deleted_results} results · {result.deleted_reports} reports ·{" "}
                  {formatBytes(result.freed_bytes)} freed.
                </p>
              </div>
            ) : null}
          </div>
        </Panel>
      </div>

      <Dialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Run retention now?"
        footer={
          <>
            <Button onClick={() => setConfirmOpen(false)}>Cancel</Button>
            <Button variant="danger" loading={running} icon="trash" onClick={run}>
              Delete due data
            </Button>
          </>
        }
      >
        <div className="space-y-3 text-sm text-muted">
          <p>
            This will archive <strong className="text-ink">{preview?.due_cases ?? 0}</strong> cases and free
            approximately <strong className="text-ink">{formatBytes(preview?.bytes_total)}</strong>.
          </p>
          <p>This cannot be undone. Audit events are retained.</p>
          <Badge tone="danger">case cutoff {preview ? formatDate(preview.cutoff) : "—"}</Badge>
        </div>
      </Dialog>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right font-mono text-xs text-ink">{value}</dd>
    </div>
  );
}
