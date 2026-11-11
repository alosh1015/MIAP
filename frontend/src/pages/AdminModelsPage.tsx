import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type ModelApproval, type ModelEntry } from "../api/client";
import { AdminSubnav } from "../components/shell/AppShell";
import {
  Badge,
  Button,
  Dialog,
  ErrorNote,
  Field,
  Input,
  Panel,
  PanelHeader,
  PageHeader,
  Table,
  Td,
  Textarea,
  Th,
  formatDate,
  prettyLabel,
  shortDigest,
} from "../components/ui";

type Decision = "approve" | "reject" | "revoke";

interface Target {
  model: ModelEntry;
  decision: Decision;
}

export function AdminModelsPage() {
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [approvals, setApprovals] = useState<ModelApproval[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [target, setTarget] = useState<Target | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    Promise.all([api.listModels(), api.listApprovals()])
      .then(([registry, history]) => {
        setModels(registry);
        setApprovals(history);
        setError(null);
      })
      .catch((caught) => setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not load models"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  return (
    <div>
      <PageHeader
        title="Model approvals"
        actions={
          <Button icon="reset" loading={loading} onClick={load}>
            Refresh
          </Button>
        }
      />
      <AdminSubnav />
      <ErrorNote message={error} />

      <Panel>
        <PanelHeader title="Registry" />
        {loading && models.length === 0 ? (
          <p className="p-8 text-sm text-muted">Loading registry…</p>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Model</Th>
                <Th>Task</Th>
                <Th>State</Th>
                <Th>Digest</Th>
                <Th align="right">Decision</Th>
              </tr>
            </thead>
            <tbody>
              {models.map((model) => (
                <tr key={`${model.model_id}-${model.version}`} className="hover:bg-surface-2/60">
                  <Td>
                    <p className="font-mono text-sm text-ink">{model.model_id}</p>
                    <p className="mt-0.5 text-xs text-muted">v{model.version}</p>
                  </Td>
                  <Td className="text-sm">{prettyLabel(model.task)}</Td>
                  <Td>
                    <div className="flex flex-wrap gap-1">
                      <Badge tone={model.state === "approved" ? "petrol" : model.state === "candidate" ? "signal" : "neutral"}>
                        {prettyLabel(model.state)}
                      </Badge>
                      {model.demo ? <Badge tone="danger">demo</Badge> : null}
                    </div>
                  </Td>
                  <Td className="font-mono text-xs text-muted">{shortDigest(model.digest, 14)}</Td>
                  <Td align="right">
                    <div className="flex justify-end gap-1.5">
                      {model.state !== "approved" ? (
                        <Button size="sm" variant="primary" onClick={() => setTarget({ model, decision: "approve" })}>
                          Approve
                        </Button>
                      ) : (
                        <Button size="sm" variant="danger" onClick={() => setTarget({ model, decision: "revoke" })}>
                          Revoke
                        </Button>
                      )}
                      {model.state !== "rejected" && model.state !== "revoked" ? (
                        <Button size="sm" onClick={() => setTarget({ model, decision: "reject" })}>
                          Reject
                        </Button>
                      ) : null}
                    </div>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      <Panel className="mt-4">
        <PanelHeader title="Decision history" />
        {approvals.length === 0 ? (
          <p className="p-5 text-sm text-muted">No decisions have been recorded yet.</p>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Model</Th>
                <Th>Decision</Th>
                <Th>Benchmark digest</Th>
                <Th>Note</Th>
                <Th align="right">Decided</Th>
              </tr>
            </thead>
            <tbody>
              {approvals.map((approval) => (
                <tr key={approval.id}>
                  <Td>
                    <p className="font-mono text-xs text-ink">{approval.model_id}</p>
                    <p className="mt-0.5 text-xs text-muted">v{approval.version}</p>
                  </Td>
                  <Td>
                    <Badge
                      tone={
                        approval.decision === "approved"
                          ? "petrol"
                          : approval.decision === "rejected"
                            ? "danger"
                            : "neutral"
                      }
                    >
                      {prettyLabel(approval.decision)}
                    </Badge>
                  </Td>
                  <Td className="font-mono text-xs text-muted">
                    {approval.benchmark_digest ? shortDigest(approval.benchmark_digest, 16) : "—"}
                  </Td>
                  <Td className="max-w-[22rem] text-xs text-muted">{approval.note || "—"}</Td>
                  <Td align="right" className="whitespace-nowrap text-xs text-muted">
                    {formatDate(approval.decided_at)}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      <DecisionDialog
        target={target}
        onClose={() => setTarget(null)}
        onDecided={() => {
          setTarget(null);
          load();
        }}
      />
    </div>
  );
}

function DecisionDialog({
  target,
  onClose,
  onDecided,
}: {
  target: Target | null;
  onClose: () => void;
  onDecided: () => void;
}) {
  const [note, setNote] = useState("");
  const [digest, setDigest] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!target) return;
    setNote("");
    setDigest("");
    setError(null);
  }, [target]);

  async function submit() {
    if (!target) return;
    setBusy(true);
    setError(null);
    try {
      await api.decideModel(target.model.model_id, target.model.version, target.decision, {
        note: note.trim(),
        benchmark_digest: digest.trim() || null,
      });
      onDecided();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not record the decision");
    } finally {
      setBusy(false);
    }
  }

  const label = target ? `${target.model.model_id} v${target.model.version}` : "";
  const requiresDigest = target?.decision === "approve";

  return (
    <Dialog
      open={target !== null}
      onClose={onClose}
      title={target ? `${prettyLabel(target.decision)} · ${label}` : ""}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant={target?.decision === "reject" || target?.decision === "revoke" ? "danger" : "primary"}
            loading={busy}
            disabled={!note.trim() || (requiresDigest && !digest.trim())}
            onClick={submit}
          >
            Record decision
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {requiresDigest ? (
          <Field label="Benchmark digest" hint="SHA-256 of the benchmark JSON used for this decision.">
            <Input value={digest} onChange={(event) => setDigest(event.target.value)} className="font-mono" />
          </Field>
        ) : null}
        <Field label="Decision note" hint="Recorded verbatim in the approval history and audit.">
          <Textarea value={note} onChange={(event) => setNote(event.target.value)} />
        </Field>
        <ErrorNote message={error} />
      </div>
    </Dialog>
  );
}
