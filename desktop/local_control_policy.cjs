'use strict';

/**
 * Desktop Local Control Phase 2 — persisted policy skeleton (main process only).
 * Phase 2 clamps: enabled always false, permissions false, empty allowlists in persisted shape.
 * Kill switch defaults engaged; false on disk is auto-remanded to engaged (safer).
 */

const POLICY_SCHEMA_VERSION = 1;
const POLICY_PHASE = 'policy_audit_kill_switch_only';
const POLICY_BASENAME = 'policy.json';

/** @param {string} userDataPath @param {typeof import('node:path')} path */
function policyFilePath(userDataPath, path) {
  return path.join(userDataPath, 'ham-desktop', 'local-control', POLICY_BASENAME);
}

/** @param {string} platform */
function defaultPolicy(platform) {
  const now = new Date().toISOString();
  return {
    schema_version: POLICY_SCHEMA_VERSION,
    enabled: false,
    phase: POLICY_PHASE,
    platform,
    allowlists: {
      browser_origins: [],
      filesystem_roots: [],
      shell_commands: [],
      mcp_servers: [],
    },
    permissions: {
      browser_automation: false,
      filesystem_access: false,
      shell_commands: false,
      app_window_control: false,
      mcp_adapters: false,
    },
    kill_switch: {
      engaged: true,
      reason: 'default_disabled',
    },
    updated_at: now,
  };
}

/**
 * Clamp in-memory policy for Phase 2 persistence (never widen permissions).
 * @param {Record<string, unknown>} raw
 * @param {string} platform
 */
function normalizePolicyForPhase2(raw, platform) {
  const base = defaultPolicy(platform);
  if (!raw || typeof raw !== 'object') return base;

  const ks = raw.kill_switch && typeof raw.kill_switch === 'object' ? raw.kill_switch : {};
  let engaged = ks.engaged !== false;
  let reason = typeof ks.reason === 'string' && ks.reason.trim() ? ks.reason.trim() : base.kill_switch.reason;
  if (!engaged) {
    engaged = true;
    reason = 'auto_remanded_phase2';
  }

  return {
    ...base,
    kill_switch: { engaged, reason },
    updated_at: typeof raw.updated_at === 'string' ? raw.updated_at : base.updated_at,
  };
}

/**
 * Redacted policy summary for IPC (no paths, no env).
 * @param {ReturnType<typeof normalizePolicyForPhase2>} policy
 * @param {{ persisted: boolean }} meta
 */
function getPolicyStatusPayload(policy, meta) {
  return {
    kind: 'ham_desktop_local_control_policy_status',
    schema_version: policy.schema_version,
    enabled: false,
    phase: policy.phase,
    persisted: meta.persisted,
    default_deny: true,
    allowlist_counts: {
      browser_origins: policy.allowlists.browser_origins.length,
      filesystem_roots: policy.allowlists.filesystem_roots.length,
      shell_commands: policy.allowlists.shell_commands.length,
      mcp_servers: policy.allowlists.mcp_servers.length,
    },
    permissions: { ...policy.permissions },
    kill_switch: { ...policy.kill_switch },
    updated_at: policy.updated_at,
  };
}

/**
 * Load policy from disk or return in-memory default (no write).
 * If file exists but kill_switch disengaged, normalize and persist safer state.
 * @param {object} opts
 * @param {string} opts.userDataPath
 * @param {string} opts.platform
 * @param {typeof import('node:fs')} opts.fs
 * @param {typeof import('node:path')} opts.path
 */
function loadPolicy(opts) {
  const { userDataPath, platform, fs, path } = opts;
  const p = policyFilePath(userDataPath, path);
  if (!fs.existsSync(p)) {
    return { policy: defaultPolicy(platform), persisted: false };
  }
  try {
    const raw = JSON.parse(fs.readFileSync(p, 'utf8'));
    const normalized = normalizePolicyForPhase2(raw, platform);
    const rawEngaged = raw.kill_switch && raw.kill_switch.engaged !== false;
    if (!rawEngaged) {
      try {
        fs.mkdirSync(path.dirname(p), { recursive: true });
        fs.writeFileSync(p, JSON.stringify(normalized, null, 2), 'utf8');
      } catch {
        /* read still valid */
      }
    }
    return { policy: normalized, persisted: true };
  } catch {
    return { policy: defaultPolicy(platform), persisted: false };
  }
}

/**
 * Persist policy (Phase 2 safe shape only).
 * @param {object} opts
 * @param {ReturnType<typeof normalizePolicyForPhase2>} opts.policy
 */
function savePolicy(opts) {
  const { userDataPath, policy, fs, path } = opts;
  const p = policyFilePath(userDataPath, path);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(policy, null, 2), 'utf8');
}

/**
 * Engage kill switch only (idempotent, always safer).
 * @returns {{ policy: ReturnType<typeof normalizePolicyForPhase2>, changed: boolean }}
 */
function engageKillSwitch(opts) {
  const { userDataPath, platform, fs, path } = opts;
  const { policy: cur } = loadPolicy({ userDataPath, platform, fs, path });
  const next = normalizePolicyForPhase2(cur, platform);
  const already =
    next.kill_switch.engaged === true && next.kill_switch.reason === 'operator_engaged';
  if (already && fs.existsSync(policyFilePath(userDataPath, path))) {
    return { policy: next, changed: false };
  }
  next.kill_switch = { engaged: true, reason: 'operator_engaged' };
  next.updated_at = new Date().toISOString();
  savePolicy({ userDataPath, policy: next, fs, path });
  return { policy: next, changed: !already };
}

module.exports = {
  POLICY_SCHEMA_VERSION,
  POLICY_PHASE,
  policyFilePath,
  defaultPolicy,
  normalizePolicyForPhase2,
  getPolicyStatusPayload,
  loadPolicy,
  savePolicy,
  engageKillSwitch,
};
