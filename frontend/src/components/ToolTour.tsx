import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { Role } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Icon, type IconName } from "./icons";
import { Button, cx } from "./ui";

interface TourStep {
  icon: IconName;
  title: string;
  body: string;
}

const STEPS: Record<Role, TourStep[]> = {
  clinician: [
    {
      icon: "dashboard",
      title: "Dashboard",
      body: "Patients, open studies and the findings waiting for your decision.",
    },
    {
      icon: "worklist",
      title: "Worklist",
      body: "Every study you own. Sort by AI flag or review progress, then open a study.",
    },
    {
      icon: "new-study",
      title: "New study",
      body: "Register or link a patient, then upload an X-ray or a four-view mammogram.",
    },
    {
      icon: "heat",
      title: "Study workspace",
      body: "Click a finding to see the area the model used. Confirm or dismiss each finding. Scroll to zoom, drag to pan, right-drag for window and level. H toggles the overlay, M measures, R resets.",
    },
    {
      icon: "models",
      title: "Models",
      body: "What MIAP can analyse, with version, licence and validation. Only approved models run.",
    },
  ],
  researcher: [
    {
      icon: "dashboard",
      title: "Dashboard",
      body: "Pseudonymised studies, batch runs and the models approved for research.",
    },
    {
      icon: "database",
      title: "Dataset",
      body: "Filter studies with research consent and export pseudonyms and metadata.",
    },
    {
      icon: "new-study",
      title: "New study",
      body: "Create a pseudonymous study, then upload de-identified images.",
    },
    {
      icon: "heat",
      title: "Study workspace",
      body: "Technical findings and per-finding area maps. Compare models with batch runs.",
    },
    {
      icon: "models",
      title: "Models",
      body: "Approved models are selectable. Candidates are listed but cannot run.",
    },
  ],
  administrator: [
    {
      icon: "shield",
      title: "Governance",
      body: "Queue, audit, retention and model approvals. No pixels, identity or findings.",
    },
    {
      icon: "audit",
      title: "Audit",
      body: "Verify the hash chain or export the events as NDJSON.",
    },
    {
      icon: "users",
      title: "Users",
      body: "Create accounts, change roles and deactivate access.",
    },
    {
      icon: "retention",
      title: "Retention",
      body: "Preview due cases, then delete expired data. Audit events remain.",
    },
    {
      icon: "models",
      title: "Model approvals",
      body: "Approve a model against a recorded benchmark digest, or revoke it.",
    },
  ],
};

const STORAGE_PREFIX = "miap.tour.v1";

function storageKey(userId: string): string {
  return `${STORAGE_PREFIX}:${userId}`;
}

function hasSeenTour(userId: string): boolean {
  try {
    return localStorage.getItem(storageKey(userId)) === "done";
  } catch {
    return true;
  }
}

function markTourSeen(userId: string): void {
  try {
    localStorage.setItem(storageKey(userId), "done");
  } catch {
    // A blocked storage still leaves the tour usable for this session.
  }
}

export function startTour(): void {
  window.dispatchEvent(new Event("miap:tour"));
}

export function ToolTour() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(0);
  const panelRef = useRef<HTMLDivElement>(null);
  const titleId = useId();

  const steps = user ? STEPS[user.role] : [];
  const step = steps[index];

  const finish = useCallback(() => {
    if (user) markTourSeen(user.id);
    setOpen(false);
  }, [user]);

  const next = useCallback(() => {
    if (index < steps.length - 1) setIndex((value) => value + 1);
    else finish();
  }, [index, steps.length, finish]);

  const back = useCallback(() => setIndex((value) => Math.max(0, value - 1)), []);

  useEffect(() => {
    if (!user) {
      setOpen(false);
      return;
    }
    setIndex(0);
    if (hasSeenTour(user.id)) return;
    const timer = window.setTimeout(() => setOpen(true), 400);
    return () => window.clearTimeout(timer);
  }, [user?.id]);

  useEffect(() => {
    const reopen = () => {
      setIndex(0);
      setOpen(true);
    };
    window.addEventListener("miap:tour", reopen);
    return () => window.removeEventListener("miap:tour", reopen);
  }, []);

  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panelRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        finish();
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        next();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        back();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener("keydown", onKey);
    };
  }, [open, finish, next, back]);

  if (!open || !step) return null;

  return (
    <div
      className="fixed inset-0 z-[70] flex items-end justify-center bg-viewer/60 p-4 backdrop-blur-[2px] sm:items-center"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) finish();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="w-full max-w-md rounded-2xl bg-surface shadow-2xl outline-none dialog-in"
      >
        <div className="flex items-center justify-between gap-3 px-5 pb-1 pt-4">
          <span className="flex items-center gap-2 text-xs font-medium text-muted">
            <Icon name={step.icon} size={16} className="text-petrol" />
            Tour · {index + 1} of {steps.length}
          </span>
          <button
            type="button"
            onClick={finish}
            aria-label="Skip tour"
            className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-2 hover:text-ink"
          >
            <Icon name="close" size={17} />
          </button>
        </div>

        <div className="px-5 py-6">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-petrol-soft text-petrol">
            <Icon name={step.icon} size={23} />
          </div>
          <h2 id={titleId} className="mt-4 text-2xl font-semibold leading-tight text-ink">
            {step.title}
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">{step.body}</p>
          <div className="mt-5 flex gap-1.5" aria-hidden="true">
            {steps.map((entry, position) => (
              <span
                key={`${entry.title}-${position}`}
                className={cx(
                  "h-1 rounded-full transition-[width,background-color] duration-150 ease-out",
                  position === index ? "w-6 bg-petrol" : "w-1.5 bg-rule",
                )}
              />
            ))}
          </div>
        </div>

        <div className="flex items-center justify-between gap-2 px-5 pb-4 pt-3">
          <Button variant="ghost" onClick={finish}>
            Skip
          </Button>
          <div className="flex items-center gap-2">
            {index > 0 ? <Button onClick={back}>Back</Button> : null}
            <Button variant="primary" onClick={next}>
              {index === steps.length - 1 ? "Done" : "Next"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
