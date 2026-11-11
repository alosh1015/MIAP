import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import {
  api,
  ApiError,
  saveBlob,
  type CaseQuery,
  type CaseSummary,
} from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Icon } from "../components/icons";
import {
  Badge,
  Button,
  Dialog,
  EmptyState,
  ErrorNote,
  Field,
  Input,
  Panel,
  PageHeader,
  Select,
  Skeleton,
  Table,
  Td,
  Th,
  cx,
  formatDay,
  prettyLabel,
  relativeTime,
} from "../components/ui";
import { AiFlag } from "./DashboardPage";

const PAGE = 25;

export function WorklistPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [rows, setRows] = useState<CaseSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [exportOpen, setExportOpen] = useState(false);

  const isAdmin = user?.role === "administrator";
  const isResearcher = user?.role === "researcher";

  const query = useMemo<CaseQuery>(
    () => ({
      sort: params.get("sort") ?? "created_at",
      order: (params.get("order") as "asc" | "desc" | null) ?? "desc",
      ai_flag: (params.get("ai_flag") as CaseQuery["ai_flag"]) ?? undefined,
      modality: params.get("modality") ?? undefined,
      consent: params.get("consent") ?? undefined,
      q: params.get("q") ?? undefined,
      offset: Number(params.get("offset") ?? 0),
      limit: PAGE,
    }),
    [params],
  );

  const load = useCallback(() => {
    setLoading(true);
    api
      .listCases(query)
      .then((data) => {
        setRows(data);
        setError(null);
      })
      .catch((caught) =>
        setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not load studies"),
      )
      .finally(() => setLoading(false));
  }, [query]);

  useEffect(load, [load]);

  function update(patch: Record<string, string | undefined>) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(patch)) {
      if (value === undefined || value === "") next.delete(key);
      else next.set(key, value);
    }
    if (!("offset" in patch)) next.delete("offset");
    setParams(next, { replace: true });
  }

  function sortBy(key: string) {
    const currentSort = query.sort;
    const currentOrder = query.order;
    update({
      sort: key,
      order: currentSort === key && currentOrder === "desc" ? "asc" : "desc",
    });
  }

  const activeFilters = ["ai_flag", "modality", "consent"].filter((key) => params.get(key));

  return (
    <div>
      <PageHeader
        title={isAdmin ? "Studies" : isResearcher ? "Research dataset" : "Worklist"}
        actions={
          <>
            {isResearcher ? (
              <Button icon="download" onClick={() => setExportOpen(true)}>
                Export dataset
              </Button>
            ) : null}
            {!isAdmin ? (
              <>
                {!isResearcher ? (
                  <Button icon="user" onClick={() => navigate("/patients/new")}>
                    New patient
                  </Button>
                ) : null}
                <Button icon="new-study" variant="primary" onClick={() => navigate("/cases/new")}>
                  New study
                </Button>
              </>
            ) : null}
          </>
        }
      />

      <Panel>
        <div className="flex flex-wrap items-center gap-2 px-4 pb-3 pt-4">
          <div className="relative min-w-[14rem] flex-1">
            <Icon
              name="search"
              size={16}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted"
            />
            <Input
              defaultValue={query.q ?? ""}
              placeholder="Search pseudonym"
              aria-label="Search pseudonym"
              className="pl-9"
              onKeyDown={(event) => {
                if (event.key === "Enter") update({ q: (event.target as HTMLInputElement).value.trim() });
              }}
              onBlur={(event) => {
                if (event.target.value.trim() !== (query.q ?? "")) update({ q: event.target.value.trim() });
              }}
            />
          </div>

          {!isAdmin ? (
            <Select
              aria-label="AI flag filter"
              value={query.ai_flag ?? ""}
              onChange={(event) => update({ ai_flag: event.target.value })}
              className="w-auto max-w-[11rem]"
            >
              <option value="">Any AI flag</option>
              <option value="flagged">Flagged</option>
              <option value="clear">Clear</option>
              <option value="pending">Pending</option>
              <option value="failed">Failed</option>
              <option value="none">No analysis</option>
            </Select>
          ) : null}

          <Select
            aria-label="Modality filter"
            value={query.modality ?? ""}
            onChange={(event) => update({ modality: event.target.value })}
            className="w-auto max-w-[11rem]"
          >
            <option value="">Any modality</option>
            <option value="xray">X-ray</option>
            <option value="mammogram">Mammogram</option>
          </Select>

          <Select
            aria-label="Consent filter"
            value={query.consent ?? ""}
            onChange={(event) => update({ consent: event.target.value })}
            className="w-auto max-w-[11rem]"
          >
            <option value="">Any consent</option>
            <option value="clinical">Clinical</option>
            <option value="research">Research</option>
            <option value="teaching">Teaching</option>
          </Select>

          {activeFilters.length > 0 ? (
            <Button
              size="sm"
              variant="ghost"
              icon="close"
              onClick={() =>
                update({ ai_flag: undefined, modality: undefined, consent: undefined, q: undefined })
              }
            >
              Clear
            </Button>
          ) : null}

          {!loading && rows.length > 0 ? (
            <p className="ml-auto text-xs text-muted tabular-nums">
              {rows.length} stud{rows.length === 1 ? "y" : "ies"}
            </p>
          ) : null}
        </div>

        <ErrorNote message={error} />

        {loading && rows.length === 0 ? (
          <div className="space-y-px px-4 pb-4">
            {Array.from({ length: 8 }).map((_, index) => (
              <div key={index} className="flex items-center gap-4 py-2.5">
                <Skeleton className="h-3.5 w-40" />
                <Skeleton className="h-3.5 w-20" />
                <Skeleton className="h-3.5 w-16" />
                <Skeleton className="ml-auto h-3.5 w-24" />
              </div>
            ))}
          </div>
        ) : !loading && rows.length === 0 ? (
          <EmptyState
            icon="worklist"
            title={activeFilters.length > 0 ? "No studies match these filters" : "No studies yet"}
            action={
              activeFilters.length > 0 ? (
                <Button size="sm" onClick={() => update({ ai_flag: undefined, modality: undefined, consent: undefined, q: undefined })}>
                  Clear filters
                </Button>
              ) : !isAdmin ? (
                <Button variant="primary" icon="new-study" onClick={() => navigate("/cases/new")}>
                  New study
                </Button>
              ) : undefined
            }
          />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th sortKey="patient" sort={query.sort} order={query.order} onSort={sortBy}>
                  {isAdmin || isResearcher ? "Pseudonym" : "Patient"}
                </Th>
                <Th sortKey="created_at" sort={query.sort} order={query.order} onSort={sortBy} className="hidden sm:table-cell">
                  Study date
                </Th>
                <Th sortKey="modality" sort={query.sort} order={query.order} onSort={sortBy} className="hidden sm:table-cell">
                  Modality
                </Th>
                <Th
                  sortKey="image_count"
                  sort={query.sort}
                  order={query.order}
                  onSort={sortBy}
                  align="right"
                  className="hidden sm:table-cell"
                >
                  Images
                </Th>
                {!isAdmin ? (
                  <Th sortKey="ai_flag" sort={query.sort} order={query.order} onSort={sortBy}>
                    AI flag
                  </Th>
                ) : null}
                {!isAdmin ? (
                  <Th
                    sortKey="findings_to_review"
                    sort={query.sort}
                    order={query.order}
                    onSort={sortBy}
                    align="right"
                    className="hidden md:table-cell"
                  >
                    To review
                  </Th>
                ) : null}
                <Th sortKey="status" sort={query.sort} order={query.order} onSort={sortBy}>
                  Status
                </Th>
                <Th align="right" className="hidden sm:table-cell">
                  Last activity
                </Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((study) => (
                <tr key={study.id} className="hover:bg-surface-2/60">
                  <Td>
                    <Link to={`/cases/${study.id}`} className="whitespace-nowrap font-medium text-ink hover:text-petrol">
                      {isAdmin ? study.pseudonym : study.patient_display}
                    </Link>
                    {!isAdmin && study.identity_visible && study.pseudonym !== study.patient_display ? (
                      <p className="mt-0.5 font-mono text-xs text-muted">{study.pseudonym}</p>
                    ) : null}
                  </Td>
                  <Td className="hidden whitespace-nowrap text-xs text-muted sm:table-cell">{formatDay(study.created_at)}</Td>
                  <Td className="hidden sm:table-cell">{study.modality ? prettyLabel(study.modality) : "—"}</Td>
                  <Td align="right" className="hidden sm:table-cell">
                    {study.image_count}
                  </Td>
                  {!isAdmin ? (
                    <Td>
                      <AiFlag flag={study.ai_flag} />
                    </Td>
                  ) : null}
                  {!isAdmin ? (
                    <Td align="right" className="hidden md:table-cell">
                      {study.findings_to_review > 0 ? (
                        <span className="inline-flex items-center gap-2">
                          <span className="h-1.5 w-14 overflow-hidden rounded-full bg-rule">
                            <span
                              className={cx(
                                "block h-full rounded-full",
                                study.reviewed >= study.findings_to_review ? "bg-petrol" : "bg-signal",
                              )}
                              style={{
                                width: `${Math.min(100, Math.round((study.reviewed / study.findings_to_review) * 100))}%`,
                              }}
                            />
                          </span>
                          <span className="font-mono text-xs text-muted">
                            {study.reviewed}/{study.findings_to_review}
                          </span>
                        </span>
                      ) : (
                        <span className="text-xs text-muted">—</span>
                      )}
                    </Td>
                  ) : null}
                  <Td>
                    <Badge tone={study.status === "archived" ? "neutral" : "petrol"}>
                      {prettyLabel(study.status)}
                    </Badge>
                  </Td>
                  <Td align="right" className="hidden whitespace-nowrap text-xs text-muted sm:table-cell">
                    {relativeTime(study.last_job?.updated_at ?? study.created_at)}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}

        {rows.length > 0 && (rows.length === PAGE || (query.offset ?? 0) > 0) ? (
          <div className="flex items-center justify-end gap-2 px-4 py-3">
            <Button
              size="sm"
              disabled={(query.offset ?? 0) === 0}
              onClick={() => update({ offset: String(Math.max(0, (query.offset ?? 0) - PAGE)) })}
            >
              Previous
            </Button>
            <Button
              size="sm"
              disabled={rows.length < PAGE}
              onClick={() => update({ offset: String((query.offset ?? 0) + PAGE) })}
            >
              Next
            </Button>
          </div>
        ) : null}
      </Panel>

      {isResearcher ? (
        <ResearchExportDialog
          open={exportOpen}
          onClose={() => setExportOpen(false)}
          filters={{ consent: query.consent, modality: query.modality }}
        />
      ) : null}
    </div>
  );
}

function ResearchExportDialog({
  open,
  onClose,
  filters,
}: {
  open: boolean;
  onClose: () => void;
  filters: { consent?: string; modality?: string };
}) {
  const [format, setFormat] = useState<"csv" | "json">("csv");
  const [consent, setConsent] = useState(filters.consent ?? "");
  const [modality, setModality] = useState(filters.modality ?? "");
  const [limit, setLimit] = useState("500");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const blob = await api.createExport({
        format,
        consent: consent || null,
        modality: modality || null,
        limit: Number(limit) || null,
      });
      saveBlob(blob, `miap-export-${new Date().toISOString().slice(0, 10)}.${format}`);
      onClose();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail || caught.message : "Export failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Export research dataset"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" icon="download" loading={busy} onClick={run}>
            Create export
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="text-sm leading-relaxed text-muted">
          Pseudonyms, study metadata and result summaries. No identity, notes or decisions. Every export
          is audited and row-capped.
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Format">
            <Select value={format} onChange={(event) => setFormat(event.target.value as "csv" | "json")}>
              <option value="csv">CSV</option>
              <option value="json">JSON</option>
            </Select>
          </Field>
          <Field label="Row limit">
            <Input
              type="number"
              min={1}
              max={5000}
              value={limit}
              onChange={(event) => setLimit(event.target.value)}
            />
          </Field>
          <Field label="Consent">
            <Select value={consent} onChange={(event) => setConsent(event.target.value)}>
              <option value="">Any consent</option>
              <option value="clinical">Clinical</option>
              <option value="research">Research</option>
              <option value="teaching">Teaching</option>
            </Select>
          </Field>
          <Field label="Modality">
            <Select value={modality} onChange={(event) => setModality(event.target.value)}>
              <option value="">Any modality</option>
              <option value="xray">X-ray</option>
              <option value="mammogram">Mammogram</option>
            </Select>
          </Field>
        </div>
        <ErrorNote message={error} />
      </div>
    </Dialog>
  );
}
