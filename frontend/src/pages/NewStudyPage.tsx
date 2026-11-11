import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError, type PatientSummary } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Icon } from "../components/icons";
import { DECISION_SUPPORT_NOTICE, DEID_NOTICE, ScreenWarning, TB_NOTICE } from "../components/ScreenWarning";
import {
  Button,
  EmptyState,
  ErrorNote,
  Field,
  Input,
  Panel,
  PanelHeader,
  PageHeader,
  Select,
} from "../components/ui";

function generatedPseudonym(): string {
  return `MIAP-${crypto.randomUUID().slice(0, 8).toUpperCase()}`;
}

export function NewStudyPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isClinician = user?.role === "clinician";

  const [pseudonym, setPseudonym] = useState(generatedPseudonym);
  const [consent, setConsent] = useState("clinical");
  const [retentionDays, setRetentionDays] = useState("365");
  const [patient, setPatient] = useState<PatientSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [lookupNumber, setLookupNumber] = useState("");
  const [lookupBusy, setLookupBusy] = useState(false);
  const [lookupMessage, setLookupMessage] = useState<string | null>(null);
  const [recent, setRecent] = useState<PatientSummary[]>([]);

  useEffect(() => {
    if (!isClinician) return;
    api
      .listPatients(undefined, 6)
      .then(setRecent)
      .catch(() => undefined);
  }, [isClinician]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const study = await api.createCase({
        pseudonym: pseudonym.trim(),
        consent,
        retention_days: retentionDays ? Number(retentionDays) : null,
        patient_id: patient?.id ?? null,
      });
      navigate(`/cases/${study.id}`, { replace: true });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not create the study");
    } finally {
      setBusy(false);
    }
  }

  async function lookup(event: FormEvent) {
    event.preventDefault();
    if (!lookupNumber.trim()) return;
    setLookupBusy(true);
    setLookupMessage(null);
    try {
      const result = await api.lookupPatient(lookupNumber.trim());
      if (result.found && result.patient) {
        setPatient(result.patient);
        setLookupMessage(null);
      } else {
        setLookupMessage("No patient with that hospital number is registered to you.");
      }
    } catch (caught) {
      setLookupMessage(caught instanceof ApiError ? caught.detail || caught.message : "Lookup failed");
    } finally {
      setLookupBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="New study"
        actions={
          <Link to="/worklist" className="text-sm font-medium text-petrol hover:underline">
            Back to worklist
          </Link>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Panel>
          <form onSubmit={submit}>
            <PanelHeader title="Study" />
            <div className="space-y-4 p-5">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Pseudonym" htmlFor="study-pseudonym" hint="No identifiers.">
                  <Input
                    id="study-pseudonym"
                    required
                    maxLength={120}
                    value={pseudonym}
                    onChange={(event) => setPseudonym(event.target.value)}
                    className="font-mono"
                  />
                </Field>
                <Field label="Consent basis" htmlFor="study-consent">
                  <Select id="study-consent" value={consent} onChange={(event) => setConsent(event.target.value)}>
                    <option value="clinical">Clinical care</option>
                    <option value="research">Research — visible to researcher accounts</option>
                    <option value="teaching">Teaching</option>
                  </Select>
                </Field>
                <Field label="Retention (days)" htmlFor="study-retention">
                  <Input
                    id="study-retention"
                    type="number"
                    min={1}
                    max={3650}
                    value={retentionDays}
                    onChange={(event) => setRetentionDays(event.target.value)}
                  />
                </Field>
              </div>

              <ErrorNote message={error} />

              <div className="flex items-center justify-end gap-2 border-t border-rule pt-4">
                <Button onClick={() => navigate(-1)}>Cancel</Button>
                <Button
                  type="submit"
                  variant="primary"
                  icon="plus"
                  loading={busy}
                  disabled={!pseudonym.trim()}
                >
                  Create study
                </Button>
              </div>
            </div>
          </form>
        </Panel>

        <div className="space-y-4">
          {isClinician ? (
            <>
              <Panel>
                <PanelHeader title="Patient record" />
                {patient ? (
                  <div className="p-4">
                    <p className="font-medium text-ink">{patient.name}</p>
                    <p className="mt-0.5 font-mono text-xs text-muted">
                      {patient.hospital_number} · {patient.sex}
                      {patient.age != null ? ` · ${patient.age} y` : ""}
                    </p>
                    <div className="mt-3 flex gap-2">
                      <Button size="sm" onClick={() => setPatient(null)}>
                        Unlink
                      </Button>
                      <Link
                        to={`/patients/${patient.id}`}
                        className="inline-flex h-8 items-center rounded-md px-3 text-xs font-medium text-petrol hover:bg-petrol-soft"
                      >
                        Open record
                      </Link>
                    </div>
                  </div>
                ) : (
                  <form className="space-y-3 p-4" onSubmit={lookup}>
                    <Field label="Hospital number" htmlFor="study-lookup">
                      <Input
                        id="study-lookup"
                        value={lookupNumber}
                        onChange={(event) => setLookupNumber(event.target.value)}
                      />
                    </Field>
                    <Button icon="search" loading={lookupBusy} type="submit" className="w-full">
                      Link existing patient
                    </Button>
                    {lookupMessage ? <p className="text-xs text-muted">{lookupMessage}</p> : null}
                  </form>
                )}
              </Panel>

              {!patient ? (
                <Panel>
                  <PanelHeader title="Recent patients" />
                  {recent.length === 0 ? (
                    <EmptyState
                      icon="users"
                      title="No patients yet"
                      action={
                        <Button size="sm" icon="user" onClick={() => navigate("/patients/new")}>
                          New patient
                        </Button>
                      }
                    />
                  ) : (
                    <ul className="divide-y divide-rule">
                      {recent.map((entry) => (
                        <li key={entry.id}>
                          <button
                            type="button"
                            onClick={() => setPatient(entry)}
                            className="flex w-full items-center justify-between gap-2 px-4 py-2.5 text-left text-sm hover:bg-surface-2"
                          >
                            <span className="min-w-0">
                              <span className="block truncate font-medium text-ink">{entry.name}</span>
                              <span className="block truncate font-mono text-xs text-muted">
                                {entry.hospital_number}
                              </span>
                            </span>
                            <Icon name="link" size={16} className="shrink-0 text-muted" />
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </Panel>
              ) : null}
            </>
          ) : (
            <Panel className="p-5">
              <p className="text-sm leading-relaxed text-muted">
                Identity is never attached to this account. The pseudonym is the research key.
              </p>
            </Panel>
          )}
        </div>
      </div>

      <ScreenWarning items={[DECISION_SUPPORT_NOTICE, TB_NOTICE, DEID_NOTICE]} />
    </div>
  );
}
