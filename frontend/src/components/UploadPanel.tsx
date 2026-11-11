import { useRef, useState, type ChangeEvent } from "react";
import { api, ApiError, type DeidReceipt, type Validation } from "../api/client";
import { Icon } from "./icons";
import { Badge, Button, Field, Input, Notice, Panel, PanelHeader, Select, cx } from "./ui";

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
        const response = await api.uploadImage(caseId, file, { modality, body_part: bodyPart, laterality, view });
        results.push({
          filename: file.name,
          ok: true,
          message: `${response.image.modality ?? "unknown"} · ${response.image.rows ?? "?"}×${response.image.cols ?? "?"} · stored de-identified`,
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
    <Panel>
      <PanelHeader title="Add images" />
      <div className="space-y-4 px-4 py-4">
        <label
          className={cx(
            "flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-md border border-dashed border-rule-strong/40 bg-surface-2 px-4 py-6 text-center transition hover:border-petrol/60",
            busy && "pointer-events-none opacity-60",
          )}
        >
          <Icon name="upload" size={22} className="text-muted" />
          <span className="text-sm font-medium text-ink">
            {files.length > 0 ? `${files.length} file${files.length === 1 ? "" : "s"} selected` : "Choose files"}
          </span>
          <span className="text-xs text-muted">.dcm, PNG or JPEG</span>
          <input
            ref={inputRef}
            type="file"
            accept=".dcm,application/dicom,image/png,image/jpeg"
            multiple
            onChange={pick}
            className="sr-only"
          />
        </label>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Modality override" htmlFor="upload-modality">
            <Select id="upload-modality" value={modality} onChange={(event) => setModality(event.target.value)}>
              <option value="">Read from the file</option>
              <option value="xray">X-ray</option>
              <option value="mammogram">Mammogram</option>
            </Select>
          </Field>
          <Field label="Body part (plain images)" htmlFor="upload-body-part">
            <Input
              id="upload-body-part"
              value={bodyPart}
              placeholder="e.g. knee, wrist, chest"
              onChange={(event) => setBodyPart(event.target.value)}
            />
          </Field>
          <Field label="Laterality" htmlFor="upload-laterality">
            <Select id="upload-laterality" value={laterality} onChange={(event) => setLaterality(event.target.value)}>
              <option value="">Not specified</option>
              <option value="L">Left</option>
              <option value="R">Right</option>
            </Select>
          </Field>
          <Field label="Mammogram view" htmlFor="upload-view">
            <Select id="upload-view" value={view} onChange={(event) => setView(event.target.value)}>
              <option value="">Not specified</option>
              <option value="CC">CC</option>
              <option value="MLO">MLO</option>
            </Select>
          </Field>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-muted">
            The original bytes are discarded after de-identification; no re-identification key is kept.
          </p>
          <Button variant="primary" icon="upload" loading={busy} disabled={files.length === 0} onClick={upload}>
            {busy ? "De-identifying…" : files.length > 1 ? `Upload ${files.length} files` : "Upload"}
          </Button>
        </div>

        {outcomes.length > 0 ? (
          <ul className="border-t border-rule">
            {outcomes.map((outcome) => (
              <li
                key={outcome.filename}
                className={cx(
                  "flex flex-wrap items-center justify-between gap-2 border-b border-rule px-1 py-2 text-sm",
                  !outcome.ok && "text-danger",
                )}
              >
                <span className="min-w-0 truncate font-medium text-ink">{outcome.filename}</span>
                <span className={cx("text-xs", outcome.ok ? "text-muted" : "text-danger")}>{outcome.message}</span>
              </li>
            ))}
          </ul>
        ) : null}

        {last?.validation ? (
          <div className="border-t border-rule pt-3">
            <div className="flex items-center justify-between gap-2 pb-2">
              <span className="text-sm font-medium text-ink">Validation</span>
              <Badge tone={last.validation.status === "warn" ? "signal" : "petrol"}>{last.validation.status}</Badge>
            </div>
            <ul className="divide-y divide-rule border-y border-rule">
              {last.validation.checks.map((check) => (
                <li key={check.code} className="flex items-start gap-3 py-2 text-sm">
                  <span className="mt-0.5 w-10 shrink-0 text-xs text-muted">{check.status}</span>
                  <div>
                    <p className="font-medium text-ink">{check.code.replaceAll("_", " ")}</p>
                    <p className="text-muted">{check.detail}</p>
                  </div>
                </li>
              ))}
            </ul>
            {last.receipt ? (
              <div className="py-2 text-xs text-muted">
                {last.receipt.removed.length} attributes removed, {last.receipt.replaced.length} replaced,{" "}
                {last.receipt.uids_remapped} UIDs remapped.{" "}
                {last.receipt.reidentification_key_retained
                  ? "Re-identification key retained."
                  : "No re-identification key retained."}
                {last.receipt.warnings.length > 0 ? (
                  <ul className="mt-1 list-disc pl-4 text-signal">
                    {last.receipt.warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}

        {outcomes.some((outcome) => !outcome.ok) ? (
          <Notice tone="signal" icon="warn">
            Rejected files were not stored.
          </Notice>
        ) : null}
      </div>
    </Panel>
  );
}
