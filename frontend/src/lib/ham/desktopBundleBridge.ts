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
  browser_control_armed?: boolean;
  browser_allow_loopback?: boolean;
  real_browser_control_armed?: boolean;
  real_browser_allow_loopback?: boolean;
  real_browser_allow_default_profile?: boolean;
  updated_at: string;
};

/** Must match `BROWSER_MVP_KILL_SWITCH_RELEASE_TOKEN` in desktop/local_control_policy.cjs */
export const HAM_DESKTOP_BROWSER_MVP_KILL_SWITCH_RELEASE = "BROWSER_MVP_KILL_SWITCH_RELEASE";

export type HamDesktopBrowserMvpStatus = {
  kind: "ham_desktop_local_control_browser_mvp_status";
  supported: boolean;
  armed: boolean;
  allow_loopback: boolean;
  session_running: boolean;
  title: string;
  display_url: string;
  gate_blocked_reason: string | null;
};

export type HamDesktopBrowserMvpPublic = {
  kind: "ham_desktop_local_control_browser_mvp_public";
  running: boolean;
  title: string;
  display_url: string;
  armed: boolean;
  allow_loopback: boolean;
  gate_blocked_reason: string | null;
  kill_switch_engaged: boolean;
};

export type HamDesktopBrowserRealStatus = {
  kind: "ham_desktop_local_control_browser_real_status";
  supported: boolean;
  armed: boolean;
  allow_loopback: boolean;
  managed_profile: boolean;
  cdp_localhost_only: boolean;
  uses_default_profile: boolean;
  session_running: boolean;
  title: string;
  display_url: string;
  gate_blocked_reason: string | null;
};

export type HamDesktopBrowserRealPublic = {
  kind: "ham_desktop_local_control_browser_real_public";
  running: boolean;
  title: string;
  display_url: string;
  armed: boolean;
  allow_loopback: boolean;
  managed_profile: boolean;
  cdp_localhost_only: boolean;
  gate_blocked_reason: string | null;
  kill_switch_engaged: boolean;
};

export type HamDesktopBrowserSessionResult =
  | { ok: true; idempotent?: boolean }
  | { ok: false; blocked: true; reason: string }
  | { ok: false; error: string };

export type HamDesktopBrowserScreenshotResult =
  | { ok: true; data_url: string }
  | { ok: false; blocked?: boolean; reason?: string; error?: string };

/** Real browser CDP helper — compact page observe snapshot (no full DOM dump). */
export type HamDesktopRealBrowserObserveCompactResult =
  | {
      ok: true;
      title: string;
      url: string;
      display_url: string;
      viewport?: {
        innerWidth: number;
        innerHeight: number;
        scrollX: number;
        scrollY: number;
      };
    }
  | { ok: false; blocked?: boolean; reason?: string; error?: string };

export type HamDesktopRealBrowserWaitResult =
  | { ok: true; waited_ms: number }
  | { ok: false; blocked?: boolean; reason?: string; error?: string };

export type HamDesktopRealBrowserScrollResult =
  | { ok: true; delta_applied: number; scroll_y?: number; inner_height?: number }
  | { ok: false; blocked?: boolean; reason?: string; error?: string };

export type HamDesktopRealBrowserClickCandidate = {
  id: string;
  tag: string;
  role: string | null;
  text: string;
  risk: string;
  box: { x: number; y: number; w: number; h: number };
};

export type HamDesktopRealBrowserEnumerateCandidatesResult =
  | { ok: true; candidates: HamDesktopRealBrowserClickCandidate[]; count: number }
  | { ok: false; blocked?: boolean; reason?: string; error?: string };

export type HamDesktopRealBrowserClickCandidateResult =
  | { ok: true }
  | { ok: false; blocked?: boolean; reason?: string; error?: string };

export type HamDesktopLocalControlAuditStatus = {
  kind: "ham_desktop_local_control_audit_status";
  available: boolean;
  writable: boolean;
  event_count_estimate: number | null;
  redacted: boolean;
};

export type HamDesktopLocalControlSidecarStatus = {
  kind: "ham_desktop_local_control_sidecar_status";
  expected: boolean;
  implemented: boolean;
  mode: string;
  transport: string;
  inbound_network: boolean;
  running: boolean;
  start_allowed: boolean;
  blocked_reason: string | null;
  health: string;
  droid_access: string;
  capabilities: Record<string, string>;
};

export type HamDesktopSidecarStartResult =
  | { ok: true }
  | { ok: false; blocked: true; reason: string }
  | { ok: false; error: string };

export type HamDesktopSidecarStopResult = { ok: true; idempotent?: boolean };

export type HamDesktopSidecarHealthResult =
  | { ok: true; result?: unknown }
  | { ok: false; reason: string };

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
  sidecar: HamDesktopLocalControlSidecarStatus;
  browser_mvp: HamDesktopBrowserMvpStatus;
  browser_real: HamDesktopBrowserRealStatus;
  capabilities: Record<string, string>;
  warnings: string[];
  non_goals: string[];
};

export type HamDesktopLocalControlKillSwitchEngageResult = {
  ok: boolean;
  changed: boolean;
  kill_switch: { engaged: boolean; reason: string };
};

/** Snapshot from main-process web bridge (`getStatus`). No access tokens returned. */
export type HamDesktopWebBridgeStatusSnapshot = {
  paired?: boolean;
  enabled?: boolean;
  /** Why bridge is disabled (e.g. explicit env override). */
  disabled_reason?: string;
  running?: boolean;
  pairing_required?: boolean;
  listener?: unknown;
  pairing?: Record<string, unknown>;
  /** Allow forward-compatible fields without claiming full schema. */
  [key: string]: unknown;
};

export type HamDesktopWebBridgeTrustedConnectResult =
  | { ok: true; status: string; already_connected?: boolean }
  | { ok: false; error: string };

export type HamDesktopWebBridgeRevokeResult =
  | { ok: true }
  | { ok: false; error?: string };

export type HamDesktopWebBridgeReadTrustedStatusResult =
  | ({ ok: true } & Record<string, unknown>)
  | { ok: false; error?: string };

export type HamDesktopWebBridgeBrowserIntentPayload = {
  intent_id?: string;
  action: "navigate_and_capture";
  url: string;
  client_context?: Record<string, unknown>;
};

export type HamDesktopWebBridgeBrowserIntentResult =
  | ({ ok: true } & Record<string, unknown>)
  | { ok: false; error?: string; reason_code?: string; http_status?: number };

export type HamDesktopWebBridgeApi = {
  getStatus: () => Promise<HamDesktopWebBridgeStatusSnapshot>;
  trustedConnect: () => Promise<HamDesktopWebBridgeTrustedConnectResult>;
  revoke: () => Promise<HamDesktopWebBridgeRevokeResult>;
  getPairingConfig: () => Promise<Record<string, unknown>>;
  setPairingConfig: (payload: { pairing_code_ttl_sec?: number }) => Promise<Record<string, unknown>>;
  readTrustedStatus: () => Promise<HamDesktopWebBridgeReadTrustedStatusResult>;
  browserIntent: (
    payload: HamDesktopWebBridgeBrowserIntentPayload,
  ) => Promise<HamDesktopWebBridgeBrowserIntentResult>;
};

export type HamDesktopLocalControlApi = {
  getStatus: () => Promise<HamDesktopLocalControlStatus>;
  getPolicyStatus: () => Promise<HamDesktopLocalControlPolicyStatus>;
  getAuditStatus: () => Promise<HamDesktopLocalControlAuditStatus>;
  getKillSwitchStatus: () => Promise<{ kind: string; engaged: boolean; reason: string }>;
  getSidecarStatus: () => Promise<HamDesktopLocalControlSidecarStatus>;
  pingSidecarHealth: () => Promise<HamDesktopSidecarHealthResult>;
  stopSidecar: () => Promise<HamDesktopSidecarStopResult>;
  startSidecar: () => Promise<HamDesktopSidecarStartResult>;
  engageKillSwitch: () => Promise<HamDesktopLocalControlKillSwitchEngageResult>;
  armBrowserOnlyControl: () => Promise<{ ok: boolean }>;
  releaseKillSwitchForBrowserMvp: (token: string) => Promise<{ ok: boolean; error?: string }>;
  getBrowserStatus: () => Promise<HamDesktopBrowserMvpPublic>;
  startBrowserSession: () => Promise<HamDesktopBrowserSessionResult>;
  navigateBrowser: (url: string) => Promise<HamDesktopBrowserSessionResult>;
  captureBrowserScreenshot: () => Promise<HamDesktopBrowserScreenshotResult>;
  stopBrowserSession: () => Promise<HamDesktopBrowserSessionResult>;
  armRealBrowserControl: () => Promise<{ ok: boolean }>;
  getRealBrowserStatus: () => Promise<HamDesktopBrowserRealPublic>;
  startRealBrowserSession: () => Promise<HamDesktopBrowserSessionResult>;
  navigateRealBrowser: (url: string) => Promise<HamDesktopBrowserSessionResult>;
  reloadRealBrowser: () => Promise<HamDesktopBrowserSessionResult>;
  captureRealBrowserScreenshot: () => Promise<HamDesktopBrowserScreenshotResult>;
  realBrowserObserveCompact: () => Promise<HamDesktopRealBrowserObserveCompactResult>;
  realBrowserWaitMs: (ms: number) => Promise<HamDesktopRealBrowserWaitResult>;
  realBrowserScrollVertical: (deltaY: number) => Promise<HamDesktopRealBrowserScrollResult>;
  realBrowserEnumerateClickCandidates: () => Promise<HamDesktopRealBrowserEnumerateCandidatesResult>;
  realBrowserClickCandidate: (candidateId: string) => Promise<HamDesktopRealBrowserClickCandidateResult>;
  stopRealBrowserSession: () => Promise<HamDesktopBrowserSessionResult>;
  /** Local web bridge — trusted connect + pairing config; no token fields in TS surface. */
  webBridge?: HamDesktopWebBridgeApi;
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

/** Desktop GOHAM local web bridge — `preload.cjs` nested under `localControl.webBridge`. */
export function getHamDesktopWebBridgeApi(): HamDesktopWebBridgeApi | null {
  const lc = getHamDesktopLocalControlApi();
  const w = lc?.webBridge;
  if (!w || typeof w.trustedConnect !== "function" || typeof w.getStatus !== "function") return null;
  return w;
}
