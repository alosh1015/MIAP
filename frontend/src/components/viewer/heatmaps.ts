import { api } from "../../api/client";
import { parseNpy } from "../../lib/npy";
import type { CamMapping, CamOverlay } from "./cam";

const cache = new Map<string, CamOverlay>();
const pending = new Map<string, Promise<CamOverlay>>();

function key(resultId: string, findingIndex: number): string {
  return `${resultId}:${findingIndex}`;
}

/** Parsed CAMs are cached per result and finding so view switches are free. */
export function cachedHeatmap(resultId: string, findingIndex: number): CamOverlay | null {
  return cache.get(key(resultId, findingIndex)) ?? null;
}

export function loadHeatmap(
  resultId: string,
  findingIndex: number,
  mapping: CamMapping = "centre",
): Promise<CamOverlay> {
  const cacheKey = key(resultId, findingIndex);
  const cached = cache.get(cacheKey);
  if (cached) return Promise.resolve(cached);
  const inflight = pending.get(cacheKey);
  if (inflight) return inflight;

  const request = api
    .getFindingHeatmap(resultId, findingIndex)
    .then((buffer) => {
      const parsed = parseNpy(buffer);
      if (parsed.shape.length !== 2) throw new Error("Heatmap is not two-dimensional");
      const overlay: CamOverlay = {
        data: parsed.data,
        width: parsed.shape[1],
        height: parsed.shape[0],
        mapping,
      };
      cache.set(cacheKey, overlay);
      return overlay;
    })
    .finally(() => pending.delete(cacheKey));

  pending.set(cacheKey, request);
  return request;
}

export function prefetchHeatmap(resultId: string, findingIndex: number, mapping: CamMapping = "centre"): void {
  if (cachedHeatmap(resultId, findingIndex)) return;
  loadHeatmap(resultId, findingIndex, mapping).catch(() => undefined);
}
