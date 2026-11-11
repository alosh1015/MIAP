import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, ApiError, type PatientSummary } from "../api/client";
import { ScreenWarning } from "../components/ScreenWarning";
import {
  Badge,
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

function ageFromDob(dob: string): number | null {
  if (!dob) return null;
  const born = new Date(dob);
  if (Number.isNaN(born.getTime())) return null;
  const now = new Date();
  let age = now.getFullYear() - born.getFullYear();
  const month = now.getMonth() - born.getMonth();
  if (month < 0 || (month === 0 && now.getDate() < born.getDate())) age -= 1;
  return age >= 0 && age < 130 ? age : null;
}

export function NewPatientPage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [hospitalNumber, setHospitalNumber] = useState("");
  const [sex, setSex] = useState("unknown");
  const [dob, setDob] = useState("");
  const [pseudonym, setPseudonym] = useState(generatedPseudonym);
  const [consent, setConsent] = useState("clinical");
  const [retentionDays, setRetentionDays] = useState("365");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [lookupNumber, setLookupNumber] = useState("");
  const [lookupBusy, setLookupBusy] = useState(false);
  const [lookupMessage, setLookupMessage] = useState<string | null>(null);
  const [found, setFound] = useState<PatientSummary | null>(null);
  const [recent, setRecent] = useState<PatientSummary[]>([]);

  useEffect(() => {
    api
      .listPatients(undefined, 6)
      .then(setRecent)
      .catch(() => undefined);
  }, []);

  const age = ageFromDob(dob);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const patient = await api.createPatient({
        name: name.trim(),
        hospital_number: hospitalNumber.trim(),
        sex,
        dob: dob || null,
      });
      const study = await api.createCase({
        pseudonym: pseudonym.trim(),
        consent,
        retention_days: retentionDays ? Number(retentionDays) : null,
        patient_id: patient.id,
      });
      navigate(`/cases/${study.id}`, { replace: true });
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.detail || caught.message
          : "Could not create the patient and study",
      );
    } finally {
      setBusy(false);
    }
  }

  async function lookup(event?: FormEvent) {
    event?.preventDefault();
    if (!lookupNumber.trim()) return;
    setLookupBusy(true);
    setLookupMessage(null);
    setFound(null);
    try {
      const result = await api.lookupPatient(lookupNumber.trim());
      if (result.found && result.patient) setFound(result.patient);
      else setLookupMessage("No patient with that hospital number is registered to you.");
    } catch (caught) {
      setLookupMessage(caught instanceof ApiError ? caught.detail || caught.message : "Lookup failed");
    } finally {
      setLookupBusy(false);
    }
  }

  async function startStudyFor(patient: PatientSummary) {
    setBusy(true);
    setError(null);
    try {
      const study = await api.createCase({
        pseudonym: generatedPseudonym(),
        consent,
        retention_days: retentionDays ? Number(retentionDays) : null,
        patient_id: patient.id,
      });
      navigate(`/cases/${study.id}`, { replace: true });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not create the study");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="New patient"
        actions={
          <Link to="/worklist" className="text-sm font-medium text-petrol hover:underline">
            Back to worklist
          </Link>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Panel>
          <form onSubmit={submit}>
            <PanelHeader title="Patient identity" />
            <div className="space-y-4 p-5">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Full name" htmlFor="patient-name">
                  <Input
                    id="patient-name"
                    required
                    maxLength={200}
                    autoComplete="off"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                  />
                </Field>
                <Field label="Hospital number" htmlFor="patient-hospital">
                  <Input
                    id="patient-hospital"
                    required
                    maxLength={64}
                    autoComplete="off"
                    value={hospitalNumber}
                    onChange={(event) => setHospitalNumber(event.target.value)}
                  />
                </Field>
                <Field label="Sex" htmlFor="patient-sex">
                  <Select id="patient-sex" value={sex} onChange={(event) => setSex(event.target.value)}>
                    <option value="unknown">Not recorded</option>
                    <option value="female">Female</option>
                    <option value="male">Male</option>
                    <option value="other">Other</option>
                  </Select>
                </Field>
                <Field
                  label="Date of birth"
                  htmlFor="patient-dob"
                  hint={age != null ? `Age ${age} years` : undefined}
                >
                  <Input
                    id="patient-dob"
                    type="date"
                    max={new Date().toISOString().slice(0, 10)}
                    value={dob}
                    onChange={(event) => setDob(event.target.value)}
                  />
                </Field>
              </div>

              <div className="border-t border-rule pt-4">
                <h3 className="text-lg font-semibold text-ink">First study</h3>
                <div className="mt-4 grid gap-4 sm:grid-cols-3">
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
                  <Field label="Consent" htmlFor="study-consent">
                    <Select id="study-consent" value={consent} onChange={(event) => setConsent(event.target.value)}>
                      <option value="clinical">Clinical care</option>
                      <option value="research">Research — shared with researchers</option>
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
              </div>

              <ErrorNote message={error} />

              <div className="flex items-center justify-end gap-2 border-t border-rule pt-4">
                <Button onClick={() => navigate(-1)}>Cancel</Button>
                <Button
                  type="submit"
                  variant="primary"
                  icon="plus"
                  loading={busy}
                  disabled={!name.trim() || !hospitalNumber.trim() || !pseudonym.trim()}
                >
                  Create patient and study
                </Button>
              </div>
            </div>
          </form>
        </Panel>

        <div className="space-y-4">
          <Panel>
            <PanelHeader title="Already registered?" />
            <form className="space-y-3 p-4" onSubmit={lookup}>
              <Field label="Hospital number" htmlFor="lookup-number">
                <Input
                  id="lookup-number"
                  value={lookupNumber}
                  onChange={(event) => setLookupNumber(event.target.value)}
                />
              </Field>
              <Button icon="search" loading={lookupBusy} type="submit" className="w-full">
                Find patient
              </Button>
            </form>
            {lookupMessage ? <p className="px-4 pb-4 text-xs text-muted">{lookupMessage}</p> : null}
            {found ? (
              <div className="border-t border-rule px-4 py-3">
                <p className="font-medium text-ink">{found.name}</p>
                <p className="mt-0.5 font-mono text-xs text-muted">
                  {found.hospital_number} · {found.sex}
                  {found.age != null ? ` · ${found.age} y` : ""}
                </p>
                <div className="mt-3 flex gap-2">
                  <Button size="sm" variant="primary" icon="plus" loading={busy} onClick={() => startStudyFor(found)}>
                    New study
                  </Button>
                  <Link
                    to={`/patients/${found.id}`}
                    className="inline-flex h-8 items-center rounded-md px-3 text-xs font-medium text-petrol hover:bg-petrol-soft"
                  >
                    Open record
                  </Link>
                </div>
              </div>
            ) : null}
          </Panel>

          <Panel>
            <PanelHeader title="Recent patients" />
            {recent.length === 0 ? (
              <EmptyState icon="users" title="No patients yet" />
            ) : (
              <ul className="divide-y divide-rule">
                {recent.map((patient) => (
                  <li key={patient.id}>
                    <Link
                      to={`/patients/${patient.id}`}
                      className="flex items-center justify-between gap-2 px-4 py-2.5 text-sm hover:bg-surface-2"
                    >
                      <span className="min-w-0">
                        <span className="block truncate font-medium text-ink">{patient.name}</span>
                        <span className="block truncate font-mono text-xs text-muted">
                          {patient.hospital_number}
                        </span>
                      </span>
                      <Badge tone="outline">
                        {patient.case_count} stud{patient.case_count === 1 ? "y" : "ies"}
                      </Badge>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>

      <ScreenWarning
        items={[
          "Identity is stored encrypted, separately from images. Only you can open it, and every view is audited.",
          "Use synthetic or fully consented data until the ethics and data-protection review for real patient data is complete.",
        ]}
      />
    </div>
  );
}
