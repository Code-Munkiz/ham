/**
 * HAM Desktop only: `preload.cjs` exposes `window.__HAM_DESKTOP_BUNDLE__` (Hermes CLI probe, curated files).
 */
export type HermesCliProbeResult =
  | { ok: true; versionLine: string }
  | { ok: false; error: string; code?: string };

export type ReadCuratedFileResult =
  | { ok: true; name: string; text: string }
  | { ok: false; error: string };

export type HamDesktopBundleApi = {
  hermesCliProbe: () => Promise<HermesCliProbeResult>;
  readCuratedFile: (name: string) => Promise<ReadCuratedFileResult>;
  openHermesUpstreamDocs: () => Promise<{ ok: boolean }>;
};

declare global {
  interface Window {
    __HAM_DESKTOP_BUNDLE__?: HamDesktopBundleApi;
  }
}

export function getDesktopBundleApi(): HamDesktopBundleApi | null {
  if (typeof window === "undefined") return null;
  const b = window.__HAM_DESKTOP_BUNDLE__;
  if (!b || typeof b.hermesCliProbe !== "function") return null;
  return b;
}
