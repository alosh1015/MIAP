import { useEffect, useRef, useState, type ReactNode } from "react";
import * as cornerstone from "@cornerstonejs/core";
import {
  activateTool,
  attachViewport,
  detachViewport,
  ENGINE_ID,
  acquireEngine,
  initCornerstone,
  releaseEngine,
  type ViewerTool,
} from "../lib/cornerstone";

export interface CamOverlay {
  data: Float32Array;
  width: number;
  height: number;
}

interface Props {
  imageId: string | null;
  label: string;
  caption?: string;
  activeTool: ViewerTool;
  cam?: CamOverlay | null;
  overlay?: ReactNode;
  className?: string;
  resetSignal?: number;
}

function camColours(cam: CamOverlay): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = cam.width;
  canvas.height = cam.height;
  const context = canvas.getContext("2d");
  if (!context) return canvas;
  const image = context.createImageData(cam.width, cam.height);
  for (let index = 0; index < cam.data.length; index += 1) {
    const value = Math.max(0, Math.min(1, cam.data[index]));
    image.data[index * 4] = 255;
    image.data[index * 4 + 1] = Math.round(255 * (1 - value));
    image.data[index * 4 + 2] = 20;
    image.data[index * 4 + 3] = Math.round(200 * value);
  }
  context.putImageData(image, 0, 0);
  return canvas;
}

function drawCam(
  overlay: HTMLCanvasElement,
  viewport: cornerstone.Types.IStackViewport,
  source: HTMLCanvasElement,
): void {
  const element = viewport.element as HTMLDivElement;
  const rect = element.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  overlay.width = Math.max(1, Math.round(rect.width * dpr));
  overlay.height = Math.max(1, Math.round(rect.height * dpr));
  overlay.style.width = `${rect.width}px`;
  overlay.style.height = `${rect.height}px`;

  const context = overlay.getContext("2d");
  if (!context) return;
  context.setTransform(1, 0, 0, 1, 0, 0);
  context.clearRect(0, 0, overlay.width, overlay.height);

  const imageData = viewport.getImageData();
  if (!imageData) return;
  const [cols, rows] = imageData.dimensions;
  const side = Math.min(cols, rows);
  const left = (cols - side) / 2;
  const top = (rows - side) / 2;
  // Cornerstone 3.33's getImageData() no longer exposes indexToWorld, so derive
  // world coordinates from the image geometry the way StackViewport does internally.
  const { origin: imageOrigin, spacing, direction } = imageData;
  const world = (x: number, y: number): [number, number, number] => [
    imageOrigin[0] + direction[0] * x * spacing[0] + direction[3] * y * spacing[1],
    imageOrigin[1] + direction[1] * x * spacing[0] + direction[4] * y * spacing[1],
    imageOrigin[2] + direction[2] * x * spacing[0] + direction[5] * y * spacing[1],
  ];

  const origin = viewport.worldToCanvas(world(left, top));
  const right = viewport.worldToCanvas(world(left + side, top));
  const bottom = viewport.worldToCanvas(world(left, top + side));

  const ax = (right[0] - origin[0]) / source.width;
  const ay = (right[1] - origin[1]) / source.width;
  const bx = (bottom[0] - origin[0]) / source.height;
  const by = (bottom[1] - origin[1]) / source.height;

  context.setTransform(
    ax * dpr,
    ay * dpr,
    bx * dpr,
    by * dpr,
    origin[0] * dpr,
    origin[1] * dpr,
  );
  context.globalCompositeOperation = "screen";
  context.globalAlpha = 0.85;
  context.imageSmoothingEnabled = true;
  context.drawImage(source, 0, 0);
  context.setTransform(1, 0, 0, 1, 0, 0);
}

export function ImageViewer({
  imageId,
  label,
  caption,
  activeTool,
  cam,
  overlay,
  className,
  resetSignal,
}: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const viewportRef = useRef<cornerstone.Types.IStackViewport | null>(null);
  const engineRef = useRef<cornerstone.RenderingEngine | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [message, setMessage] = useState("");
  const [windowLevel, setWindowLevel] = useState("");
  const viewportId = useRef(`miap-vp-${Math.random().toString(36).slice(2, 10)}`);
  const camRef = useRef<CamOverlay | null>(cam ?? null);
  camRef.current = cam ?? null;
  const colourRef = useRef<{ source: CamOverlay; canvas: HTMLCanvasElement } | null>(null);

  useEffect(() => {
    const element = hostRef.current;
    if (!element || !imageId) return;
    let disposed = false;
    const engineId = ENGINE_ID;
    let engine: cornerstone.RenderingEngine | null = null;
    let released = false;

    const release = () => {
      if (released) return;
      released = true;
      if (!engine) return;
      detachViewport(viewportId.current, engineId);
      try {
        engine.disableElement(viewportId.current);
      } catch {
        // Viewport was never enabled.
      }
      releaseEngine();
    };

    setStatus("loading");
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
      attachViewport(viewportId.current, engineId);
      activateTool(activeTool);
      setStatus("ready");
    })().catch((error: unknown) => {
      if (disposed) return;
      release();
      setStatus("error");
      setMessage(error instanceof Error ? error.message : String(error));
    });

    const updateVoi = () => {
      const range = viewportRef.current?.getProperties().voiRange;
      if (!range) return;
      const width = range.upper - range.lower;
      setWindowLevel(`W ${Math.round(width)} / L ${Math.round(range.lower + width / 2)}`);
    };
    const reset = () => {
      viewportRef.current?.resetCamera();
      viewportRef.current?.render();
    };

    element.addEventListener(cornerstone.Enums.Events.VOI_MODIFIED, updateVoi);
    element.addEventListener("dblclick", reset);
    const observer = new ResizeObserver(() => {
      engineRef.current?.resize(true, false);
      drawOverlay();
    });
    observer.observe(element);
    const drawOverlay = () => {
      const viewport = viewportRef.current;
      const canvas = canvasRef.current;
      const active = camRef.current;
      if (!viewport || !canvas || !active) return;
      let prepared = colourRef.current;
      if (!prepared || prepared.source !== active) {
        prepared = { source: active, canvas: camColours(active) };
        colourRef.current = prepared;
      }
      drawCam(canvas, viewport, prepared.canvas);
    };
    element.addEventListener(cornerstone.Enums.Events.IMAGE_RENDERED, drawOverlay);
    element.addEventListener(cornerstone.Enums.Events.CAMERA_MODIFIED, drawOverlay);

    return () => {
      disposed = true;
      observer.disconnect();
      element.removeEventListener(cornerstone.Enums.Events.VOI_MODIFIED, updateVoi);
      element.removeEventListener(cornerstone.Enums.Events.IMAGE_RENDERED, drawOverlay);
      element.removeEventListener(cornerstone.Enums.Events.CAMERA_MODIFIED, drawOverlay);
      element.removeEventListener("dblclick", reset);
      release();
      engineRef.current = null;
      viewportRef.current = null;
    };
    // activeTool is applied by the effect below; cam changes are drawn by the redraw effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [imageId]);

  useEffect(() => {
    if (status === "ready") activateTool(activeTool);
  }, [activeTool, status]);

  useEffect(() => {
    if (resetSignal === undefined || status !== "ready") return;
    viewportRef.current?.resetCamera();
    viewportRef.current?.render();
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
    drawCam(canvas, viewport, prepared.canvas);
  }, [cam, status]);

  if (!imageId) {
    return (
      <div className={`flex flex-col items-center justify-center bg-slate-900/95 text-center ${className ?? ""}`}>
        <span className="text-xs uppercase tracking-[0.2em] text-slate-500">{label}</span>
        <p className="mt-3 max-w-[16rem] text-sm text-slate-400">
          This view was not uploaded. The study is incomplete.
        </p>
      </div>
    );
  }

  return (
    <div className={`relative overflow-hidden bg-black ${className ?? ""}`}>
      <div ref={hostRef} className="cornerstone-element" />
      <canvas ref={canvasRef} className="pointer-events-none absolute inset-0" />
      <div className="pointer-events-none absolute left-3 top-3 rounded bg-black/70 px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-white">
        {label}
      </div>
      {caption ? (
        <div className="pointer-events-none absolute right-3 top-3 rounded bg-black/60 px-2 py-1 text-[11px] text-slate-300">
          {caption}
        </div>
      ) : null}
      {windowLevel && status === "ready" ? (
        <div className="pointer-events-none absolute bottom-3 right-3 rounded bg-black/60 px-2 py-1 font-mono text-[11px] text-slate-300">
          {windowLevel}
        </div>
      ) : null}
      {status === "loading" ? (
        <div className="absolute inset-0 flex items-center justify-center bg-black/60 text-sm text-slate-300">
          Loading pixels…
        </div>
      ) : null}
      {status === "error" ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/80 p-6 text-center">
          <p className="text-sm font-medium text-rose-300">Image could not be displayed</p>
          <p className="max-w-sm text-xs text-slate-400">{message}</p>
        </div>
      ) : null}
      {imgOverlay(overlay)}
    </div>
  );
}

function imgOverlay(overlay: ReactNode) {
  if (!overlay) return null;
  return <div className="pointer-events-none absolute inset-x-0 bottom-0">{overlay}</div>;
}
