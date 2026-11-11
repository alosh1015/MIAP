import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, type PatientDetail } from "../api/client";
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
  PanelHeader,
  PageHeader,
  Select,
  Skeleton,
  Table,
  Td,
  Th,
  formatDate,
  formatDay,
  prettyLabel,
} from "../components/ui";

export function PatientPage() {
  const { patientId = "" } = useParams();
  const navigate = useNavigate();
  const [patient, setPatient] = useState<PatientDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);

  const load = useCallback(() => {
    api
      .getPatient(patientId)
      .then(setPatient)
      .catch((caught) => setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not load this patient"));
  }, [patientId]);

  useEffect(load, [load]);

  if (error) {
    return (
      <div>
        <PageHeader title="Patient" />
        <ErrorNote message={error} />
        <Link to="/worklist" className="mt-4 inline-block text-sm font-medium text-petrol hover:underline">
          Back to worklist
        </Link>
      </div>
    );
  }

  if (!patient) {
    return (
      <div className="space-y-6">
        <div className="space-y-2">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-7 w-56" />
        </div>
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={patient.name}
        crumb={
          <Link to="/worklist" className="hover:text-ink">
            Worklist
          </Link>
        }
        subtitle={
          <span className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-mono text-ink">{patient.hospital_number}</span>
            <span className="text-rule-strong">·</span>
            <span className="capitalize">{patient.sex}</span>
            {patient.age != null ? (
              <>
                <span className="text-rule-strong">·</span>
                <span>{patient.age} years</span>
              </>
            ) : null}
            {patient.dob ? (
              <>
                <span className="text-rule-strong">·</span>
                <span>born {formatDay(patient.dob)}</span>
              </>
            ) : null}
          </span>
        }
        actions={
          <>
            <Button icon="settings" onClick={() => setEditOpen(true)}>
              Edit record
            </Button>
            <Button variant="primary" icon="plus" onClick={() => navigate("/cases/new")}>
              New study
            </Button>
          </>
        }
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Panel>
          <PanelHeader title="Studies" />
          {patient.cases.length === 0 ? (
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
                  <Th>Pseudonym</Th>
                  <Th>Modality</Th>
                  <Th>Status</Th>
                  <Th align="right">Created</Th>
                </tr>
              </thead>
              <tbody>
                {patient.cases.map((study) => (
                  <tr key={study.id} className="hover:bg-surface-2/60">
                    <Td>
                      <Link to={`/cases/${study.id}`} className="font-mono text-sm text-ink hover:text-petrol">
                        {study.pseudonym}
                      </Link>
                    </Td>
                    <Td>{study.modality ? prettyLabel(study.modality) : "—"}</Td>
                    <Td>
                      <Badge tone={study.status === "archived" ? "neutral" : "petrol"}>
                        {prettyLabel(study.status)}
                      </Badge>
                    </Td>
                    <Td align="right" className="text-xs text-muted">
                      {formatDate(study.created_at)}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Panel>

        <div className="space-y-4">
          <Panel className="p-5">
            <h2 className="text-base font-semibold text-ink">Record</h2>
            <dl className="mt-3 space-y-2 text-sm">
              <Row label="Hospital number" value={patient.hospital_number} mono />
              <Row label="Sex" value={prettyLabel(patient.sex)} />
              <Row label="Date of birth" value={patient.dob ? formatDay(patient.dob) : "Not recorded"} />
              <Row label="Created" value={formatDate(patient.created_at)} />
              <Row label="Updated" value={formatDate(patient.updated_at)} />
            </dl>
            <p className="mt-4 border-t border-rule pt-3 text-xs leading-relaxed text-muted">
              <Icon name="shield" size={13} className="mr-1.5 inline align-[-2px] text-petrol" />
              Visible only to you. Researchers and administrators see the pseudonym, and every view is audited.
            </p>
          </Panel>
        </div>
      </div>

      <EditPatientDialog
        open={editOpen}
        patient={patient}
        onClose={() => setEditOpen(false)}
        onSaved={(updated) => {
          setPatient(updated);
          setEditOpen(false);
        }}
      />
    </div>
  );
}

function EditPatientDialog({
  open,
  patient,
  onClose,
  onSaved,
}: {
  open: boolean;
  patient: PatientDetail;
  onClose: () => void;
  onSaved: (patient: PatientDetail) => void;
}) {
  const [name, setName] = useState(patient.name);
  const [hospitalNumber, setHospitalNumber] = useState(patient.hospital_number);
  const [sex, setSex] = useState(patient.sex);
  const [dob, setDob] = useState(patient.dob ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(patient.name);
    setHospitalNumber(patient.hospital_number);
    setSex(patient.sex);
    setDob(patient.dob ?? "");
    setError(null);
  }, [open, patient]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const updated = await api.updatePatient(patient.id, {
        name: name.trim(),
        hospital_number: hospitalNumber.trim(),
        sex,
        dob: dob || null,
      });
      onSaved(updated);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not update the record");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Edit patient record"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save}>
            Save changes
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="Full name">
          <Input value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field label="Hospital number">
          <Input value={hospitalNumber} onChange={(event) => setHospitalNumber(event.target.value)} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Sex">
            <Select value={sex} onChange={(event) => setSex(event.target.value)}>
              <option value="unknown">Not recorded</option>
              <option value="female">Female</option>
              <option value="male">Male</option>
              <option value="other">Other</option>
            </Select>
          </Field>
          <Field label="Date of birth">
            <Input type="date" value={dob} onChange={(event) => setDob(event.target.value)} />
          </Field>
        </div>
        <ErrorNote message={error} />
      </div>
    </Dialog>
  );
}

function Row({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="shrink-0 text-muted">{label}</dt>
      <dd className={`text-right text-ink ${mono ? "font-mono text-xs" : ""}`}>{value}</dd>
    </div>
  );
}
