import type { HermesDesktopPresetId } from "./hermesDesktopPresets";

/**
 * HAM Desktop only: `preload.cjs` exposes `window.__HAM_DESKTOP_BUNDLE__` (Hermes CLI probe, curated files).
 */
export type HermesCliProbeResult =
  | { ok: true; versionLine: string }
  | { ok: false; error: string; code?: string };

export type HermesPresetRunResult =
  | {
      ok: true;
      preset: string;
      argv: string[];
      stdout: string;
      stderr: string;
      exitCode: number;
      truncated: boolean;
    }
  | { ok: false; error: string; code?: string; preset?: string };

export type ReadCuratedFileResult =
  | { ok: true; name: string; text: string }
  | { ok: false; error: string };

/** Payload from Electron main — read-only doctor; no filesystem paths (Phase 1). */
export type HamDesktopLocalControlStatus = {
  kind: "ham_desktop_local_control_status";
  schema_version: number;
  available: boolean;
  enabled: boolean;
  phase: string;
  platform: string;
  supported_platform: boolean;
  platform_status: "linux_first" | "windows_planned" | "unsupported";
  security: {
    context_isolation: boolean;
    node_integration: boolean;
    sandbox: boolean;
  };
  paths: {
    user_data_writable: boolean;
    audit_log_dir_writable: boolean;
  };
  capabilities: Record<string, string>;
  warnings: string[];
  non_goals: string[];
};

export type HamDesktopBundleApi = {
  hermesCliProbe: () => Promise<HermesCliProbeResult>;
  runHermesPreset?: (id: HermesDesktopPresetId) => Promise<HermesPresetRunResult>;
  readCuratedFile: (name: string) => Promise<ReadCuratedFileResult>;
  openHermesUpstreamDocs: () => Promise<{ ok: boolean }>;
  localControl?: {
    getStatus: () => Promise<HamDesktopLocalControlStatus>;
  };
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
