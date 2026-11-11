import { useEffect, useRef } from "react";

export interface ViewerShortcutHandlers {
  onOverlay?: () => void;
  onMeasure?: () => void;
  onLasso?: () => void;
  onReset?: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  onEscape?: () => void;
}

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable;
}

/** Global keys for the viewer. H overlay, M measure, L lasso, R reset, arrows views. */
export function useViewerShortcuts(handlers: ViewerShortcutHandlers) {
  const latest = useRef(handlers);
  latest.current = handlers;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (isTypingTarget(event.target) || event.metaKey || event.ctrlKey || event.altKey) return;
      const current = latest.current;
      switch (event.key) {
        case "h":
        case "H":
          current.onOverlay?.();
          break;
        case "m":
        case "M":
          current.onMeasure?.();
          break;
        case "l":
        case "L":
          current.onLasso?.();
          break;
        case "r":
        case "R":
          current.onReset?.();
          break;
        case "ArrowLeft":
          if (current.onPrev) {
            event.preventDefault();
            current.onPrev();
          }
          break;
        case "ArrowRight":
          if (current.onNext) {
            event.preventDefault();
            current.onNext();
          }
          break;
        case "Escape":
          current.onEscape?.();
          break;
        default:
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
