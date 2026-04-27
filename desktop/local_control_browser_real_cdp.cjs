'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { validateNavigateUrl, safeDisplayUrl } = require('./local_control_browser_url.cjs');

const MAX_SCREENSHOT_DATA_URL_CHARS = 1_500_000;
const CDP_READY_MS = 45_000;
const NAV_WAIT_MS = 35_000;

/**
 * @param {object} policy normalized policy v3+
 * @param {string} platform process.platform
 */
function realBrowserActionGates(policy, platform) {
  if (platform !== 'linux') return { ok: false, reason: 'platform_not_supported' };
  if (policy.kill_switch.engaged) return { ok: false, reason: 'kill_switch_engaged' };
  if (!policy.real_browser_control_armed) return { ok: false, reason: 'real_browser_not_armed' };
  if (!policy.permissions.real_browser_automation) return { ok: false, reason: 'real_browser_automation_off' };
  return { ok: true };
}

/**
 * Newest Playwright-downloaded Chromium under ``~/.cache/ms-playwright`` (or ``PLAYWRIGHT_BROWSERS_PATH``).
 * No sudo required; pairs with ``scripts/ensure_chromium_for_desktop.sh`` / ``python -m playwright install chromium``.
 */
function discoverPlaywrightChromiumLinux() {
  const raw = (process.env.PLAYWRIGHT_BROWSERS_PATH || '').trim();
  const root = raw || path.join(os.homedir(), '.cache', 'ms-playwright');
  let names;
  try {
    names = fs.readdirSync(root, { withFileTypes: true });
  } catch {
    return null;
  }
  const dirs = names
    .filter((d) => d.isDirectory() && /^chromium-\d+$/u.test(d.name))
    .map((d) => d.name)
    .sort((a, b) => {
      const na = parseInt(a.replace(/^chromium-/u, ''), 10);
      const nb = parseInt(b.replace(/^chromium-/u, ''), 10);
      return (Number.isFinite(nb) ? nb : 0) - (Number.isFinite(na) ? na : 0);
    });
  for (const name of dirs) {
    const chrome = path.join(root, name, 'chrome-linux64', 'chrome');
    try {
      fs.accessSync(chrome, fs.constants.X_OK);
      return chrome;
    } catch {
      /* continue */
    }
  }
  return null;
}

/**
 * @param {(cmd: string, args: string[], opts?: object) => string} execFileSync
 */
function discoverChromiumExecutableLinux(execFileSync) {
  const env = String(process.env.HAM_DESKTOP_CHROME_PATH || process.env.CHROME_PATH || '').trim();
  if (env) return env;
  const candidates = [
    'google-chrome-stable',
    'google-chrome',
    'chromium-browser',
    'chromium',
    'microsoft-edge-stable',
    'brave-browser',
  ];
  for (const c of candidates) {
    try {
      const p = execFileSync('which', [c], { encoding: 'utf8', timeout: 4000 }).trim();
      if (p) return p;
    } catch {
      /* continue */
    }
  }
  // Distros / snaps often install here without every desktop PATH matching the Electron main process.
  const absoluteCandidates = [
    '/usr/bin/google-chrome-stable',
    '/usr/bin/google-chrome',
    '/opt/google/chrome/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/snap/bin/chromium',
    '/var/lib/snapd/snap/bin/chromium',
    '/usr/local/bin/google-chrome',
    '/usr/local/bin/chromium',
  ];
  for (const p of absoluteCandidates) {
    try {
      fs.accessSync(p, fs.constants.X_OK);
      return p;
    } catch {
      /* continue */
    }
  }
  const pw = discoverPlaywrightChromiumLinux();
  if (pw) return pw;
  return null;
}

function pickDebugPort() {
  return 9200 + Math.floor(Math.random() * 799);
}

/**
 * @param {typeof fetch} fetchImpl
 */
async function waitForDevtoolsJsonVersion(port, fetchImpl, deadlineMs) {
  const url = `http://127.0.0.1:${port}/json/version`;
  const deadline = Date.now() + deadlineMs;
  while (Date.now() < deadline) {
    try {
      const r = await fetchImpl(url);
      if (r.ok) return;
    } catch {
      /* retry */
    }
    await new Promise((r) => setTimeout(r, 80));
  }
  throw new Error('cdp_not_ready');
}

/**
 * @param {typeof fetch} fetchImpl
 */
/**
 * CDP Page.reload + wait for load (no user-controlled input).
 * Exported for unit tests with a stub cdp.
 *
 * @param {{ send: (m: string, p?: Record<string, unknown>) => Promise<unknown>, onceEvent: (m: string, fn: () => void) => void }} cdp
 * @param {number} navWaitMs
 */
async function reloadPageViaCdp(cdp, navWaitMs) {
  const loadDone = new Promise((resolve) => {
    const t = setTimeout(() => resolve(false), navWaitMs);
    cdp.onceEvent('Page.loadEventFired', () => {
      clearTimeout(t);
      resolve(true);
    });
  });
  try {
    await cdp.send('Page.reload', { ignoreCache: false });
  } catch {
    return { ok: false, error: 'reload_failed' };
  }
  await loadDone;
  return { ok: true };
}

async function fetchPageDebuggerWebSocketUrl(port, fetchImpl) {
  const r = await fetchImpl(`http://127.0.0.1:${port}/json/list`);
  if (!r.ok) throw new Error('json_list_failed');
  const list = await r.json();
  if (!Array.isArray(list)) throw new Error('json_list_invalid');
  const page = list.find(
    (t) =>
      t &&
      t.type === 'page' &&
      typeof t.webSocketDebuggerUrl === 'string' &&
      !String(t.url || '').startsWith('devtools://'),
  );
  if (!page) throw new Error('no_page_target');
  return page.webSocketDebuggerUrl;
}

class CdpSession {
  /**
   * @param {string} wsUrl
   */
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    /** @type {import('ws').WebSocket | null} */
    this.ws = null;
    this.nextId = 0;
    /** @type {Map<number, { resolve: (v: unknown) => void, reject: (e: Error) => void, t: NodeJS.Timeout }>} */
    this.pending = new Map();
    /** @type {Map<string, Array<(p: unknown) => void>>} */
    this.eventQueue = new Map();
  }

  async connect() {
    const WebSocket = require('ws');
    await new Promise((resolve, reject) => {
      const ws = new WebSocket(this.wsUrl);
      this.ws = ws;
      ws.on('open', () => resolve());
      ws.on('error', (e) => reject(e instanceof Error ? e : new Error(String(e))));
      ws.on('message', (data) => this._onMessage(data));
    });
  }

  /**
   * @param {Buffer | ArrayBuffer | Buffer[]} data
   */
  _onMessage(data) {
    let msg;
    try {
      msg = JSON.parse(data.toString());
    } catch {
      return;
    }
    if (msg.id != null && this.pending.has(msg.id)) {
      const slot = this.pending.get(msg.id);
      this.pending.delete(msg.id);
      clearTimeout(slot.t);
      if (msg.error) slot.reject(new Error(msg.error.message || 'cdp_error'));
      else slot.resolve(msg.result);
      return;
    }
    if (typeof msg.method === 'string') {
      const q = this.eventQueue.get(msg.method);
      if (q && q.length) {
        const fn = q.shift();
        fn(msg.params);
      }
    }
  }

  /**
   * @param {string} method
   * @param {(params: unknown) => void} fn
   */
  onceEvent(method, fn) {
    if (!this.eventQueue.has(method)) this.eventQueue.set(method, []);
    this.eventQueue.get(method).push(fn);
  }

  /**
   * @param {string} method
   * @param {Record<string, unknown>} [params]
   */
  send(method, params = {}) {
    const WebSocket = require('ws');
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      return Promise.reject(new Error('ws_closed'));
    }
    const id = ++this.nextId;
    return new Promise((resolve, reject) => {
      const t = setTimeout(() => {
        if (this.pending.has(id)) {
          this.pending.delete(id);
          reject(new Error('cdp_timeout'));
        }
      }, 45000);
      this.pending.set(id, {
        resolve: (v) => {
          clearTimeout(t);
          resolve(v);
        },
        reject: (e) => {
          clearTimeout(t);
          reject(e);
        },
        t,
      });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    try {
      this.ws?.close();
    } catch {
      /* ignore */
    }
    this.ws = null;
    for (const [, slot] of this.pending) clearTimeout(slot.t);
    this.pending.clear();
    this.eventQueue.clear();
  }
}

/**
 * @param {object} [opts]
 * @param {typeof fetch} [opts.fetchImpl]
 * @param {typeof import('node:child_process').spawn} [opts.spawnImpl]
 * @param {(cmd: string, args: string[], o?: object) => string} [opts.execFileSyncImpl]
 * @param {string} [opts.userDataPath]
 * @param {typeof import('node:path')} [opts.path]
 */
function createRealBrowserCdpController(opts = {}) {
  const fetchImpl = opts.fetchImpl || fetch;
  const spawnImpl = opts.spawnImpl || spawn;
  const execFileSyncImpl = opts.execFileSyncImpl || require('node:child_process').execFileSync;
  const pathMod = opts.path || require('node:path');
  const fsMod = opts.fs || require('node:fs');

  const userDataPath = opts.userDataPath || '';
  const profileDir =
    userDataPath && pathMod
      ? pathMod.join(userDataPath, 'ham-desktop', 'local-control', 'real-browser-profile')
      : '';

  /** @type {import('node:child_process').ChildProcess | null} */
  let child = null;
  let debugPort = /** @type {number | null} */ (null);
  /** @type {CdpSession | null} */
  let cdp = null;

  function isChildAlive() {
    return !!(child && child.exitCode === null && !child.killed);
  }

  function getStatus() {
    if (!isChildAlive()) {
      return { running: false, title: '', href: '', display_url: '' };
    }
    return { running: true, title: '', href: '', display_url: '' };
  }

  async function readPageMeta() {
    if (!cdp) return { title: '', href: '', display_url: '' };
    try {
      const hrefR = await cdp.send('Runtime.evaluate', { expression: 'location.href', returnByValue: true });
      const titleR = await cdp.send('Runtime.evaluate', { expression: 'document.title', returnByValue: true });
      const href = hrefR && hrefR.result && 'value' in hrefR.result ? String(hrefR.result.value || '') : '';
      const title = titleR && titleR.result && 'value' in titleR.result ? String(titleR.result.value || '') : '';
      return { title, href, display_url: safeDisplayUrl(href) };
    } catch {
      return { title: '', href: '', display_url: '' };
    }
  }

  async function startSession() {
    if (isChildAlive() && cdp) {
      return { ok: true };
    }
    if (isChildAlive() && !cdp) {
      try {
        await attachCdp();
        return { ok: true };
      } catch {
        return { ok: false, error: 'cdp_attach_failed' };
      }
    }

    const exe = discoverChromiumExecutableLinux(execFileSyncImpl);
    if (!exe) return { ok: false, error: 'chromium_not_found' };

    if (!profileDir) return { ok: false, error: 'profile_root_missing' };
    try {
      fsMod.mkdirSync(profileDir, { recursive: true });
    } catch {
      return { ok: false, error: 'profile_mkdir_failed' };
    }

    const port = pickDebugPort();
    const args = [
      `--user-data-dir=${profileDir}`,
      `--remote-debugging-port=${port}`,
      '--remote-debugging-address=127.0.0.1',
      '--no-first-run',
      '--no-default-browser-check',
      '--disable-extensions',
      '--disable-dev-shm-usage',
      '--disable-background-networking',
      'about:blank',
    ];

    try {
      child = spawnImpl(exe, args, {
        stdio: 'ignore',
        detached: false,
        env: { ...process.env },
      });
    } catch {
      return { ok: false, error: 'spawn_failed' };
    }

    debugPort = port;
    child.on('exit', () => {
      child = null;
      debugPort = null;
      if (cdp) {
        cdp.close();
        cdp = null;
      }
    });

    try {
      await waitForDevtoolsJsonVersion(port, fetchImpl, CDP_READY_MS);
      await attachCdp();
    } catch {
      stopSession();
      return { ok: false, error: 'cdp_startup_failed' };
    }

    return { ok: true };
  }

  async function attachCdp() {
    if (!debugPort) throw new Error('no_debug_port');
    const wsUrl = await fetchPageDebuggerWebSocketUrl(debugPort, fetchImpl);
    const session = new CdpSession(wsUrl);
    await session.connect();
    await session.send('Page.enable', {});
    await session.send('Runtime.enable', {});
    if (cdp) cdp.close();
    cdp = session;
  }

  /**
   * @param {string} urlString
   * @param {{ allow_loopback: boolean }} urlOpts
   */
  async function navigate(urlString, urlOpts) {
    const v = validateNavigateUrl(urlString, { allow_loopback: urlOpts.allow_loopback });
    if (!v.ok) return { ok: false, error: v.error };
    if (!isChildAlive() || !cdp) return { ok: false, error: 'not_running' };

    const loadDone = new Promise((resolve) => {
      const t = setTimeout(() => resolve(false), NAV_WAIT_MS);
      cdp.onceEvent('Page.loadEventFired', () => {
        clearTimeout(t);
        resolve(true);
      });
    });

    try {
      await cdp.send('Page.navigate', { url: v.href });
    } catch {
      return { ok: false, error: 'navigate_failed' };
    }
    await loadDone;
    return { ok: true };
  }

  async function reload() {
    if (!isChildAlive() || !cdp) return { ok: false, error: 'not_running' };
    return reloadPageViaCdp(cdp, NAV_WAIT_MS);
  }

  async function screenshot() {
    if (!isChildAlive() || !cdp) return { ok: false, error: 'not_running' };
    let result;
    try {
      result = await cdp.send('Page.captureScreenshot', { format: 'png' });
    } catch {
      return { ok: false, error: 'screenshot_failed' };
    }
    const b64 = result && typeof result.data === 'string' ? result.data : '';
    if (!b64) return { ok: false, error: 'screenshot_empty' };
    const dataUrl = `data:image/png;base64,${b64}`;
    if (dataUrl.length > MAX_SCREENSHOT_DATA_URL_CHARS) {
      return { ok: false, error: 'screenshot_too_large' };
    }
    return { ok: true, data_url: dataUrl };
  }

  function stopSession() {
    if (cdp) {
      cdp.close();
      cdp = null;
    }
    if (child && !child.killed && child.exitCode === null) {
      try {
        child.kill('SIGTERM');
      } catch {
        /* ignore */
      }
      const c = child;
      setTimeout(() => {
        try {
          if (c && c.exitCode === null && !c.killed) c.kill('SIGKILL');
        } catch {
          /* ignore */
        }
      }, 3500).unref?.();
    }
    child = null;
    debugPort = null;
    return { ok: true, idempotent: true };
  }

  async function getStatusForIpc() {
    const base = getStatus();
    if (!base.running || !cdp) return { ...base, title: '', display_url: '' };
    const meta = await readPageMeta();
    return { running: true, title: meta.title, href: meta.href, display_url: meta.display_url };
  }

  return {
    getStatus,
    getStatusForIpc,
    startSession,
    navigate,
    reload,
    screenshot,
    stopSession,
    discoverChromiumExecutableLinux: () => discoverChromiumExecutableLinux(execFileSyncImpl),
    MAX_SCREENSHOT_DATA_URL_CHARS,
  };
}

module.exports = {
  createRealBrowserCdpController,
  realBrowserActionGates,
  discoverPlaywrightChromiumLinux,
  discoverChromiumExecutableLinux,
  reloadPageViaCdp,
  MAX_SCREENSHOT_DATA_URL_CHARS,
  pickDebugPort,
  waitForDevtoolsJsonVersion,
  fetchPageDebuggerWebSocketUrl,
};
