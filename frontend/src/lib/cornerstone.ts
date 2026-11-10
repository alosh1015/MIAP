import * as cornerstone from "@cornerstonejs/core";
import * as cornerstoneTools from "@cornerstonejs/tools";
import { api, type PixelMeta } from "../api/client";

export const TOOL_GROUP_ID = "miap-viewer-tools";
export const ENGINE_ID = "miap-rendering-engine";
const SCHEME = "miap";

export type ViewerTool = "WindowLevel" | "Pan" | "Zoom" | "Length";

let ready: Promise<void> | null = null;
let synchronizer: cornerstoneTools.Synchronizer | null = null;
let engineUsers = 0;

export function acquireEngine(): cornerstone.RenderingEngine {
  const engine =
    cornerstone.getRenderingEngine(ENGINE_ID) ?? new cornerstone.RenderingEngine(ENGINE_ID);
  engineUsers += 1;
  return engine;
}

export function releaseEngine(): void {
  engineUsers = Math.max(0, engineUsers - 1);
  if (engineUsers === 0) {
    cornerstone.getRenderingEngine(ENGINE_ID)?.destroy();
  }
}

const TOOL_NAMES: Record<ViewerTool, string> = {
  WindowLevel: cornerstoneTools.WindowLevelTool.toolName,
  Pan: cornerstoneTools.PanTool.toolName,
  Zoom: cornerstoneTools.ZoomTool.toolName,
  Length: cornerstoneTools.LengthTool.toolName,
};

function typedArray(dtype: PixelMeta["dtype"], buffer: ArrayBuffer): ArrayBufferView {
  switch (dtype) {
    case "uint8":
      return new Uint8Array(buffer);
    case "uint16":
      return new Uint16Array(buffer);
    case "int16":
      return new Int16Array(buffer);
    case "float32":
      return new Float32Array(buffer);
    default:
      throw new Error(`Unsupported pixel type: ${dtype}`);
  }
}

function percentileWindow(values: ArrayBufferView): [number, number] {
  const all = values as unknown as ArrayLike<number>;
  const stride = Math.max(1, Math.floor(all.length / 100_000));
  const sample: number[] = [];
  for (let index = 0; index < all.length; index += stride) sample.push(all[index]);
  sample.sort((a, b) => a - b);
  const low = sample[Math.floor(sample.length * 0.02)] ?? 0;
  const high = sample[Math.floor(sample.length * 0.98)] ?? 1;
  const width = Math.max(1, high - low);
  return [low + width / 2, width];
}

const inFlight = new Map<string, Promise<Record<string, unknown>>>();

async function fetchMiapImage(imageId: string): Promise<Record<string, unknown>> {
  const id = imageId.slice(SCHEME.length + 1);
  const { meta, buffer } = await api.getPixels(id);
  let scalar = typedArray(meta.dtype, buffer);

  if (meta.slope !== 1 || meta.intercept !== 0) {
    const source = scalar as unknown as ArrayLike<number>;
    const rescaled = new Float32Array(source.length);
    for (let index = 0; index < source.length; index += 1) {
      rescaled[index] = source[index] * meta.slope + meta.intercept;
    }
    scalar = rescaled;
  }

  let windowCenter: number;
  let windowWidth: number;
  if (meta.window_center != null && meta.window_width != null && meta.window_width > 0) {
    windowCenter = meta.window_center;
    windowWidth = meta.window_width;
  } else {
    [windowCenter, windowWidth] = percentileWindow(scalar);
  }

  const existing = cornerstone.cache.getImage(imageId);
  if (existing) return existing as unknown as Record<string, unknown>;

  const { cols, rows } = meta;
  const imagePlaneModule = {
    frameOfReferenceUID: imageId,
    rows,
    columns: cols,
    imageOrientationPatient: [1, 0, 0, 0, 1, 0],
    rowCosines: [1, 0, 0],
    columnCosines: [0, 1, 0],
    imagePositionPatient: [0, 0, 0],
    pixelSpacing: [meta.row_pixel_spacing, meta.column_pixel_spacing],
    rowPixelSpacing: meta.row_pixel_spacing,
    columnPixelSpacing: meta.column_pixel_spacing,
  };
  const bytesPerElement = { uint8: 1, uint16: 2, int16: 2, float32: 4 }[meta.dtype];
  const imagePixelModule = {
    samplesPerPixel: 1,
    photometricInterpretation: "MONOCHROME2",
    rows,
    columns: cols,
    bitsAllocated: bytesPerElement * 8,
    bitsStored: bytesPerElement * 8,
    highBit: bytesPerElement * 8 - 1,
    pixelRepresentation: meta.dtype === "int16" ? 1 : 0,
  };
  cornerstone.utilities.genericMetadataProvider.add(imageId, {
    type: "imagePlaneModule",
    metadata: imagePlaneModule,
  });
  cornerstone.utilities.genericMetadataProvider.add(imageId, {
    type: "imagePixelModule",
    metadata: imagePixelModule,
  });
  cornerstone.utilities.genericMetadataProvider.add(imageId, {
    type: "generalSeriesModule",
    metadata: { modality: "OT" },
  });
  cornerstone.utilities.genericMetadataProvider.add(imageId, {
    type: "generalImageModule",
    metadata: { instanceNumber: 1 },
  });

  const values = scalar as unknown as ArrayLike<number>;
  let minPixelValue = values[0];
  let maxPixelValue = values[0];
  for (let index = 1; index < values.length; index += 1) {
    if (values[index] < minPixelValue) minPixelValue = values[index];
    if (values[index] > maxPixelValue) maxPixelValue = values[index];
  }

  const voxelManager = cornerstone.utilities.VoxelManager.createImageVoxelManager({
    width: cols,
    height: rows,
    numberOfComponents: 1,
    scalarData: scalar as never,
    id: imageId,
  });

  const image = {
    imageId,
    rows,
    columns: cols,
    width: cols,
    height: rows,
    intercept: 0,
    slope: 1,
    windowCenter: [windowCenter],
    windowWidth: [windowWidth],
    invert: meta.photometric === "MONOCHROME1",
    voiLUTFunction:
      meta.voi_lut_function === "LINEAR_EXACT"
        ? cornerstone.Enums.VOILUTFunctionType.LINEAR_EXACT
        : meta.voi_lut_function === "SIGMOID"
          ? cornerstone.Enums.VOILUTFunctionType.SAMPLED_SIGMOID
          : cornerstone.Enums.VOILUTFunctionType.LINEAR,
    color: false,
    numberOfComponents: 1,
    dataType: scalar.constructor.name,
    minPixelValue,
    maxPixelValue,
    columnPixelSpacing: meta.column_pixel_spacing,
    rowPixelSpacing: meta.row_pixel_spacing,
    FrameOfReferenceUID: imageId,
    getPixelData: () => scalar,
    voxelManager,
    sizeInBytes: scalar.byteLength,
    referencedImageId: imageId,
  };

  return image as unknown as Record<string, unknown>;
}

function loadMiapImage(imageId: string): Promise<Record<string, unknown>> {
  const cached = cornerstone.cache.getImage(imageId);
  if (cached) return Promise.resolve(cached as unknown as Record<string, unknown>);
  const pending = inFlight.get(imageId);
  if (pending) return pending;
  const load = fetchMiapImage(imageId).finally(() => inFlight.delete(imageId));
  inFlight.set(imageId, load);
  return load;
}

export function initCornerstone(): Promise<void> {
  if (!ready) {
    ready = (async () => {
      cornerstone.init();
      cornerstoneTools.init();
      cornerstone.imageLoader.registerImageLoader(SCHEME, (imageId) => ({
        promise: loadMiapImage(imageId) as Promise<never>,
      }));

      for (const tool of [
        cornerstoneTools.WindowLevelTool,
        cornerstoneTools.PanTool,
        cornerstoneTools.ZoomTool,
        cornerstoneTools.LengthTool,
        cornerstoneTools.StackScrollTool,
      ]) {
        cornerstoneTools.addTool(tool);
      }

      synchronizer = cornerstoneTools.synchronizers.createZoomPanSynchronizer("miap-zoom-pan");
    })();
  }
  return ready;
}

export function toolGroup(): cornerstoneTools.Types.IToolGroup | undefined {
  return (
    cornerstoneTools.ToolGroupManager.getToolGroup(TOOL_GROUP_ID) ??
    cornerstoneTools.ToolGroupManager.createToolGroup(TOOL_GROUP_ID)
  );
}

export function attachViewport(viewportId: string, engineId: string): void {
  const group = toolGroup();
  if (!group) return;
  for (const name of Object.values(TOOL_NAMES)) {
    if (!group.hasTool(name)) group.addTool(name);
  }
  if (!group.hasTool(cornerstoneTools.StackScrollTool.toolName)) {
    group.addTool(cornerstoneTools.StackScrollTool.toolName);
    group.setToolActive(cornerstoneTools.StackScrollTool.toolName, {
      bindings: [{ mouseButton: cornerstoneTools.Enums.MouseBindings.Wheel }],
    });
  }
  group.addViewport(viewportId, engineId);
  synchronizer?.add({ renderingEngineId: engineId, viewportId });
  activateTool("WindowLevel", group);
}

export function detachViewport(viewportId: string, engineId: string): void {
  const group = toolGroup();
  group?.removeViewports(engineId, viewportId);
  synchronizer?.remove({ renderingEngineId: engineId, viewportId });
}

export function activateTool(tool: ViewerTool, group = toolGroup()): void {
  if (!group) return;
  for (const [name, toolName] of Object.entries(TOOL_NAMES)) {
    if (name === tool) {
      group.setToolActive(toolName, { bindings: [{ mouseButton: cornerstoneTools.Enums.MouseBindings.Primary }] });
    } else {
      group.setToolPassive(toolName);
    }
  }
}

export function resetSynchronizer(): void {
  synchronizer?.setEnabled(true);
}
