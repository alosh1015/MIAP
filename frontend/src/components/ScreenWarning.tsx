import { Icon } from "./icons";

export const DECISION_SUPPORT_NOTICE =
  "Decision support only. MIAP is not a diagnosis and scores are not calibrated; a clinician must review the image and the patient.";

export const TB_NOTICE =
  "MIAP does not screen for tuberculosis. A low or negative AI result does not exclude TB; use the local TB pathway.";

export const DEID_NOTICE =
  "Images are de-identified before storage; no re-identification key is kept.";

export const OVERLAY_NOTICE =
  "The overlay shows where the model looked, not proof of disease; areas outside the model input carry no heatmap and are not evidence of normality.";

export function ScreenWarning({ items }: { items: (string | null | undefined)[] }) {
  const lines = Array.from(new Set(items.filter((item): item is string => Boolean(item?.trim()))));
  if (lines.length === 0) return null;
  return (
    <section
      aria-label="Safety notice"
      className="mt-8 flex items-start gap-2.5 border-l-2 border-signal py-1 pl-3 text-xs leading-relaxed text-muted"
    >
      <Icon name="warn" size={16} className="mt-0.5 shrink-0 text-signal" />
      <div className="min-w-0">
        <p className="font-medium text-ink">Safety notice</p>
        <ul className="mt-1 space-y-0.5">
          {lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}
