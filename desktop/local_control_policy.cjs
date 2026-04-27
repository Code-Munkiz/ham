'use strict';

/**
 * Desktop Local Control — persisted policy (main process only).
 * Phase 4A: schema v2 — browser MVP arm + optional loopback; kill_switch persisted as-is (no remand on v2).
 * Phase 2 v1 files migrate to v2 once (kill_switch disengaged on v1 is remanded on migration only).
 */

const POLICY_SCHEMA_VERSION = 2;
const POLICY_PHASE = 'browser_mvp_4a';
const POLICY_BASENAME = 'policy.json';

const BROWSER_MVP_KILL_SWITCH_RELEASE_TOKEN = 'BROWSER_MVP_KILL_SWITCH_RELEASE';

/** @param {string} userDataPath @param {typeof import('node:path')} path */
function policyFilePath(userDataPath, path) {
  return path.join(userDataPath, 'ham-desktop', 'local-control', POLICY_BASENAME);
}

function emptyAllowlists() {
  return {
    browser_origins: [],
    filesystem_roots: [],
    shell_commands: [],
    mcp_servers: [],
  };
}

/** @param {string} platform */
function defaultPolicy(platform) {
  const now = new Date().toISOString();
  return {
    schema_version: POLICY_SCHEMA_VERSION,
    enabled: false,
    phase: POLICY_PHASE,
    platform,
    allowlists: emptyAllowlists(),
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
    browser_control_armed: false,
    browser_allow_loopback: false,
    updated_at: now,
  };
}

/** @param {unknown} al */
function mergeAllowlists(al, base) {
  const a = al && typeof al === 'object' ? al : {};
  return {
    browser_origins: Array.isArray(a.browser_origins) ? a.browser_origins : base.browser_origins,
    filesystem_roots: Array.isArray(a.filesystem_roots) ? a.filesystem_roots : base.filesystem_roots,
    shell_commands: Array.isArray(a.shell_commands) ? a.shell_commands : base.shell_commands,
    mcp_servers: Array.isArray(a.mcp_servers) ? a.mcp_servers : base.mcp_servers,
  };
}

/**
 * One-time migration from v1 disk shape: remand disengaged kill_switch (Phase 2 safety).
 * @param {Record<string, unknown>} raw
 * @param {string} platform
 */
function migrateV1RawToV2(raw, platform) {
  const base = defaultPolicy(platform);
  const ks = raw.kill_switch && typeof raw.kill_switch === 'object' ? raw.kill_switch : {};
  let engaged = ks.engaged !== false;
  let reason = typeof ks.reason === 'string' && ks.reason.trim() ? ks.reason.trim() : base.kill_switch.reason;
  if (!engaged) {
    engaged = true;
    reason = 'auto_remanded_phase2';
  }
  return {
    ...base,
    allowlists: mergeAllowlists(raw.allowlists, base.allowlists),
    kill_switch: { engaged, reason },
    updated_at: typeof raw.updated_at === 'string' ? raw.updated_at : base.updated_at,
  };
}

/**
 * @param {Record<string, unknown>} raw
 * @param {string} platform
 */
function normalizePolicyV2FromDisk(raw, platform) {
  const base = defaultPolicy(platform);
  if (!raw || typeof raw !== 'object') return base;

  const ks = raw.kill_switch && typeof raw.kill_switch === 'object' ? raw.kill_switch : {};
  const engaged = ks.engaged !== false;
  const reason = typeof ks.reason === 'string' && ks.reason.trim() ? ks.reason.trim() : base.kill_switch.reason;

  const browser_control_armed = raw.browser_control_armed === true;
  const browser_allow_loopback = raw.browser_allow_loopback === true;

  const permIn = raw.permissions && typeof raw.permissions === 'object' ? raw.permissions : {};

  const out = {
    ...base,
    schema_version: POLICY_SCHEMA_VERSION,
    phase: typeof raw.phase === 'string' && raw.phase.trim() ? raw.phase.trim() : POLICY_PHASE,
    allowlists: mergeAllowlists(raw.allowlists, base.allowlists),
    kill_switch: { engaged, reason },
    browser_control_armed,
    browser_allow_loopback,
    permissions: {
      browser_automation: browser_control_armed && permIn.browser_automation === true,
      filesystem_access: false,
      shell_commands: false,
      app_window_control: false,
      mcp_adapters: false,
    },
    updated_at: typeof raw.updated_at === 'string' ? raw.updated_at : base.updated_at,
  };

  enforcePermissionInvariants(out);
  return out;
}

function enforcePermissionInvariants(p) {
  p.permissions.filesystem_access = false;
  p.permissions.shell_commands = false;
  p.permissions.app_window_control = false;
  p.permissions.mcp_adapters = false;
  if (p.browser_control_armed && !p.permissions.browser_automation) {
    p.browser_control_armed = false;
  }
  if (!p.browser_control_armed) {
    p.permissions.browser_automation = false;
  }
}

/**
 * Legacy helper kept for tests: v1-style remand behavior via migration path.
 * @param {Record<string, unknown>} raw
 * @param {string} platform
 */
function normalizePolicyForPhase2(raw, platform) {
  return migrateV1RawToV2(raw, platform);
}

/**
 * @param {unknown} policy
 * @param {{ persisted: boolean }} meta
 */
function getPolicyStatusPayload(policy, meta) {
  const p = policy;
  return {
    kind: 'ham_desktop_local_control_policy_status',
    schema_version: p.schema_version,
    enabled: false,
    phase: p.phase,
    persisted: meta.persisted,
    default_deny: true,
    allowlist_counts: {
      browser_origins: p.allowlists.browser_origins.length,
      filesystem_roots: p.allowlists.filesystem_roots.length,
      shell_commands: p.allowlists.shell_commands.length,
      mcp_servers: p.allowlists.mcp_servers.length,
    },
    permissions: { ...p.permissions },
    kill_switch: { ...p.kill_switch },
    browser_control_armed: p.browser_control_armed === true,
    browser_allow_loopback: p.browser_allow_loopback === true,
    updated_at: p.updated_at,
  };
}

/**
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
    const ver = typeof raw.schema_version === 'number' ? raw.schema_version : 1;
    let policy;
    let migrated = false;
    if (ver < 2) {
      policy = migrateV1RawToV2(raw, platform);
      migrated = true;
    } else {
      policy = normalizePolicyV2FromDisk(raw, platform);
    }
    if (migrated) {
      try {
        fs.mkdirSync(path.dirname(p), { recursive: true });
        fs.writeFileSync(p, JSON.stringify(policy, null, 2), 'utf8');
      } catch {
        /* read still valid */
      }
    }
    return { policy, persisted: true };
  } catch {
    return { policy: defaultPolicy(platform), persisted: false };
  }
}

/**
 * @param {object} opts
 * @param {Record<string, unknown>} opts.policy
 */
function savePolicy(opts) {
  const { userDataPath, policy, fs, path } = opts;
  const p = policyFilePath(userDataPath, path);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(policy, null, 2), 'utf8');
}

/**
 * Engage kill switch; clears browser arm (safer).
 * @returns {{ policy: object, changed: boolean }}
 */
function engageKillSwitch(opts) {
  const { userDataPath, platform, fs, path } = opts;
  const { policy: cur } = loadPolicy({ userDataPath, platform, fs, path });
  const next = normalizePolicyV2FromDisk(cur, platform);
  const already =
    next.kill_switch.engaged === true &&
    next.kill_switch.reason === 'operator_engaged' &&
    next.browser_control_armed === false;
  if (already && fs.existsSync(policyFilePath(userDataPath, path))) {
    return { policy: next, changed: false };
  }
  next.kill_switch = { engaged: true, reason: 'operator_engaged' };
  next.browser_control_armed = false;
  next.permissions.browser_automation = false;
  next.updated_at = new Date().toISOString();
  enforcePermissionInvariants(next);
  savePolicy({ userDataPath, policy: next, fs, path });
  return { policy: next, changed: !already };
}

/**
 * Arm browser-only local control (narrow opt-in). Does not disengage kill switch.
 */
function armBrowserOnlyControl(opts) {
  const { userDataPath, platform, fs, path } = opts;
  const { policy: cur } = loadPolicy({ userDataPath, platform, fs, path });
  const next = normalizePolicyV2FromDisk(cur, platform);
  next.browser_control_armed = true;
  next.permissions.browser_automation = true;
  next.schema_version = POLICY_SCHEMA_VERSION;
  next.phase = POLICY_PHASE;
  next.updated_at = new Date().toISOString();
  enforcePermissionInvariants(next);
  savePolicy({ userDataPath, policy: next, fs, path });
  return { policy: next };
}

/**
 * Audited release of kill switch for browser MVP only (requires exact confirm token).
 */
function disengageKillSwitchForBrowserMvp(opts) {
  const { userDataPath, platform, fs, path, token } = opts;
  if (String(token || '') !== BROWSER_MVP_KILL_SWITCH_RELEASE_TOKEN) {
    return { ok: false, error: 'confirm_token_invalid' };
  }
  const { policy: cur } = loadPolicy({ userDataPath, platform, fs, path });
  const next = normalizePolicyV2FromDisk(cur, platform);
  next.kill_switch = { engaged: false, reason: 'browser_mvp_operator_ack' };
  next.updated_at = new Date().toISOString();
  enforcePermissionInvariants(next);
  savePolicy({ userDataPath, policy: next, fs, path });
  return { ok: true, policy: next };
}

module.exports = {
  POLICY_SCHEMA_VERSION,
  POLICY_PHASE,
  POLICY_BASENAME,
  BROWSER_MVP_KILL_SWITCH_RELEASE_TOKEN,
  policyFilePath,
  defaultPolicy,
  normalizePolicyForPhase2,
  normalizePolicyV2FromDisk,
  migrateV1RawToV2,
  getPolicyStatusPayload,
  loadPolicy,
  savePolicy,
  engageKillSwitch,
  armBrowserOnlyControl,
  disengageKillSwitchForBrowserMvp,
};
