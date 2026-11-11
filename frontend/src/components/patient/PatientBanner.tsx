import { Link } from "react-router-dom";
import type { PatientSummary } from "../../api/client";
import { Icon } from "../icons";
import { Badge, cx } from "../ui";

const CONSENT_LABEL: Record<string, string> = {
  clinical: "Clinical care",
  research: "Research",
  teaching: "Teaching",
};

export function PatientBanner({
  patient,
  pseudonym,
  consent,
  identityVisible,
}: {
  patient: PatientSummary | null;
  pseudonym: string;
  consent?: string;
  identityVisible: boolean;
}) {
  const identity = identityVisible && patient ? patient : null;
  const unlinked = !patient;

  return (
    <div
      className={cx(
        "z-20 flex flex-wrap items-start justify-between gap-3 rounded-xl bg-surface px-4 py-3",
      )}
    >
      <div className="flex min-w-0 items-start gap-3">
        <span
          className={cx(
            "mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
            identity ? "bg-petrol-soft text-petrol" : "bg-surface-2 text-muted",
          )}
        >
          <Icon name={identity ? "user" : "lock"} size={18} />
        </span>
        <div className="min-w-0">
          <p className="truncate text-lg font-semibold leading-tight text-ink">
            {identity ? identity.name : pseudonym}
          </p>
          {identity ? (
            <p className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
              <span className="font-mono text-xs text-ink">{identity.hospital_number}</span>
              <span className="capitalize">{identity.sex}</span>
              {identity.age != null ? <span>{identity.age} years</span> : null}
              {identity.dob ? <span className="font-mono text-xs">DOB {identity.dob}</span> : null}
            </p>
          ) : (
            <p className="mt-0.5 text-sm text-muted">
              {unlinked ? "No patient record linked." : "Identity hidden for this account."}
            </p>
          )}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <Badge tone={identity ? "petrol" : "neutral"}>
          {identity ? "Identity visible" : unlinked ? "No patient linked" : "Identity restricted"}
        </Badge>
        {consent ? <span className="text-xs text-muted">{CONSENT_LABEL[consent] ?? consent}</span> : null}
        {identity ? (
          <Link
            to={`/patients/${identity.id}`}
            className="text-sm font-medium text-petrol hover:underline"
          >
            Open record
          </Link>
        ) : null}
      </div>
    </div>
  );
}
