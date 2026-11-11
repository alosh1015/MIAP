import * as cornerstone from "@cornerstonejs/core";

export type CamMapping = "centre" | "full";

export interface CamOverlay {
  data: Float32Array;
  width: number;
  height: number;
  mapping?: CamMapping;
}

export function camColours(cam: CamOverlay): HTMLCanvasElement {
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

/**
 * Draw the CAM canvas over the viewport using the viewport's own world→canvas
 * transform, so the overlay tracks zoom, pan and window/level. Opacity and the
 * before/after split are CSS concerns on the canvas element.
 */
export function drawCam(
  overlay: HTMLCanvasElement,
  viewport: cornerstone.Types.IStackViewport,
  source: HTMLCanvasElement,
  mapping: CamMapping = "centre",
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
  // A centre-crop profile maps to the middle square; a resize profile maps to
  // the whole stored frame.
  const spanX = mapping === "full" ? cols : Math.min(cols, rows);
  const spanY = mapping === "full" ? rows : Math.min(cols, rows);
  const left = (cols - spanX) / 2;
  const top = (rows - spanY) / 2;
  const { origin: imageOrigin, spacing, direction } = imageData;
  const world = (x: number, y: number): [number, number, number] => [
    imageOrigin[0] + direction[0] * x * spacing[0] + direction[3] * y * spacing[1],
    imageOrigin[1] + direction[1] * x * spacing[0] + direction[4] * y * spacing[1],
    imageOrigin[2] + direction[2] * x * spacing[0] + direction[5] * y * spacing[1],
  ];

  const origin = viewport.worldToCanvas(world(left, top));
  const right = viewport.worldToCanvas(world(left + spanX, top));
  const bottom = viewport.worldToCanvas(world(left, top + spanY));

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
  context.globalAlpha = 1;
  context.imageSmoothingEnabled = true;
  context.drawImage(source, 0, 0);
  context.setTransform(1, 0, 0, 1, 0, 0);
}
