'use strict';

/**
 * Desktop Local Control Phase 1 — read-only status/doctor payload (main process).
 * No automation, paths are never returned to the renderer (booleans only under `paths`).
 */

const SCHEMA_VERSION = 1;
const PHASE = 'doctor_status_only';

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
 */
function buildLocalControlStatus(opts) {
  const { platform, userDataPath, security, fs, path } = opts;
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
    capabilities: {
      browser_automation: 'not_implemented',
      filesystem_access: 'not_implemented',
      shell_commands: 'not_implemented',
      app_window_control: 'not_implemented',
      mcp_adapters: 'not_implemented',
    },
    warnings,
    non_goals: [
      'no automation in phase 1',
      'no cloud-run browser control',
      'no war-room revival',
    ],
  };
}

module.exports = {
  buildLocalControlStatus,
  platformDerived,
  SCHEMA_VERSION,
  PHASE,
};
