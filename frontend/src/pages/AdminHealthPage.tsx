import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type SystemHealth } from "../api/client";
import { AdminSubnav } from "../components/shell/AppShell";
import { Icon } from "../components/icons";
import {
  Badge,
  Button,
  ErrorNote,
  Notice,
  Panel,
  PanelHeader,
  PageHeader,
  Stat,
  Table,
  Td,
  Th,
  formatBytes,
  formatDate,
  prettyLabel,
} from "../components/ui";

export function AdminHealthPage() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    api
      .health()
      .then((data) => {
        setHealth(data);
        setError(null);
      })
      .catch((caught) => setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not load system health"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  return (
    <div>
      <PageHeader
        title="Governance"
        actions={
          <Button icon="reset" loading={loading} onClick={load}>
            Refresh
          </Button>
        }
      />
      <AdminSubnav />
      <ErrorNote message={error} />

      {!health ? (
        <Panel className="p-8 text-sm text-muted">{loading ? "Checking the system…" : "No health data."}</Panel>
      ) : (
        <div className="space-y-6">
          <Notice tone={health.status === "ok" ? "petrol" : "signal"} icon={health.status === "ok" ? "check" : "warn"}>
            System is <strong>{health.status}</strong> · MIAP {health.version} · generated{" "}
            {formatDate(health.generated_at)}
          </Notice>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Stat
              label="Analysis queue"
              value={health.queue.queued + health.queue.running}
              tone={health.queue.running > 0 ? "petrol" : "neutral"}
              hint={`${health.queue.running} running · ${health.queue.queued} waiting`}
            />
            <Stat label="Failed today" value={health.queue.failed_today} tone={health.queue.failed_today > 0 ? "danger" : "neutral"} />
            <Stat label="Active users" value={health.users.active} hint={`${health.users.total} total`} />
            <Stat
              label="Audit events"
              value={health.audit.checked}
              tone={health.audit.ok ? "petrol" : "danger"}
              hint={health.audit.ok ? "chain intact" : `broken at ${health.audit.first_bad_seq}`}
            />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Panel>
              <PanelHeader title="Storage and database" />
              <dl className="space-y-3 p-5 text-sm">
                <Row label="Database file" value={`${health.database.file} · ${formatBytes(health.database.size_bytes)}`} />
                <Row label="Schema version" value={String(health.database.schema_version)} />
                <Row
                  label="Data directory"
                  value={`${formatBytes(health.storage.data_size_bytes)} used of ${formatBytes(health.storage.total_bytes)}`}
                />
                <Row label="Free disk" value={formatBytes(health.storage.free_bytes)} />
                <Row label="Studies" value={`${health.cases.total} · ${health.cases.archived} archived`} />
                <Row label="Due for retention" value={String(health.cases.due_for_retention)} />
                <Row label="Stored results" value={String(health.results.total)} />
              </dl>
            </Panel>

            <Panel>
              <PanelHeader title="Worker and models" />
              <div className="space-y-4 p-5">
                <div className="flex items-center justify-between gap-3">
                  <span className="flex items-center gap-2 text-sm text-ink">
                    <Icon
                      name={health.worker.running ? "check" : "warn"}
                      size={16}
                      className={health.worker.running ? "text-petrol" : "text-signal"}
                    />
                    CPU worker {health.worker.running ? "running" : "idle"}
                  </span>
                  <Badge tone="outline">cache {health.worker.engine_cache.length} engine(s)</Badge>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge tone="petrol">{health.models.approved} approved</Badge>
                  <Badge tone="signal">{health.models.candidate} candidate</Badge>
                </div>
                <div className="overflow-hidden">
                  <Table>
                    <thead>
                      <tr>
                        <Th>Model</Th>
                        <Th>Version</Th>
                        <Th>State</Th>
                        <Th>Source</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {health.models.versions.map((entry) => (
                        <tr key={`${entry.model_id}-${entry.version}`}>
                          <Td className="font-mono text-xs">{entry.model_id}</Td>
                          <Td className="text-xs text-muted">{entry.version}</Td>
                          <Td>
                            <Badge tone={entry.state === "approved" ? "petrol" : "neutral"}>
                              {prettyLabel(entry.state)}
                            </Badge>
                          </Td>
                          <Td className="text-xs text-muted">{prettyLabel(entry.state_source)}</Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </div>
                <Link to="/admin/models" className="text-sm font-medium text-petrol hover:underline">
                  Model approvals
                </Link>
              </div>
            </Panel>
          </div>

          <Panel className="p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-ink">Audit chain</h2>
                <p className="mt-0.5 text-xs text-muted">{health.audit.checked} events checked.</p>
              </div>
              <div className="flex items-center gap-2">
                <Badge tone={health.audit.ok ? "petrol" : "danger"}>
                  {health.audit.ok ? "intact" : "broken"}
                </Badge>
                <Link to="/admin/audit" className="text-sm font-medium text-petrol hover:underline">
                  Audit chain
                </Link>
              </div>
            </div>
          </Panel>
        </div>
      )}
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
