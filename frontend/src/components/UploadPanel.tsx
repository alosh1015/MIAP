import { useRef, useState, type ChangeEvent, type ReactNode } from "react";
import { api, ApiError, type DeidReceipt, type Validation } from "../api/client";
import { Badge, Card } from "./ui";

interface Outcome {
  filename: string;
  ok: boolean;
  message: string;
  validation?: Validation;
  receipt?: DeidReceipt;
}

export function UploadPanel({ caseId, onUploaded }: { caseId: string; onUploaded: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [modality, setModality] = useState("");
  const [bodyPart, setBodyPart] = useState("");
  const [laterality, setLaterality] = useState("");
  const [view, setView] = useState("");
  const [busy, setBusy] = useState(false);
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);

  function pick(event: ChangeEvent<HTMLInputElement>) {
    setFiles(Array.from(event.target.files ?? []));
    setOutcomes([]);
  }

  async function upload() {
    if (files.length === 0) return;
    setBusy(true);
    const results: Outcome[] = [];
    for (const file of files) {
      try {
        const response = await api.uploadImage(caseId, file, {
          modality,
          body_part: bodyPart,
          laterality,
          view,
        });
        results.push({
          filename: file.name,
          ok: true,
          message: `${response.image.modality ?? "unknown"} · ${response.image.rows ?? "?"}×${response.image.cols ?? "?"}`,
          validation: response.validation,
          receipt: response.deid_receipt,
        });
      } catch (caught) {
        const apiError = caught instanceof ApiError ? caught : null;
        results.push({
          filename: file.name,
          ok: false,
          message: apiError ? `${apiError.message}${apiError.detail ? ` — ${apiError.detail}` : ""}` : "Upload failed",
        });
      }
    }
    setOutcomes(results);
    setFiles([]);
    if (inputRef.current) inputRef.current.value = "";
    setBusy(false);
    if (results.some((result) => result.ok)) onUploaded();
  }

  const last = [...outcomes].reverse().find((outcome) => outcome.ok);

  return (
    <Card className="p-5">
      <h2 className="text-sm font-semibold text-slate-900">Add images</h2>
      <p className="mt-1 text-xs text-slate-500">
        DICOM (.dcm) or a plain X-ray image (PNG/JPEG). The file is de-identified before it is written to
        storage; the original bytes are discarded.
      </p>

      <div className="mt-4 grid gap-3 md:grid-cols-[1fr_auto]">
        <label className="block">
          <span className="text-xs font-medium text-slate-600">Files</span>
          <input
            ref={inputRef}
            type="file"
            accept=".dcm,application/dicom,image/png,image/jpeg"
            multiple
            onChange={pick}
            className="focus-ring mt-1 block w-full rounded-lg border border-dashed border-slate-300 bg-slate-50 px-3 py-3 text-xs text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-white file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-slate-700"
          />
        </label>
        <button
          type="button"
          onClick={upload}
          disabled={busy || files.length === 0}
          className="focus-ring self-end rounded-lg bg-clinical-600 px-4 py-2 text-sm font-semibold text-white hover:bg-clinical-700 disabled:opacity-50"
        >
          {busy ? "De-identifying…" : files.length > 1 ? `Upload ${files.length} files` : "Upload"}
        </button>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Modality override">
          <select value={modality} onChange={(event) => setModality(event.target.value)} className={selectClass}>
            <option value="">Read from file</option>
            <option value="xray">X-ray</option>
            <option value="mammogram">Mammogram</option>
          </select>
        </Field>
        <Field label="Body part (plain images)">
          <input
            value={bodyPart}
            onChange={(event) => setBodyPart(event.target.value)}
            placeholder="CHEST"
            className={inputClass}
          />
        </Field>
        <Field label="Laterality">
          <select value={laterality} onChange={(event) => setLaterality(event.target.value)} className={selectClass}>
            <option value="">Not specified</option>
            <option value="L">Left</option>
            <option value="R">Right</option>
          </select>
        </Field>
        <Field label="Mammogram view">
          <select value={view} onChange={(event) => setView(event.target.value)} className={selectClass}>
            <option value="">Not specified</option>
            <option value="CC">CC</option>
            <option value="MLO">MLO</option>
          </select>
        </Field>
      </div>

      {outcomes.length > 0 ? (
        <div className="mt-4 space-y-2">
          {outcomes.map((outcome) => (
            <div
              key={outcome.filename}
              className={`rounded-lg border px-3 py-2 text-xs ${
                outcome.ok ? "border-slate-200 bg-slate-50" : "border-rose-200 bg-rose-50"
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-medium text-slate-700">{outcome.filename}</span>
                {outcome.ok ? <Badge tone="good">stored de-identified</Badge> : <Badge tone="bad">rejected</Badge>}
              </div>
              <p className="mt-1 text-slate-500">{outcome.message}</p>
            </div>
          ))}
        </div>
      ) : null}

      {last?.validation ? (
        <div className="mt-4 rounded-lg border border-slate-200 bg-white">
          <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
            <span className="text-xs font-semibold text-slate-700">Validation</span>
            <Badge tone={last.validation.status === "warn" ? "warn" : "good"}>{last.validation.status}</Badge>
          </div>
          <ul className="divide-y divide-slate-100">
            {last.validation.checks.map((check) => (
              <li key={check.code} className="flex items-start gap-3 px-3 py-2 text-xs">
                <span className="mt-0.5 w-10 shrink-0 uppercase text-slate-400">{check.status}</span>
                <div>
                  <p className="font-medium text-slate-700">{check.code.replaceAll("_", " ")}</p>
                  <p className="text-slate-500">{check.detail}</p>
                </div>
              </li>
            ))}
          </ul>
          {last.receipt ? (
            <div className="border-t border-slate-100 px-3 py-2 text-[11px] text-slate-500">
              De-identification: {last.receipt.removed.length} attributes removed,{" "}
              {last.receipt.replaced.length} replaced, {last.receipt.uids_remapped} UIDs remapped.{" "}
              {last.receipt.reidentification_key_retained
                ? "Re-identification key retained."
                : "No re-identification key retained."}
              {last.receipt.warnings.length > 0 ? (
                <ul className="mt-1 list-disc pl-4 text-amber-700">
                  {last.receipt.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

const inputClass =
  "focus-ring mt-1 w-full rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-700";
const selectClass = inputClass;

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-[11px] font-medium text-slate-500">{label}</span>
      {children}
    </label>
  );
}
