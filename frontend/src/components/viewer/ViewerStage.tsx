import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import * as cornerstone from "@cornerstonejs/core";
import {
  acquireEngine,
  attachViewport,
  detachViewport,
  ENGINE_ID,
  initCornerstone,
  releaseEngine,
  type ViewerMode,
} from "../../lib/cornerstone";
import { Icon } from "../icons";
import { cx } from "../ui";
import { camColours, drawCam, type CamOverlay } from "./cam";

export type Highlight = [number, number][];

function clamp01(value: number) {
  return Math.min(1, Math.max(0, value));
}

function worldToImagePoint(
  viewport: cornerstone.Types.IStackViewport,
  world: [number, number, number],
): [number, number] | null {
  const data = viewport.getImageData();
  const imageData = data.imageData as unknown as { worldToIndex?: (point: number[]) => number[] };
  const [width, height] = data.dimensions;
  if (typeof imageData?.worldToIndex !== "function" || width < 2 || height < 2) return null;
  const [column, row] = imageData.worldToIndex(world);
  return [clamp01(column / (width - 1)), clamp01(row / (height - 1))];
}

function imagePointToWorld(
  viewport: cornerstone.Types.IStackViewport,
  point: [number, number],
): [number, number, number] | null {
  const data = viewport.getImageData();
  const imageData = data.imageData as unknown as { indexToWorld?: (point: number[]) => number[] };
  const [width, height] = data.dimensions;
  if (typeof imageData?.indexToWorld !== "function" || width < 2 || height < 2) return null;
  const world = imageData.indexToWorld([point[0] * (width - 1), point[1] * (height - 1), 0]);
  return [world[0], world[1], world[2]];
}

interface Props {
  imageId: string | null;
  viewLabel: string;
  patientLabel: string;
  modality: string;
  active: boolean;
  mode: ViewerMode;
  cam: CamOverlay | null;
  highlights?: Highlight[];
  onHighlight?: (points: Highlight) => void;
  showOverlay: boolean;
  opacity: number;
  split: boolean;
  splitPosition: number;
  onSplitPosition: (value: number) => void;
  resetSignal: number;
  onActivate?: () => void;
  className?: string;
}

export function ViewerStage({
  imageId,
  viewLabel,
  patientLabel,
  modality,
  active,
  mode,
  cam,
  highlights = [],
  onHighlight,
  showOverlay,
  opacity,
  split,
  splitPosition,
  onSplitPosition,
  resetSignal,
  onActivate,
  className,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const lassoCanvasRef = useRef<HTMLCanvasElement>(null);
  const viewportRef = useRef<cornerstone.Types.IStackViewport | null>(null);
  const engineRef = useRef<cornerstone.RenderingEngine | null>(null);
  const resetRef = useRef<() => void>(() => undefined);
  const camRef = useRef<CamOverlay | null>(null);
  const colourRef = useRef<{ source: CamOverlay; canvas: HTMLCanvasElement } | null>(null);
  const highlightsRef = useRef<Highlight[]>(highlights);
  const drawingRef = useRef<[number, number][] | null>(null);
  const drawHighlightsRef = useRef<() => void>(() => undefined);
  const viewportId = useRef(`miap-vp-${Math.random().toString(36).slice(2, 10)}`);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("");
  const [zoom, setZoom] = useState(100);
  const [windowLevel, setWindowLevel] = useState("");

  camRef.current = cam;
  highlightsRef.current = highlights;

  drawHighlightsRef.current = () => {
    const canvas = lassoCanvasRef.current;
    const element = hostRef.current;
    if (!canvas || !element) return;
    const rect = element.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.round(rect.width * dpr));
    const height = Math.max(1, Math.round(rect.height * dpr));
    if (canvas.width !== width) canvas.width = width;
    if (canvas.height !== height) canvas.height = height;
    canvas.style.width = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.clearRect(0, 0, rect.width, rect.height);

    const paint = (points: [number, number][], live: boolean) => {
      if (points.length < 2) return;
      context.beginPath();
      context.moveTo(points[0][0], points[0][1]);
      for (let index = 1; index < points.length; index += 1) {
        context.lineTo(points[index][0], points[index][1]);
      }
      context.closePath();
      context.fillStyle = live ? "rgba(226,169,79,0.14)" : "rgba(226,169,79,0.22)";
      context.fill();
      context.strokeStyle = "#e2a94f";
      context.lineWidth = 2;
      context.setLineDash(live ? [6, 4] : []);
      context.stroke();
      context.setLineDash([]);
    };

    const viewport = viewportRef.current;
    if (viewport) {
      for (const polygon of highlightsRef.current) {
        const points: [number, number][] = [];
        for (const point of polygon) {
          const world = imagePointToWorld(viewport, point);
          if (!world) continue;
          const canvasPoint = viewport.worldToCanvas(world);
          points.push([canvasPoint[0], canvasPoint[1]]);
        }
        paint(points, false);
      }
    }
    if (drawingRef.current) paint(drawingRef.current, true);
  };

  useEffect(() => {
    drawHighlightsRef.current();
  }, [highlights, status]);

  useEffect(() => {
    if (mode !== "lasso" && drawingRef.current) {
      drawingRef.current = null;
      drawHighlightsRef.current();
    }
  }, [mode]);

  useEffect(() => {
    const element = hostRef.current;
    if (!element || !imageId) return;
    let disposed = false;
    let released = false;
    let engine: cornerstone.RenderingEngine | null = null;

    const release = () => {
      if (released) return;
      released = true;
      if (!engine) return;
      detachViewport(viewportId.current, ENGINE_ID);
      try {
        engine.disableElement(viewportId.current);
      } catch {
        // The viewport never finished enabling.
      }
      releaseEngine();
    };

    setStatus("loading");
    setZoom(100);
    setWindowLevel("");

    (async () => {
      await initCornerstone();
      if (disposed) return;
      engine = acquireEngine();
      engine.enableElement({
        viewportId: viewportId.current,
        type: cornerstone.Enums.ViewportType.STACK,
        element,
      });
      const viewport = engine.getViewport(viewportId.current) as cornerstone.Types.IStackViewport;
      viewportRef.current = viewport;
      engineRef.current = engine;
      await viewport.setStack([`miap:${imageId}`], 0);
      if (disposed) return;
      viewport.render();
      attachViewport(viewportId.current, ENGINE_ID, mode);
      setStatus("ready");
    })().catch((error: unknown) => {
      if (disposed) return;
      release();
      setStatus("error");
      setMessage(error instanceof Error ? error.message : String(error));
    });

    const reset = () => {
      const viewport = viewportRef.current;
      if (!viewport) return;
      viewport.resetCamera();
      viewport.resetProperties();
      viewport.render();
    };
    resetRef.current = reset;

    let lastTap = 0;
    const onTouchEnd = () => {
      const now = Date.now();
      if (now - lastTap < 300) reset();
      lastTap = now;
    };
    const onContextMenu = (event: MouseEvent) => event.preventDefault();

    const updateCorners = () => {
      const viewport = viewportRef.current;
      if (!viewport) return;
      const scale = viewport.getZoom();
      if (Number.isFinite(scale) && scale > 0) setZoom(Math.max(1, Math.round(scale * 100)));
      const range = viewport.getProperties().voiRange;
      if (range) {
        const width = range.upper - range.lower;
        setWindowLevel(`W ${Math.round(width)} · L ${Math.round(range.lower + width / 2)}`);
      }
    };

    const drawOverlay = () => {
      const viewport = viewportRef.current;
      const canvas = canvasRef.current;
      const source = camRef.current;
      if (!viewport || !canvas) return;
      if (!source) {
        colourRef.current = null;
        canvas.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
        return;
      }
      let prepared = colourRef.current;
      if (!prepared || prepared.source !== source) {
        prepared = { source, canvas: camColours(source) };
        colourRef.current = prepared;
      }
      drawCam(canvas, viewport, prepared.canvas, source.mapping ?? "centre");
    };

    const drawLassos = () => drawHighlightsRef.current();
    element.addEventListener(cornerstone.Enums.Events.IMAGE_RENDERED, updateCorners);
    element.addEventListener(cornerstone.Enums.Events.IMAGE_RENDERED, drawOverlay);
    element.addEventListener(cornerstone.Enums.Events.IMAGE_RENDERED, drawLassos);
    element.addEventListener(cornerstone.Enums.Events.CAMERA_MODIFIED, updateCorners);
    element.addEventListener(cornerstone.Enums.Events.CAMERA_MODIFIED, drawOverlay);
    element.addEventListener(cornerstone.Enums.Events.CAMERA_MODIFIED, drawLassos);
    element.addEventListener(cornerstone.Enums.Events.VOI_MODIFIED, updateCorners);
    element.addEventListener("dblclick", reset);
    element.addEventListener("touchend", onTouchEnd);
    element.addEventListener("contextmenu", onContextMenu);

    const observer = new ResizeObserver(() => {
      engineRef.current?.resize(true, false);
      drawOverlay();
      drawLassos();
      updateCorners();
    });
    observer.observe(element);

    return () => {
      disposed = true;
      observer.disconnect();
      element.removeEventListener(cornerstone.Enums.Events.IMAGE_RENDERED, updateCorners);
      element.removeEventListener(cornerstone.Enums.Events.IMAGE_RENDERED, drawOverlay);
      element.removeEventListener(cornerstone.Enums.Events.IMAGE_RENDERED, drawLassos);
      element.removeEventListener(cornerstone.Enums.Events.CAMERA_MODIFIED, updateCorners);
      element.removeEventListener(cornerstone.Enums.Events.CAMERA_MODIFIED, drawOverlay);
      element.removeEventListener(cornerstone.Enums.Events.CAMERA_MODIFIED, drawLassos);
      element.removeEventListener(cornerstone.Enums.Events.VOI_MODIFIED, updateCorners);
      element.removeEventListener("dblclick", reset);
      element.removeEventListener("touchend", onTouchEnd);
      element.removeEventListener("contextmenu", onContextMenu);
      release();
      viewportRef.current = null;
      engineRef.current = null;
      colourRef.current = null;
      resetRef.current = () => undefined;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [imageId]);

  useEffect(() => {
    if (resetSignal === 0 || status !== "ready") return;
    resetRef.current();
  }, [resetSignal, status]);

  useEffect(() => {
    const viewport = viewportRef.current;
    const canvas = canvasRef.current;
    if (!viewport || !canvas) return;
    if (!cam) {
      colourRef.current = null;
      const context = canvas.getContext("2d");
      context?.clearRect(0, 0, canvas.width, canvas.height);
      return;
    }
    let prepared = colourRef.current;
    if (!prepared || prepared.source !== cam) {
      prepared = { source: cam, canvas: camColours(cam) };
      colourRef.current = prepared;
    }
    drawCam(canvas, viewport, prepared.canvas, cam.mapping ?? "centre");
  }, [cam, status]);

  if (!imageId) {
    return (
      <div className={cx("flex h-full w-full flex-col items-center justify-center gap-2 bg-viewer px-4 text-center", className)}>
        <Icon name="image" size={22} className="text-viewer-muted" />
        <p className="text-xs text-viewer-muted">{viewLabel}</p>
        <p className="max-w-[14rem] text-sm text-viewer-muted">This view was not uploaded. The study is incomplete.</p>
      </div>
    );
  }

  function moveSplit(event: ReactPointerEvent<HTMLButtonElement>) {
    const host = hostRef.current;
    if (!host) return;
    const rect = host.getBoundingClientRect();
    const percent = ((event.clientX - rect.left) / rect.width) * 100;
    onSplitPosition(Math.min(100, Math.max(0, Math.round(percent))));
  }

  function lassoPoint(event: ReactPointerEvent<HTMLCanvasElement>): [number, number] {
    const rect = event.currentTarget.getBoundingClientRect();
    return [event.clientX - rect.left, event.clientY - rect.top];
  }

  function onLassoDown(event: ReactPointerEvent<HTMLCanvasElement>) {
    if (event.button !== 0 || mode !== "lasso" || !viewportRef.current) return;
    event.preventDefault();
    try {
      event.currentTarget.setPointerCapture(event.pointerId);
    } catch {
      // Capture is best-effort; drawing still follows pointermove on the canvas.
    }
    drawingRef.current = [lassoPoint(event)];
    drawHighlightsRef.current();
  }

  function onLassoMove(event: ReactPointerEvent<HTMLCanvasElement>) {
    const points = drawingRef.current;
    if (!points) return;
    event.preventDefault();
    const point = lassoPoint(event);
    const last = points[points.length - 1];
    if (Math.hypot(point[0] - last[0], point[1] - last[1]) < 1.5) return;
    points.push(point);
    drawHighlightsRef.current();
  }

  function onLassoUp(event: ReactPointerEvent<HTMLCanvasElement>) {
    const points = drawingRef.current;
    drawingRef.current = null;
    if (!points) return;
    event.preventDefault();
    const viewport = viewportRef.current;
    if (points.length >= 3 && viewport && onHighlight) {
      // Store points in the image frame so the outline survives reloads and PDFs.
      const normalised = points
        .map(([x, y]) => {
          const world = viewport.canvasToWorld([x, y]);
          return worldToImagePoint(viewport, [world[0], world[1], world[2]]);
        })
        .filter((point): point is [number, number] => point !== null);
      if (normalised.length >= 3) onHighlight(normalised);
    }
    drawHighlightsRef.current();
  }

  function onLassoCancel() {
    drawingRef.current = null;
    drawHighlightsRef.current();
  }

  return (
    <div
      className={cx(
        "viewer-scope relative h-full w-full select-none overflow-hidden bg-viewer",
        active && "ring-1 ring-inset ring-petrol",
        className,
      )}
      onPointerDown={onActivate}
    >
      <div ref={hostRef} className="cornerstone-element" />
      <canvas
        ref={canvasRef}
        aria-hidden="true"
        className="pointer-events-none absolute inset-0"
        style={{
          opacity: showOverlay && cam ? Math.min(1, Math.max(0, opacity)) : 0,
          clipPath: split && cam ? `inset(0 0 0 ${splitPosition}%)` : undefined,
        }}
      />
      <canvas
        ref={lassoCanvasRef}
        aria-hidden="true"
        className={cx("absolute inset-0", mode === "lasso" ? "cursor-crosshair" : "pointer-events-none")}
        style={{ touchAction: "none" }}
        onPointerDown={onLassoDown}
        onPointerMove={onLassoMove}
        onPointerUp={onLassoUp}
        onPointerCancel={onLassoCancel}
      />
      {mode === "lasso" ? (
        <p className="pointer-events-none absolute left-1/2 top-3 -translate-x-1/2 whitespace-nowrap rounded-full border border-white/20 bg-viewer/85 px-3 py-1 text-xs text-viewer-ink">
          Draw a loop around an abnormal area
        </p>
      ) : null}

      <div className="pointer-events-none absolute left-3 top-2.5 max-w-[70%] space-y-0.5 drop-shadow">
        <p className="truncate text-xs font-medium text-viewer-ink">{patientLabel}</p>
        <p className="text-xs text-viewer-muted">{viewLabel}</p>
      </div>
      <div className="pointer-events-none absolute right-3 top-2.5 space-y-0.5 text-right drop-shadow">
        <p className="text-xs text-viewer-ink">{modality}</p>
        <p className="font-mono text-xs text-viewer-muted">{imageId.slice(0, 8)}</p>
      </div>
      {status === "ready" ? (
        <>
          <p className="pointer-events-none absolute bottom-2.5 left-3 font-mono text-xs text-viewer-muted drop-shadow">
            {zoom}%
          </p>
          <p className="pointer-events-none absolute bottom-2.5 right-3 font-mono text-xs text-viewer-muted drop-shadow">
            {windowLevel}
          </p>
        </>
      ) : null}

      {split && showOverlay && cam ? (
        <button
          type="button"
          role="slider"
          aria-label="Before and after split position"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={splitPosition}
          className="absolute inset-y-0 z-10 w-11 -translate-x-1/2 cursor-ew-resize touch-none"
          style={{ left: `${splitPosition}%` }}
          onPointerDown={(event) => {
            event.currentTarget.setPointerCapture(event.pointerId);
            moveSplit(event);
          }}
          onPointerMove={(event) => {
            if (event.currentTarget.hasPointerCapture(event.pointerId)) moveSplit(event);
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft") {
              event.preventDefault();
              onSplitPosition(Math.max(0, splitPosition - 2));
            } else if (event.key === "ArrowRight") {
              event.preventDefault();
              onSplitPosition(Math.min(100, splitPosition + 2));
            }
          }}
        >
          <span className="pointer-events-none absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-viewer-ink/70" />
          <span className="pointer-events-none absolute left-1/2 top-1/2 flex h-8 w-8 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full border border-viewer-ink/50 bg-viewer/80 text-viewer-ink shadow">
            <Icon name="split" size={15} />
          </span>
        </button>
      ) : null}

      {status === "loading" ? (
        <div className="absolute inset-0 flex items-center justify-center bg-viewer/70 text-sm text-viewer-muted">
          Loading pixels…
        </div>
      ) : null}
      {status === "error" ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-viewer/90 p-6 text-center">
          <p className="text-sm font-medium text-signal">Image could not be displayed</p>
          <p className="max-w-sm text-xs text-viewer-muted">{message}</p>
        </div>
      ) : null}
    </div>
  );
}
