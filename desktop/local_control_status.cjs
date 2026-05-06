"use strict";

/**
 * Desktop Local Control — read-only status/doctor payload (main process).
 * Phase 2: policy / audit / kill-switch skeleton; paths are never returned (booleans only under `paths`).
 */

const { loadPolicy, getPolicyStatusPayload } = require("./local_control_policy.cjs");
const { getAuditStatus } = require("./local_control_audit.cjs");
const {
  buildSidecarStatus,
  createIdleSidecarManagerView,
} = require("./local_control_sidecar_status.cjs");
const { browserActionGates } = require("./local_control_browser_mvp.cjs");
const {
  realBrowserActionGates,
  isRealBrowserRuntimeDiscoverable,
} = require("./local_control_browser_real_cdp.cjs");

const SCHEMA_VERSION = 6;
const PHASE = "browser_real_4b";

/** @param {string} platform process.platform */
function platformDerived(platform) {
  if (platform === "linux") {
    return { supported_platform: true, platform_status: "linux_first" };
  }
  if (platform === "win32") {
    return { supported_platform: true, platform_status: "windows_planned" };
  }
  return { supported_platform: false, platform_status: "unsupported" };
}

/**
 * @param {object} opts
 * @param {string} opts.platform
 * @param {string} opts.userDataPath absolute path (main only; never echoed in IPC payload)
 * @param {{ context_isolation: boolean, node_integration: boolean, sandbox: boolean }} opts.security
 * @param {typeof import('node:fs')} opts.fs
 * @param {typeof import('node:path')} opts.path
 * @param {{ getSnapshot: () => { running: boolean, health_last: 'ok' | 'error' | null } }} [opts.sidecarManager]
 * @param {() => { running: boolean, title: string, display_url: string }} [opts.browserMvpGetStatus]
 * @param {{ running: boolean, title: string, display_url: string }} [opts.browserRealSnapshot]
 */
function buildLocalControlStatus(opts) {
  const {
    platform,
    userDataPath,
    security,
    fs,
    path,
    sidecarManager,
    browserMvpGetStatus,
    browserRealSnapshot,
  } = opts;
  const mgr = sidecarManager || createIdleSidecarManagerView();
  const browserSnap =
    typeof browserMvpGetStatus === "function"
      ? browserMvpGetStatus()
      : { running: false, title: "", display_url: "" };
  const realSnap = browserRealSnapshot || { running: false, title: "", display_url: "" };
  const warnings = [];

  let user_data_writable = false;
  try {
    fs.accessSync(userDataPath, fs.constants.W_OK);
    user_data_writable = true;
  } catch {
    warnings.push("user_data_not_writable");
  }

  const auditRoot = path.join(userDataPath, "ham-desktop", "local-control", "audit");
  let audit_log_dir_writable = false;
  try {
    if (fs.existsSync(auditRoot)) {
      fs.accessSync(auditRoot, fs.constants.W_OK);
      audit_log_dir_writable = true;
    } else {
      audit_log_dir_writable = user_data_writable;
    }
  } catch {
    warnings.push("audit_dir_not_writable");
  }

  const derived = platformDerived(platform);
  if (!derived.supported_platform) {
    warnings.push("platform_out_of_scope");
  }

  const { policy, persisted } = loadPolicy({ userDataPath, platform, fs, path });
  const policy_status = getPolicyStatusPayload(policy, { persisted });
  const audit_status = getAuditStatus({ userDataPath, fs, path });
  const bg = browserActionGates(policy, platform);
  const rg = realBrowserActionGates(policy, platform);

  return {
    kind: "ham_desktop_local_control_status",
    schema_version: SCHEMA_VERSION,
    available: true,
    enabled: false,
    phase: PHASE,
    platform,
    supported_platform: derived.supported_platform,
    platform_status: derived.platform_status,
    security: {
      context_isolation: security.context_isolation,
      node_integration: security.node_integration,
      sandbox: security.sandbox,
    },
    paths: {
      user_data_writable,
      audit_log_dir_writable,
    },
    policy: policy_status,
    audit: audit_status,
    kill_switch: {
      engaged: policy.kill_switch.engaged,
      reason: policy.kill_switch.reason,
    },
    sidecar: buildSidecarStatus({
      killSwitchEngaged: policy.kill_switch.engaged,
      manager: mgr,
    }),
    browser_mvp: {
      kind: "ham_desktop_local_control_browser_mvp_status",
      supported: platform === "linux",
      armed: policy.browser_control_armed === true,
      allow_loopback: policy.browser_allow_loopback === true,
      session_running: browserSnap.running,
      title: browserSnap.title || "",
      display_url: browserSnap.display_url || "",
      gate_blocked_reason: bg.ok ? null : bg.reason,
    },
    browser_real: {
      kind: "ham_desktop_local_control_browser_real_status",
      supported: platform === "linux" || platform === "win32",
      armed: policy.real_browser_control_armed === true,
      allow_loopback: policy.real_browser_allow_loopback === true,
      managed_profile: true,
      cdp_localhost_only: true,
      uses_default_profile: false,
      session_running: realSnap.running,
      title: realSnap.title || "",
      display_url: realSnap.display_url || "",
      gate_blocked_reason: rg.ok ? null : rg.reason,
    },
    capabilities: {
      browser_automation: platform === "linux" ? "available_guarded" : "not_implemented",
      real_browser_cdp:
        (platform === "linux" || platform === "win32") && isRealBrowserRuntimeDiscoverable(platform)
          ? "available_guarded"
          : "not_implemented",
      filesystem_access: "not_implemented",
      shell_commands: "not_implemented",
      app_window_control: "not_implemented",
      mcp_adapters: "not_implemented",
    },
    warnings,
    non_goals: [
      "Phase 4A: embedded Electron BrowserWindow MVP (proof); Phase 4B: managed Chromium + localhost CDP only",
      "no attach to operator default browser profile; no cookie/header extraction; no paths in renderer",
      "no Playwright sidecar; no /api/browser; no War Room",
      "no shell, filesystem, app, or MCP local control",
      "no cloud-run browser control plane",
    ],
  };
}

module.exports = {
  buildLocalControlStatus,
  platformDerived,
  SCHEMA_VERSION,
  PHASE,
};
