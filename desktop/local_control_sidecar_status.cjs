"use strict";

/**
 * Desktop Local Control Phase 3B — sidecar status shape for aggregate + IPC.
 * Lifecycle details live in local_control_sidecar_manager.cjs (main only).
 */

const KIND = "ham_desktop_local_control_sidecar_status";

/** @typedef {{ getSnapshot: () => { running: boolean, health_last: 'ok' | 'error' | null } }} SidecarManagerView */

function healthLabel(snapshot) {
  if (!snapshot.running) return "unavailable";
  if (snapshot.health_last === "ok") return "ok";
  if (snapshot.health_last === "error") return "error";
  return "unknown";
}

/**
 * @param {object} opts
 * @param {boolean} opts.killSwitchEngaged
 * @param {SidecarManagerView} opts.manager
 */
function buildSidecarStatus(opts) {
  const { killSwitchEngaged, manager } = opts;
  const snap = manager.getSnapshot();
  const start_allowed = !killSwitchEngaged;
  return {
    kind: KIND,
    expected: true,
    implemented: true,
    mode: "inert_process_shell",
    transport: "stdio_json_rpc",
    inbound_network: false,
    running: snap.running,
    start_allowed,
    blocked_reason: killSwitchEngaged ? "kill_switch_engaged" : null,
    health: healthLabel(snap),
    droid_access: "not_enabled",
    capabilities: {
      browser_automation: "not_implemented",
      filesystem_access: "not_implemented",
      shell_commands: "not_implemented",
      app_window_control: "not_implemented",
      mcp_adapters: "not_implemented",
    },
  };
}

/** @returns {SidecarManagerView} */
function createIdleSidecarManagerView() {
  return {
    getSnapshot: () => ({ running: false, health_last: null }),
  };
}

module.exports = {
  KIND,
  buildSidecarStatus,
  createIdleSidecarManagerView,
};
