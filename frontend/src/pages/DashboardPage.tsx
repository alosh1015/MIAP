import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  api,
  ApiError,
  type AdminDashboard,
  type ClinicianDashboard,
  type Dashboard,
  type ResearcherDashboard,
} from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Icon } from "../components/icons";
import { DECISION_SUPPORT_NOTICE, ScreenWarning, TB_NOTICE } from "../components/ScreenWarning";
import {
  Badge,
  Button,
  EmptyState,
  ErrorNote,
  Notice,
  Panel,
  PanelHeader,
  PageHeader,
  Skeleton,
  Stat,
  Table,
  Td,
  Th,
  formatDate,
  prettyLabel,
  relativeTime,
} from "../components/ui";

export function DashboardPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .dashboard()
      .then(setData)
      .catch((caught) => setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not load the dashboard"));
  }, []);

  const greeting = user ? `Good ${partOfDay()}, ${user.display_name.split(" ")[0]}` : "Dashboard";

  return (
    <div>
      <PageHeader
        title={greeting}
        actions={
          !data ? null : data.role === "clinician" ? (
            <>
              <Button icon="user" onClick={() => navigate("/patients/new")}>
                New patient
              </Button>
              <Button icon="new-study" variant="primary" onClick={() => navigate("/cases/new")}>
                New study
              </Button>
            </>
          ) : data?.role === "researcher" ? (
            <Button icon="bolt" variant="primary" onClick={() => navigate("/research/batches")}>
              Batch runs
            </Button>
          ) : (
            <Button icon="shield" variant="primary" onClick={() => navigate("/admin/health")}>
              System health
            </Button>
          )
        }
      />

      <ErrorNote message={error} />

      {!data && !error ? <DashboardSkeleton /> : null}

      {data?.role === "clinician" ? <ClinicianView data={data} /> : null}
      {data?.role === "researcher" ? <ResearcherView data={data} /> : null}
      {data?.role === "administrator" ? <AdminView data={data} /> : null}
    </div>
  );
}

function ClinicianView({ data }: { data: ClinicianDashboard }) {
  const navigate = useNavigate();
  return (
    <div className="space-y-6">
      <div className="grid gap-x-8 gap-y-6 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="My patients" value={data.patients.mine} />
        <Stat label="Open studies" value={data.studies.open} hint={`${data.studies.total} total`} />
        <Stat label="Flagged by AI" value={data.ai.flagged} tone="signal" />
        <Stat
          label="Findings to review"
          value={data.ai.awaiting_review}
          tone={data.ai.awaiting_review > 0 ? "signal" : "neutral"}
        />
      </div>

      <Panel>
        <PanelHeader
          title="Recent studies"
          actions={
            <Link to="/worklist" className="text-sm font-medium text-petrol hover:underline">
              Open worklist
            </Link>
          }
        />
        {data.recent_cases.length === 0 ? (
          <EmptyState
            icon="worklist"
            title="No studies yet"
            action={
              <Button variant="primary" icon="plus" onClick={() => navigate("/cases/new")}>
                New study
              </Button>
            }
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Patient</Th>
                <Th>Study</Th>
                <Th>AI</Th>
                <Th align="right">Review</Th>
                <Th align="right">Created</Th>
              </tr>
            </thead>
            <tbody>
              {data.recent_cases.map((study) => (
                <tr key={study.id} className="hover:bg-surface-2/60">
                  <Td>
                    <Link to={`/cases/${study.id}`} className="font-medium text-ink hover:text-petrol">
                      {study.patient_display}
                    </Link>
                    {study.patient_display !== study.pseudonym ? (
                      <p className="mt-0.5 font-mono text-xs text-muted">{study.pseudonym}</p>
                    ) : null}
                  </Td>
                  <Td>
                    <span>{study.modality ? prettyLabel(study.modality) : "—"}</span>
                    <p className="mt-0.5 text-xs text-muted">
                      {study.image_count} image{study.image_count === 1 ? "" : "s"}
                    </p>
                  </Td>
                  <Td>
                    <AiFlag flag={study.ai_flag} />
                  </Td>
                  <Td align="right">
                    {study.findings_to_review > 0 ? (
                      <Badge tone="signal">
                        {study.reviewed}/{study.findings_to_review}
                      </Badge>
                    ) : (
                      <span className="text-xs text-muted">—</span>
                    )}
                  </Td>
                  <Td align="right" className="text-xs text-muted">
                    {relativeTime(study.created_at)}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      <ScreenWarning
        items={[DECISION_SUPPORT_NOTICE, ...(data.notices.length ? data.notices : [TB_NOTICE])]}
      />
    </div>
  );
}

function ResearcherView({ data }: { data: ResearcherDashboard }) {
  return (
    <div className="space-y-6">
      <Notice tone="signal" icon="bolt">
        {data.compute_warning}
      </Notice>

      <div className="grid gap-x-8 gap-y-6 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="My studies" value={data.datasets.own} />
        <Stat label="Research consent" value={data.datasets.research_consent} />
        <Stat label="Active batches" value={data.batches.active} tone="petrol" />
        <Stat
          label="Approved models"
          value={data.models.approved}
          hint={`${data.models.candidate} candidate`}
        />
      </div>

      <Panel>
        <PanelHeader title="Recent exports" />
        {data.recent_exports.length === 0 ? (
          <EmptyState icon="download" title="No exports yet" />
        ) : (
          <ul className="divide-y divide-rule">
            {data.recent_exports.map((entry) => (
              <li key={`${entry.at}-${JSON.stringify(entry.detail)}`} className="px-4 py-3">
                <p className="text-sm text-ink">{formatDate(entry.at)}</p>
                <p className="mt-0.5 font-mono text-xs text-muted">
                  {Object.entries(entry.detail)
                    .map(([key, value]) => `${key}=${String(value)}`)
                    .join(" · ")}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

function AdminView({ data }: { data: AdminDashboard }) {
  return (
    <div className="space-y-6">
      <Notice tone="neutral" icon="lock">
        Governance data only — no images, identity, findings or case reports.
      </Notice>

      <div className="grid gap-x-8 gap-y-6 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Queue" value={data.queue.queued + data.queue.running} hint={`${data.queue.running} running · ${data.queue.queued} waiting`} />
        <Stat label="Active users" value={data.users.active} />
        <Stat
          label="Pending approvals"
          value={data.models.pending_approvals}
          tone={data.models.pending_approvals > 0 ? "signal" : "neutral"}
        />
        <Stat
          label="Retention due"
          value={data.retention.due}
          tone={data.retention.due > 0 ? "signal" : "neutral"}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel className="p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-ink">Audit chain</h2>
              <p className="mt-1 text-xs tabular-nums text-muted">Verified {formatDate(data.audit.verified_at)}</p>
            </div>
            <Badge tone={data.audit.ok ? "good" : "danger"}>{data.audit.ok ? "intact" : "broken"}</Badge>
          </div>
          <p className="mt-4 text-3xl font-medium leading-none tabular-nums text-ink">{data.audit.checked}</p>
          <p className="mt-1 text-xs text-muted">
            events checked
            {data.audit.first_bad_seq != null ? ` · first bad sequence ${data.audit.first_bad_seq}` : ""}
          </p>
          <Link to="/admin/audit" className="mt-4 inline-block text-sm font-medium text-petrol hover:underline">
            Audit chain
          </Link>
        </Panel>

        <Panel className="p-5">
          <h2 className="text-base font-semibold text-ink">Governance shortcuts</h2>
          <ul className="mt-3">
            <Shortcut to="/admin/users" icon="users" label="Users and roles" />
            <Shortcut to="/admin/models" icon="models" label="Model approvals" />
            <Shortcut to="/admin/retention" icon="retention" label="Retention" />
            <Shortcut to="/admin/health" icon="health" label="System health" />
          </ul>
        </Panel>
      </div>
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-8">
      <div className="grid gap-x-8 gap-y-6 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((index) => (
          <div key={index} className="border-t border-rule pt-3">
            <Skeleton className="h-3 w-24" />
            <Skeleton className="mt-3 h-8 w-14" />
          </div>
        ))}
      </div>
      <Panel className="p-5">
        <Skeleton className="h-4 w-32" />
        <div className="mt-5 space-y-3">
          {[0, 1, 2, 3, 4].map((index) => (
            <Skeleton key={index} className="h-9 w-full" />
          ))}
        </div>
      </Panel>
    </div>
  );
}

function Shortcut({ to, icon, label }: { to: string; icon: Parameters<typeof Icon>[0]["name"]; label: string }) {
  return (
    <li>
      <Link
        to={to}
        className="flex items-center justify-between gap-2 border-b border-rule py-2.5 text-sm text-ink last:border-0 hover:text-petrol"
      >
        <span className="flex items-center gap-2.5">
          <Icon name={icon} size={16} className="text-muted" />
          {label}
        </span>
        <Icon name="chevron-right" size={15} className="text-muted" />
      </Link>
    </li>
  );
}

export function AiFlag({ flag }: { flag: string | null }) {
  if (!flag) return <span className="text-xs text-muted">—</span>;
  const map: Record<string, { tone: "signal" | "good" | "neutral" | "danger" | "petrol"; label: string }> = {
    flagged: { tone: "signal", label: "Flagged" },
    clear: { tone: "good", label: "Clear" },
    pending: { tone: "petrol", label: "Pending" },
    failed: { tone: "danger", label: "Failed" },
  };
  const entry = map[flag] ?? { tone: "neutral" as const, label: flag };
  return <Badge tone={entry.tone}>{entry.label}</Badge>;
}

function partOfDay(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "morning";
  if (hour < 17) return "afternoon";
  return "evening";
}
