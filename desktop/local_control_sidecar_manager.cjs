'use strict';

const { spawn } = require('node:child_process');
const path = require('node:path');

const HEALTH_TIMEOUT_MS = 5000;
const SHUTDOWN_WAIT_MS = 4000;

/**
 * @param {object} opts
 * @param {string} opts.childScriptPath absolute path to local_control_sidecar_child.cjs
 * @param {(type: string) => void} opts.onAuditEvent optional; main records redacted audit
 */
function createSidecarManager(opts) {
  const { childScriptPath, onAuditEvent } = opts;
  /** @type {import('node:child_process').ChildProcessWithoutNullStreams | null} */
  let proc = null;
  /** @type {boolean} */
  let running = false;
  /** @type {'ok' | 'error' | null} */
  let healthLast = null;
  let seq = 0;
  /** @type {Map<string, { resolve: (v: unknown) => void, reject: (e: Error) => void, timer: NodeJS.Timeout }>} */
  const pending = new Map();

  function record(type) {
    if (typeof onAuditEvent === 'function') onAuditEvent(type);
  }

  function getSnapshot() {
    return { running, health_last: healthLast };
  }

  function tearDownProc() {
    proc = null;
    running = false;
  }

  function rejectAllPending(reason) {
    for (const [id, p] of pending) {
      clearTimeout(p.timer);
      p.reject(new Error(reason));
      pending.delete(id);
    }
  }

  function handleLine(line) {
    if (!line) return;
    let msg;
    try {
      msg = JSON.parse(line);
    } catch {
      return;
    }
    const id = msg && typeof msg === 'object' && 'id' in msg ? String(msg.id) : null;
    if (id == null || !pending.has(id)) return;
    const p = pending.get(id);
    pending.delete(id);
    clearTimeout(p.timer);
    p.resolve(msg);
  }

  function attachStdout(stdout) {
    let buf = '';
    stdout.setEncoding('utf8');
    stdout.on('data', (chunk) => {
      buf += chunk;
      let idx;
      while ((idx = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, idx).trim();
        buf = buf.slice(idx + 1);
        handleLine(line);
      }
    });
  }

  /**
   * @param {string} method
   * @param {number} timeoutMs
   */
  function request(method, timeoutMs) {
    if (!proc || !proc.stdin || !running) {
      return Promise.reject(new Error('not_running'));
    }
    const id = `sc-${++seq}`;
    const payload = `${JSON.stringify({ method, id })}\n`;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(new Error('timeout'));
      }, timeoutMs);
      pending.set(id, { resolve, reject, timer });
      try {
        proc.stdin.write(payload);
      } catch (e) {
        clearTimeout(timer);
        pending.delete(id);
        reject(e instanceof Error ? e : new Error(String(e)));
      }
    });
  }

  /**
   * @param {{ killSwitchEngaged: boolean }} policyGate
   * @returns {Promise<{ ok: boolean, blocked?: boolean, reason?: string, error?: string }>}
   */
  async function start(policyGate) {
    if (policyGate.killSwitchEngaged) {
      record('local_control_sidecar_start_blocked');
      return { ok: false, blocked: true, reason: 'kill_switch_engaged' };
    }
    if (running && proc && !proc.killed) {
      return { ok: true };
    }

    const env = { ...process.env };
    if (process.versions.electron) {
      env.ELECTRON_RUN_AS_NODE = '1';
    }

    try {
      const childProc = spawn(process.execPath, [childScriptPath], {
        env,
        stdio: ['pipe', 'pipe', 'pipe'],
        windowsHide: true,
      });
      proc = childProc;
      running = true;
      healthLast = null;

      childProc.on('exit', () => {
        rejectAllPending('exited');
        tearDownProc();
        healthLast = null;
      });
      childProc.on('error', () => {
        rejectAllPending('spawn_error');
        tearDownProc();
        healthLast = 'error';
      });

      attachStdout(childProc.stdout);

      const healthResp = await request('health', HEALTH_TIMEOUT_MS);
      if (!healthResp || !healthResp.ok) {
        try {
          childProc.kill('SIGTERM');
        } catch {
          /* ignore */
        }
        tearDownProc();
        healthLast = 'error';
        return { ok: false, error: 'health_handshake_failed' };
      }
      healthLast = 'ok';
      return { ok: true };
    } catch {
      tearDownProc();
      healthLast = 'error';
      return { ok: false, error: 'spawn_failed' };
    }
  }

  /**
   * @returns {Promise<{ ok: boolean, idempotent?: boolean }>}
   */
  async function stop() {
    if (!proc || !running) {
      return { ok: true, idempotent: true };
    }
    record('local_control_sidecar_stop');
    const p = proc;
    await new Promise((resolve) => {
      const done = () => resolve(undefined);
      const t = setTimeout(() => {
        try {
          p.kill('SIGTERM');
        } catch {
          /* ignore */
        }
        done();
      }, SHUTDOWN_WAIT_MS);
      p.once('exit', () => {
        clearTimeout(t);
        done();
      });
      try {
        p.stdin.write(`${JSON.stringify({ method: 'shutdown', id: `sd-${++seq}` })}\n`);
      } catch {
        clearTimeout(t);
        try {
          p.kill('SIGTERM');
        } catch {
          /* ignore */
        }
        done();
      }
    });
    tearDownProc();
    healthLast = null;
    return { ok: true };
  }

  /**
   * @returns {Promise<{ ok: boolean, reason?: string, result?: unknown }>}
   */
  async function pingHealth() {
    if (!proc || !running) {
      return { ok: false, reason: 'not_running' };
    }
    try {
      const healthResp = await request('health', HEALTH_TIMEOUT_MS);
      if (healthResp && healthResp.ok) {
        healthLast = 'ok';
        return { ok: true, result: healthResp.result };
      }
      healthLast = 'error';
      return { ok: false, reason: 'health_failed' };
    } catch {
      healthLast = 'error';
      return { ok: false, reason: 'health_error' };
    }
  }

  return {
    getSnapshot,
    start,
    stop,
    pingHealth,
  };
}

function defaultChildScriptPath() {
  return path.join(__dirname, 'local_control_sidecar_child.cjs');
}

module.exports = {
  createSidecarManager,
  defaultChildScriptPath,
  HEALTH_TIMEOUT_MS,
};
