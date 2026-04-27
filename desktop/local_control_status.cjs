'use strict';

/**
 * Desktop Local Control — read-only status/doctor payload (main process).
 * Phase 2: policy / audit / kill-switch skeleton; paths are never returned (booleans only under `paths`).
 */

const { loadPolicy, getPolicyStatusPayload } = require('./local_control_policy.cjs');
const { getAuditStatus } = require('./local_control_audit.cjs');
const { buildSidecarStatus, createIdleSidecarManagerView } = require('./local_control_sidecar_status.cjs');

const SCHEMA_VERSION = 4;
const PHASE = 'policy_audit_kill_switch_only';

/** @param {string} platform process.platform */
function platformDerived(platform) {
  if (platform === 'linux') {
    return { supported_platform: true, platform_status: 'linux_first' };
  }
  if (platform === 'win32') {
    return { supported_platform: true, platform_status: 'windows_planned' };
  }
  return { supported_platform: false, platform_status: 'unsupported' };
}

/**
 * @param {object} opts
 * @param {string} opts.platform
 * @param {string} opts.userDataPath absolute path (main only; never echoed in IPC payload)
 * @param {{ context_isolation: boolean, node_integration: boolean, sandbox: boolean }} opts.security
 * @param {typeof import('node:fs')} opts.fs
 * @param {typeof import('node:path')} opts.path
 * @param {{ getSnapshot: () => { running: boolean, health_last: 'ok' | 'error' | null } }} [opts.sidecarManager]
 */
function buildLocalControlStatus(opts) {
  const { platform, userDataPath, security, fs, path, sidecarManager } = opts;
  const mgr = sidecarManager || createIdleSidecarManagerView();
  const warnings = [];

  let user_data_writable = false;
  try {
    fs.accessSync(userDataPath, fs.constants.W_OK);
    user_data_writable = true;
  } catch {
    warnings.push('user_data_not_writable');
  }

  const auditRoot = path.join(userDataPath, 'ham-desktop', 'local-control', 'audit');
  let audit_log_dir_writable = false;
  try {
    if (fs.existsSync(auditRoot)) {
      fs.accessSync(auditRoot, fs.constants.W_OK);
      audit_log_dir_writable = true;
    } else {
      audit_log_dir_writable = user_data_writable;
    }
  } catch {
    warnings.push('audit_dir_not_writable');
  }

  const derived = platformDerived(platform);
  if (!derived.supported_platform) {
    warnings.push('platform_out_of_scope');
  }

  const { policy, persisted } = loadPolicy({ userDataPath, platform, fs, path });
  const policy_status = getPolicyStatusPayload(policy, { persisted });
  const audit_status = getAuditStatus({ userDataPath, fs, path });

  return {
    kind: 'ham_desktop_local_control_status',
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
    capabilities: {
      browser_automation: 'not_implemented',
      filesystem_access: 'not_implemented',
      shell_commands: 'not_implemented',
      app_window_control: 'not_implemented',
      mcp_adapters: 'not_implemented',
    },
    warnings,
    non_goals: [
      'no automation in phase 3b',
      'sidecar is inert lifecycle shell only (no tools)',
      'no cloud-run browser control',
      'no war-room revival',
      'no disengage kill_switch via product ui',
    ],
  };
}

module.exports = {
  buildLocalControlStatus,
  platformDerived,
  SCHEMA_VERSION,
  PHASE,
};
