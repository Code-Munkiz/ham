'use strict';

/**
 * Desktop Local Control Phase 2 — redacted audit log (JSONL under userData).
 * Events contain only type + ISO timestamp — no paths, env, or secrets.
 */

const AUDIT_SUBDIR = 'audit';
const EVENTS_FILE = 'events.jsonl';

const SAFE_EVENT_TYPES = new Set([
  'local_control_status_read',
  'local_control_policy_read',
  'local_control_audit_status_read',
  'local_control_kill_switch_status_read',
  'local_control_kill_switch_engaged',
  'local_control_sidecar_start_blocked',
  'local_control_sidecar_status_read',
  'local_control_sidecar_health_ping',
  'local_control_sidecar_stop',
  'local_control_browser_arm',
  'local_control_browser_start',
  'local_control_browser_start_blocked',
  'local_control_browser_navigate',
  'local_control_browser_navigate_blocked',
  'local_control_browser_screenshot',
  'local_control_browser_stop',
  'local_control_browser_error',
  'local_control_kill_switch_disengaged_browser_mvp',
]);

/** @param {string} userDataPath @param {typeof import('node:path')} path */
function auditDirPath(userDataPath, path) {
  return path.join(userDataPath, 'ham-desktop', 'local-control', AUDIT_SUBDIR);
}

function eventsFilePath(userDataPath, path) {
  return path.join(auditDirPath(userDataPath, path), EVENTS_FILE);
}

/**
 * @param {object} opts
 * @param {string} opts.userDataPath
 * @param {typeof import('node:fs')} opts.fs
 * @param {typeof import('node:path')} opts.path
 */
function getAuditStatus(opts) {
  const { userDataPath, fs, path } = opts;
  const dir = auditDirPath(userDataPath, path);
  const file = eventsFilePath(userDataPath, path);
  let available = false;
  let writable = false;
  let event_count_estimate = null;

  try {
    fs.accessSync(userDataPath, fs.constants.W_OK);
    writable = true;
  } catch {
    writable = false;
  }

  try {
    if (fs.existsSync(dir)) {
      fs.accessSync(dir, fs.constants.W_OK);
      available = true;
    } else {
      available = writable;
    }
  } catch {
    available = false;
  }

  if (fs.existsSync(file)) {
    try {
      fs.accessSync(file, fs.constants.W_OK);
      const st = fs.statSync(file);
      if (st.size === 0) {
        event_count_estimate = 0;
      } else {
        const raw = fs.readFileSync(file, 'utf8');
        const lines = raw.trim().split(/\r?\n/).filter(Boolean);
        event_count_estimate = lines.length;
      }
    } catch {
      event_count_estimate = null;
    }
  } else if (available) {
    event_count_estimate = 0;
  }

  return {
    kind: 'ham_desktop_local_control_audit_status',
    available,
    writable: available && writable,
    event_count_estimate,
    redacted: true,
  };
}

/**
 * @param {object} opts
 * @param {string} opts.type
 */
function appendAuditEvent(opts) {
  const { userDataPath, type, fs, path } = opts;
  const t = String(type || '').trim();
  if (!SAFE_EVENT_TYPES.has(t)) {
    return { ok: false, error: 'event_type_not_allowed' };
  }
  const dir = auditDirPath(userDataPath, path);
  const file = eventsFilePath(userDataPath, path);
  try {
    fs.mkdirSync(dir, { recursive: true });
    const line = `${JSON.stringify({ type: t, ts_iso: new Date().toISOString() })}\n`;
    fs.appendFileSync(file, line, 'utf8');
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

module.exports = {
  SAFE_EVENT_TYPES,
  getAuditStatus,
  appendAuditEvent,
  auditDirPath,
  eventsFilePath,
};
