import { useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import { activateViewerTools, initCornerstone, type ViewerMode } from "../../lib/cornerstone";
import { useViewerShortcuts } from "../../lib/viewerShortcuts";
import { Icon } from "../icons";
import { cx } from "../ui";
import type { CamOverlay } from "./cam";
import { ViewerStage, type Highlight } from "./ViewerStage";
import type { StudyView } from "./ViewStrip";

export type CamState = "idle" | "loading" | "ready" | "none";

interface Props {
  caseId: string | null;
  views: StudyView[];
  grid: boolean;
  activeImageId: string | null;
  onActiveImage: (imageId: string) => void;
  patientLabel: string;
  modality: string;
  resultImageId: string | null;
  cam: CamOverlay | null;
  camState: CamState;
  defaultOpacity: number;
  defaultSplit: boolean;
  fill?: boolean;
}

export function StudyViewer({
  caseId,
  views,
  grid,
  activeImageId,
  onActiveImage,
  patientLabel,
  modality,
  resultImageId,
  cam,
  camState,
  defaultOpacity,
  defaultSplit,
  fill = false,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [mode, setMode] = useState<ViewerMode>("navigate");
  const [showOverlay, setShowOverlay] = useState(true);
  const [opacity, setOpacity] = useState(defaultOpacity);
  const [split, setSplit] = useState(defaultSplit);
  const [splitPosition, setSplitPosition] = useState(50);
  const [resetSignal, setResetSignal] = useState(0);
  const [fullscreen, setFullscreen] = useState(false);
  const [controlsVisible, setControlsVisible] = useState(true);
  const [pinned, setPinned] = useState(false);
  const [highlights, setHighlights] = useState<Record<string, Highlight[]>>({});
  const pinnedRef = useRef(false);
  const hideTimer = useRef<number | null>(null);

  const present = views.filter((view) => view.image);
  const stageViews = grid ? views : present.filter((view) => view.id === activeImageId).slice(0, 1);
  const fallbackViews = stageViews.length > 0 ? stageViews : present.slice(0, 1);
  const activeHighlights = activeImageId ? highlights[activeImageId] ?? [] : [];
  const annotationKey = present.map((view) => view.image!.id).join(",");

  const currentIndex = present.findIndex((view) => view.id === activeImageId);

  useEffect(() => setOpacity(defaultOpacity), [defaultOpacity]);
  useEffect(() => setSplit(defaultSplit), [defaultSplit]);

  useEffect(() => {
    if (!caseId || !annotationKey) return;
    let cancelled = false;
    const ids = annotationKey.split(",");
    Promise.all(ids.map((id) => api.listAnnotations(caseId, id)))
      .then((lists) => {
        if (cancelled) return;
        const loaded: Record<string, Highlight[]> = {};
        lists.forEach((list, index) => {
          loaded[ids[index]] = list.map((annotation) => annotation.points);
        });
        setHighlights(loaded);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [caseId, annotationKey]);

  useEffect(() => {
    let cancelled = false;
    initCornerstone()
      .then(() => {
        if (!cancelled) activateViewerTools(mode);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [mode]);

  useEffect(() => {
    const onChange = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  useEffect(() => {
    return () => {
      if (hideTimer.current) window.clearTimeout(hideTimer.current);
    };
  }, []);

  function reveal() {
    setControlsVisible(true);
    if (hideTimer.current) window.clearTimeout(hideTimer.current);
    hideTimer.current = window.setTimeout(() => {
      if (!pinnedRef.current) setControlsVisible(false);
    }, 2500);
  }

  function scheduleHide() {
    if (hideTimer.current) window.clearTimeout(hideTimer.current);
    if (!pinnedRef.current) hideTimer.current = window.setTimeout(() => setControlsVisible(false), 1200);
  }

  function pin(value: boolean) {
    pinnedRef.current = value;
    setPinned(value);
  }

  function step(delta: number) {
    if (present.length < 2) return;
    const from = currentIndex === -1 ? 0 : currentIndex;
    const next = present[(from + delta + present.length) % present.length];
    if (next.image) onActiveImage(next.image.id);
  }

  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await containerRef.current?.requestFullscreen();
    } catch {
      /* Browsers may refuse fullscreen without a user gesture. */
    }
  }

  useViewerShortcuts({
    onOverlay: cam ? () => setShowOverlay((value) => !value) : undefined,
    onMeasure: () => setMode((value) => (value === "measure" ? "navigate" : "measure")),
    onLasso: () => setMode((value) => (value === "lasso" ? "navigate" : "lasso")),
    onReset: () => setResetSignal((value) => value + 1),
    onPrev: present.length > 1 ? () => step(-1) : undefined,
    onNext: present.length > 1 ? () => step(1) : undefined,
    onEscape: () => {
      if (mode === "measure" || mode === "lasso") setMode("navigate");
    },
  });

  async function addHighlight(imageId: string, points: Highlight) {
    setHighlights((previous) => ({
      ...previous,
      [imageId]: [...(previous[imageId] ?? []), points],
    }));
    if (!caseId) return;
    try {
      const saved = await api.createAnnotation(caseId, imageId, points);
      setHighlights((previous) => ({
        ...previous,
        [imageId]: (previous[imageId] ?? []).map((polygon) =>
          polygon === points ? saved.points : polygon,
        ),
      }));
    } catch {
      setHighlights((previous) => ({
        ...previous,
        [imageId]: (previous[imageId] ?? []).filter((polygon) => polygon !== points),
      }));
    }
  }

  async function clearHighlights() {
    const imageId = activeImageId;
    if (!imageId) return;
    if (caseId) {
      try {
        await api.clearAnnotations(caseId, imageId);
      } catch {
        return;
      }
    }
    setHighlights((previous) => {
      if (!previous[imageId]) return previous;
      const next = { ...previous };
      delete next[imageId];
      return next;
    });
  }

  const overlayReady = Boolean(cam);
  const columns = grid ? 2 : 1;

  return (
    <div
      ref={containerRef}
      className={cx("relative overflow-hidden rounded-lg bg-viewer", fill && !fullscreen && "h-full")}
      style={fullscreen ? { height: "100vh" } : undefined}
      onPointerMove={reveal}
      onPointerDown={reveal}
      onMouseEnter={reveal}
      onMouseLeave={scheduleHide}
      onFocusCapture={() => {
        pin(true);
        setControlsVisible(true);
      }}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          pin(false);
          scheduleHide();
        }
      }}
    >
      <div
        className={cx(
        "grid gap-px bg-rule",
        !fullscreen && !fill && "h-[480px] sm:h-[540px] lg:h-[620px]",
        !fullscreen && fill && "h-full min-h-[420px] xl:min-h-0",
      )}
        style={{
          gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`,
          gridTemplateRows: grid ? "repeat(2, minmax(0, 1fr))" : "minmax(0, 1fr)",
          height: fullscreen ? "100%" : undefined,
        }}
      >
        {fallbackViews.map((view) => (
          <ViewerStage
            key={view.id || view.label}
            imageId={view.image?.id ?? null}
            viewLabel={view.label}
            patientLabel={patientLabel}
            modality={modality}
            active={view.id === activeImageId}
            mode={mode}
            cam={view.id === resultImageId ? cam : null}
            highlights={view.image ? highlights[view.image.id] ?? [] : []}
            onHighlight={(points) => {
              const id = view.image?.id;
              if (id) void addHighlight(id, points);
            }}
            showOverlay={showOverlay}
            opacity={opacity}
            split={split}
            splitPosition={splitPosition}
            onSplitPosition={setSplitPosition}
            resetSignal={resetSignal}
            onActivate={() => view.image && onActiveImage(view.image.id)}
          />
        ))}
        {fallbackViews.length === 0 ? (
          <div className="flex h-full items-center justify-center bg-viewer text-sm text-viewer-muted">
            No viewable images in this study.
          </div>
        ) : null}
      </div>

      {camState === "loading" ? (
        <p className="pointer-events-none absolute left-1/2 top-12 z-10 -translate-x-1/2 rounded-full border border-white/20 bg-viewer/85 px-3 py-1 text-xs text-viewer-muted">
          Preparing area map…
        </p>
      ) : null}
      {camState === "none" ? (
        <p className="pointer-events-none absolute left-1/2 top-12 z-10 -translate-x-1/2 rounded-full border border-white/20 bg-viewer/85 px-3 py-1 text-xs text-viewer-muted">
          No region highlighted for this finding.
        </p>
      ) : null}

      <div
        className={cx(
          "absolute bottom-3 left-1/2 z-20 flex max-w-[calc(100%-1rem)] -translate-x-1/2 items-center gap-0.5 overflow-x-auto rounded-lg border border-white/15 bg-viewer/90 p-1 shadow-lg backdrop-blur transition-opacity",
          controlsVisible || pinned ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        role="toolbar"
        aria-label="Viewer controls"
      >
        <BarButton
          icon="heat"
          label="Toggle area overlay (H)"
          active={showOverlay && overlayReady}
          disabled={!overlayReady}
          onClick={() => setShowOverlay((value) => !value)}
        />
        <label className={cx("hidden items-center px-1.5 sm:flex", !overlayReady && "opacity-40")}>
          <span className="sr-only">Overlay opacity</span>
          <input
            type="range"
            min={0.1}
            max={1}
            step={0.05}
            value={opacity}
            disabled={!overlayReady}
            onChange={(event) => setOpacity(Number(event.target.value))}
            className="h-1 w-20 accent-petrol"
          />
        </label>
        <BarButton
          icon="split"
          label="Before and after split"
          active={split && overlayReady}
          disabled={!overlayReady}
          onClick={() => setSplit((value) => !value)}
        />
        <span className="mx-0.5 h-6 w-px bg-white/15" aria-hidden="true" />
        <BarButton icon="measure" label="Measure (M)" active={mode === "measure"} onClick={() => setMode(mode === "measure" ? "navigate" : "measure")} />
        <BarButton icon="lasso" label="Lasso highlight (L)" active={mode === "lasso"} onClick={() => setMode(mode === "lasso" ? "navigate" : "lasso")} />
        {activeHighlights.length > 0 ? (
          <BarButton icon="trash" label="Clear highlights" onClick={clearHighlights} />
        ) : null}
        <BarButton icon="reset" label="Reset view (R)" onClick={() => setResetSignal((value) => value + 1)} />
        <BarButton icon="chevron-left" label="Previous view" disabled={present.length < 2} onClick={() => step(-1)} />
        <BarButton icon="chevron-right" label="Next view" disabled={present.length < 2} onClick={() => step(1)} />
        <BarButton icon="fullscreen" label={fullscreen ? "Exit fullscreen" : "Fullscreen"} onClick={toggleFullscreen} />
      </div>
    </div>
  );
}

function BarButton({
  icon,
  label,
  active = false,
  disabled = false,
  onClick,
}: {
  icon: "heat" | "split" | "measure" | "lasso" | "trash" | "reset" | "chevron-left" | "chevron-right" | "fullscreen" | "info";
  label: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-pressed={active || undefined}
      disabled={disabled}
      onClick={onClick}
      className={cx(
        "flex h-11 w-11 shrink-0 items-center justify-center rounded-md transition",
        active ? "bg-white/15 text-signal" : "text-viewer-ink/85 hover:bg-white/10 hover:text-viewer-ink",
        disabled && "cursor-not-allowed opacity-35",
      )}
    >
      <Icon name={icon} size={19} />
    </button>
  );
}
