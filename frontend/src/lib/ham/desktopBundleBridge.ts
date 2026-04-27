import type { HermesDesktopPresetId } from "./hermesDesktopPresets";

/**
 * HAM Desktop only: `preload.cjs` exposes `window.__HAM_DESKTOP_BUNDLE__` (Hermes CLI probe, curated files).
 * Local Control also uses `window.hamDesktop.localControl` (same narrow bridge object).
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

export type HamDesktopLocalControlPolicyStatus = {
  kind: "ham_desktop_local_control_policy_status";
  schema_version: number;
  enabled: boolean;
  phase: string;
  persisted: boolean;
  default_deny: boolean;
  allowlist_counts: Record<string, number>;
  permissions: Record<string, boolean>;
  kill_switch: { engaged: boolean; reason: string };
  updated_at: string;
};

export type HamDesktopLocalControlAuditStatus = {
  kind: "ham_desktop_local_control_audit_status";
  available: boolean;
  writable: boolean;
  event_count_estimate: number | null;
  redacted: boolean;
};

/** Payload from Electron main — doctor + Phase 2 skeleton; no filesystem paths. */
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
  policy: HamDesktopLocalControlPolicyStatus;
  audit: HamDesktopLocalControlAuditStatus;
  kill_switch: { engaged: boolean; reason: string };
  capabilities: Record<string, string>;
  warnings: string[];
  non_goals: string[];
};

export type HamDesktopLocalControlKillSwitchEngageResult = {
  ok: boolean;
  changed: boolean;
  kill_switch: { engaged: boolean; reason: string };
};

export type HamDesktopLocalControlApi = {
  getStatus: () => Promise<HamDesktopLocalControlStatus>;
  getPolicyStatus: () => Promise<HamDesktopLocalControlPolicyStatus>;
  getAuditStatus: () => Promise<HamDesktopLocalControlAuditStatus>;
  getKillSwitchStatus: () => Promise<{ kind: string; engaged: boolean; reason: string }>;
  engageKillSwitch: () => Promise<HamDesktopLocalControlKillSwitchEngageResult>;
};

export type HamDesktopBundleApi = {
  hermesCliProbe: () => Promise<HermesCliProbeResult>;
  runHermesPreset?: (id: HermesDesktopPresetId) => Promise<HermesPresetRunResult>;
  readCuratedFile: (name: string) => Promise<ReadCuratedFileResult>;
  openHermesUpstreamDocs: () => Promise<{ ok: boolean }>;
  localControl?: HamDesktopLocalControlApi;
};

declare global {
  interface Window {
    __HAM_DESKTOP_BUNDLE__?: HamDesktopBundleApi;
    hamDesktop?: { localControl: HamDesktopLocalControlApi };
  }
}

export function getDesktopBundleApi(): HamDesktopBundleApi | null {
  if (typeof window === "undefined") return null;
  const b = window.__HAM_DESKTOP_BUNDLE__;
  if (!b || typeof b.hermesCliProbe !== "function") return null;
  return b;
}

/** Prefer `hamDesktop.localControl`; fallback to bundle (same object in preload). */
export function getHamDesktopLocalControlApi(): HamDesktopLocalControlApi | null {
  if (typeof window === "undefined") return null;
  const h = window.hamDesktop?.localControl;
  if (h && typeof h.getStatus === "function") return h;
  const b = window.__HAM_DESKTOP_BUNDLE__?.localControl;
  if (b && typeof b.getStatus === "function") return b;
  return null;
}
