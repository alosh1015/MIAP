import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type Batch } from "../api/client";
import { Icon } from "../components/icons";
import {
  Badge,
  Button,
  EmptyState,
  ErrorNote,
  Panel,
  PageHeader,
  Spinner,
  Table,
  Td,
  Th,
  formatDate,
  prettyLabel,
  shortDigest,
} from "../components/ui";

function batchTone(state: Batch["state"]): "petrol" | "signal" | "danger" | "neutral" {
  if (state === "completed") return "petrol";
  if (state === "running" || state === "queued") return "signal";
  if (state === "failed") return "danger";
  return "neutral";
}

export function ResearchBatchesPage() {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    api
      .listBatches(30)
      .then((data) => {
        setBatches(data);
        setError(null);
      })
      .catch((caught) => setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not load batches"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  useEffect(() => {
    const active = batches.some((batch) => batch.state === "queued" || batch.state === "running");
    if (!active) return;
    const timer = window.setTimeout(load, 3000);
    return () => window.clearTimeout(timer);
  }, [batches, load]);

  return (
    <div>
      <PageHeader
        title="Batch runs"
        actions={
          <>
            <Button icon="reset" onClick={load}>
              Refresh
            </Button>
            <Link
              to="/research"
              className="inline-flex h-10 items-center gap-2 rounded-md bg-petrol px-4 text-sm font-medium text-paper hover:opacity-90"
            >
              <Icon name="database" size={17} />
              Open dataset
            </Link>
          </>
        }
      />

      <ErrorNote message={error} />

      <Panel>
        {loading && batches.length === 0 ? (
          <p className="flex items-center gap-2 p-8 text-sm text-muted">
            <Spinner size={15} />
            Loading batch runs…
          </p>
        ) : batches.length === 0 ? (
          <EmptyState
            icon="bolt"
            title="No batch runs yet"
            action={
              <Link to="/research" className="text-sm font-medium text-petrol hover:underline">
                Browse the dataset
              </Link>
            }
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Batch</Th>
                <Th>Study</Th>
                <Th>Model</Th>
                <Th>State</Th>
                <Th align="right">Progress</Th>
                <Th align="right">Created</Th>
              </tr>
            </thead>
            <tbody>
              {batches.map((batch) => {
                const done = (batch.counts.completed ?? 0) + (batch.counts.failed ?? 0);
                const percent = batch.total > 0 ? Math.round((done / batch.total) * 100) : 0;
                return (
                  <tr key={batch.batch_id} className="hover:bg-surface-2/60">
                    <Td className="font-mono text-xs text-muted">{shortDigest(batch.batch_id, 18)}</Td>
                    <Td>
                      <Link to={`/cases/${batch.case_id}`} className="text-sm font-medium text-petrol hover:underline">
                        Open study
                      </Link>
                    </Td>
                    <Td>
                      <span className="font-mono text-xs text-ink">{batch.model_id}</span>
                      {batch.model_version ? (
                        <p className="mt-0.5 text-xs text-muted">{batch.model_version}</p>
                      ) : null}
                    </Td>
                    <Td>
                      <Badge tone={batchTone(batch.state)}>{prettyLabel(batch.state)}</Badge>
                    </Td>
                    <Td align="right">
                      <div className="ml-auto flex w-36 items-center gap-2">
                        <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-rule">
                          <span
                            className="block h-full rounded-full bg-petrol transition-all"
                            style={{ width: `${percent}%` }}
                          />
                        </span>
                        <span className="w-12 shrink-0 font-mono text-xs text-muted">
                          {done}/{batch.total}
                        </span>
                      </div>
                      {batch.counts.failed ? (
                        <p className="mt-0.5 text-xs text-danger">{batch.counts.failed} failed</p>
                      ) : null}
                    </Td>
                    <Td align="right" className="whitespace-nowrap text-xs text-muted">
                      {formatDate(batch.created_at)}
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </Panel>
    </div>
  );
}
