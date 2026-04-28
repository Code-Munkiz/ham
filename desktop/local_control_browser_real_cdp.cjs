'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { validateNavigateUrl, safeDisplayUrl } = require('./local_control_browser_url.cjs');

const MAX_SCREENSHOT_DATA_URL_CHARS = 1_500_000;
const CDP_READY_MS = 45_000;
const CDP_ATTACH_RETRY_MS = 25_000;
const NAV_WAIT_MS = 35_000;

/** GoHAM v1 Slice 1 — bounded interaction primitives (scroll / wait / enumerated click). */
const MAX_SCROLL_DELTA_PX = 600;
const MIN_WAIT_MS = 500;
const MAX_WAIT_MS = 3000;
const MAX_CLICK_CANDIDATES = 20;
const CANDIDATE_TEXT_SNIPPET = 64;
const CANDIDATE_TTL_MS = 45_000;

/**
 * @param {number} dy
 * @returns {number}
 */
function clampScrollDelta(dy) {
  const d = Math.round(Number(dy) || 0);
  if (!Number.isFinite(d)) return 0;
  if (d === 0) return 0;
  return Math.max(-MAX_SCROLL_DELTA_PX, Math.min(MAX_SCROLL_DELTA_PX, d));
}

/**
 * @param {unknown} ms
 * @returns {number | null}
 */
function clampWaitMs(ms) {
  const n = Math.round(Number(ms) || 0);
  if (!Number.isFinite(n)) return null;
  if (n < MIN_WAIT_MS || n > MAX_WAIT_MS) return null;
  return n;
}

/**
 * @param {string} id
 * @returns {boolean}
 */
function isValidCandidateId(id) {
  return /^ham_cand_\d+_\d+$/.test(String(id || '').trim());
}

/**
 * In-page script: tag candidates with data-ham-cand-id and return a compact JSON-serializable list.
 * No full HTML; text snippets capped server-side via SNIP in script.
 *
 * @param {number} epoch
 */
function buildCandidateEnumerationExpression(epoch) {
  const E = Math.floor(Number(epoch) || 0);
  const MAX = MAX_CLICK_CANDIDATES;
  const SNIP = CANDIDATE_TEXT_SNIPPET;
  return `(function(){
    var EPOCH = ${E};
    var MAX = ${MAX};
    var SNIP = ${SNIP};
    var BAD = /pay|checkout|sign\\s*in|log\\s*in|password|card\\s*number|subscribe\\s*now|buy\\s*now/i;
    document.querySelectorAll('[data-ham-cand-id]').forEach(function (el) {
      el.removeAttribute('data-ham-cand-id');
    });
    var out = [];
    var vw = window.innerWidth;
    var vh = window.innerHeight;
    var nodes = [];
    document.querySelectorAll('a[href]').forEach(function (n) { nodes.push(n); });
    document.querySelectorAll('button[type="button"]').forEach(function (n) { nodes.push(n); });
    document.querySelectorAll('input[type="button"]').forEach(function (n) { nodes.push(n); });
    document.querySelectorAll('[role="button"]').forEach(function (n) { nodes.push(n); });
    document.querySelectorAll('[role="link"]').forEach(function (n) { nodes.push(n); });
    var seen = new Set();
    var idx = 0;
    for (var i = 0; i < nodes.length && out.length < MAX; i++) {
      var el = nodes[i];
      if (seen.has(el)) continue;
      seen.add(el);
      var r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) continue;
      if (r.bottom < -2 || r.top > vh + 2 || r.right < -2 || r.left > vw + 2) continue;
      var href = el.getAttribute && el.getAttribute('href');
      if (href) {
        var h = String(href).trim().toLowerCase();
        if (h.indexOf('javascript:') === 0 || h.indexOf('mailto:') === 0 || h.indexOf('tel:') === 0) continue;
      }
      var txt = String((el.innerText || el.textContent || '')).trim().replace(/\\s+/g, ' ');
      if (BAD.test(txt)) continue;
      var al = String(el.getAttribute('aria-label') || '').trim();
      if (BAD.test(al)) continue;
      if (el.disabled === true) continue;
      if (String(el.getAttribute('aria-disabled') || '').toLowerCase() === 'true') continue;
      var tag = String(el.tagName || '').toLowerCase();
      var role = String(el.getAttribute('role') || '').toLowerCase() || null;
      var id = 'ham_cand_' + EPOCH + '_' + idx;
      idx += 1;
      el.setAttribute('data-ham-cand-id', id);
      var snippet = txt.length > SNIP ? txt.slice(0, SNIP) + '\\u2026' : txt;
      out.push({
        id: id,
        tag: tag,
        role: role,
        text: snippet,
        risk: 'low',
        box: { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) },
      });
    }
    return out;
  })()`;
}

/**
 * Dispatch a conservative click on a previously enumerated candidate (data-ham-cand-id).
 *
 * @param {string} id
 */
function buildClickCandidateExpression(id) {
  const idLit = JSON.stringify(String(id));
  return `(() => {
    const id = ${idLit};
    const el = document.querySelector('[data-ham-cand-id="' + id + '"]');
    if (!el) return { ok: false, err: 'gone' };
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return { ok: false, err: 'invisible' };
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    if (r.bottom < -2 || r.top > vh + 2 || r.right < -2 || r.left > vw + 2) return { ok: false, err: 'offscreen' };
    const tag = String(el.tagName || '').toLowerCase();
    const type = String(el.getAttribute('type') || '').toLowerCase();
    if (tag === 'input' && type === 'password') return { ok: false, err: 'blocked' };
    if (type === 'submit') return { ok: false, err: 'blocked' };
    const txt = String((el.innerText || el.textContent || '')).trim();
    const BAD = /pay|checkout|sign\\s*in|log\\s*in|password/i;
    if (BAD.test(txt)) return { ok: false, err: 'blocked' };
    el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
    return { ok: true };
  })()`;
}

/**
 * @param {object} policy normalized policy v3+
 * @param {string} platform process.platform
 */
function realBrowserActionGates(policy, platform) {
  if (platform !== 'linux' && platform !== 'win32') return { ok: false, reason: 'platform_not_supported' };
  if (policy.kill_switch.engaged) return { ok: false, reason: 'kill_switch_engaged' };
  if (!policy.real_browser_control_armed) return { ok: false, reason: 'real_browser_not_armed' };
  if (!policy.permissions.real_browser_automation) return { ok: false, reason: 'real_browser_automation_off' };
  if (!isRealBrowserRuntimeDiscoverable(platform)) return { ok: false, reason: 'chromium_not_found' };
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

function discoverChromiumExecutableWindows() {
  const env = String(process.env.HAM_DESKTOP_CHROME_PATH || process.env.CHROME_PATH || '').trim();
  if (env) return env;
  const programFiles = (process.env.PROGRAMFILES || '').trim();
  const programFilesX86 = (process.env['PROGRAMFILES(X86)'] || '').trim();
  const localAppData = (process.env.LOCALAPPDATA || '').trim();
  const roots = [programFiles, programFilesX86, localAppData].filter((p) => p.length > 0);
  const rels = [
    ['Google', 'Chrome', 'Application', 'chrome.exe'],
    ['Microsoft', 'Edge', 'Application', 'msedge.exe'],
    ['Chromium', 'Application', 'chrome.exe'],
  ];
  for (const root of roots) {
    for (const rel of rels) {
      const p = path.join(root, ...rel);
      try {
        fs.accessSync(p, fs.constants.X_OK);
        return p;
      } catch {
        /* continue */
      }
    }
  }
  return null;
}

/**
 * Discover browser executable by platform while preserving Linux path behavior.
 *
 * @param {(cmd: string, args: string[], opts?: object) => string} execFileSync
 * @param {string} platform
 */
function discoverChromiumExecutable(execFileSync, platform) {
  if (platform === 'linux') return discoverChromiumExecutableLinux(execFileSync);
  if (platform === 'win32') return discoverChromiumExecutableWindows();
  return null;
}

/**
 * @param {string} platform
 */
function isRealBrowserRuntimeDiscoverable(platform) {
  try {
    const execFileSync = require('node:child_process').execFileSync;
    return Boolean(discoverChromiumExecutable(execFileSync, platform));
  } catch {
    return false;
  }
}

function pickDebugPort() {
  return 9200 + Math.floor(Math.random() * 799);
}

/**
 * Force IPv4 loopback for CDP WebSocket URLs. Some Linux setups resolve `localhost`
 * or `[::1]` inconsistently between HTTP (fetch) and the `ws` client, which yields
 * flaky handshakes even when /json/list succeeds.
 *
 * @param {string} urlStr
 * @returns {string}
 */
function normalizeLoopbackWebSocketUrl(urlStr) {
  if (!urlStr || typeof urlStr !== 'string') return urlStr;
  try {
    const u = new URL(urlStr);
    const h = u.hostname.replace(/^\[|\]$/g, '').toLowerCase();
    if (h === 'localhost' || h === '::1') {
      u.hostname = '127.0.0.1';
    }
    return u.href;
  } catch {
    return urlStr;
  }
}

/**
 * @param {number} port
 * @param {typeof fetch} fetchImpl
 */
async function fetchDebuggerTargets(port, fetchImpl) {
  const listUrl = `http://127.0.0.1:${port}/json/list`;
  const legacyUrl = `http://127.0.0.1:${port}/json`;
  let r = await fetchImpl(listUrl);
  if (!r.ok) {
    r = await fetchImpl(legacyUrl);
  }
  if (!r.ok) throw new Error('json_list_failed');
  const list = await r.json();
  if (!Array.isArray(list)) throw new Error('json_list_invalid');
  return list;
}

/**
 * @param {unknown} err
 * @returns {{ ok: false, error: string, detail: string }}
 */
function mapAttachExceptionToResult(err) {
  const detail = err instanceof Error ? err.message : String(err);
  if (detail === 'no_page_target') {
    return { ok: false, error: 'cdp_no_page_target', detail };
  }
  if (detail === 'json_list_failed' || detail === 'json_list_invalid') {
    return { ok: false, error: 'cdp_target_list_failed', detail };
  }
  if (detail === 'managed_browser_exited_during_cdp_attach' || detail === 'cdp_debug_port_changed') {
    return { ok: false, error: 'browser_exited_during_attach', detail };
  }
  return { ok: false, error: 'cdp_attach_failed', detail };
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
  const list = await fetchDebuggerTargets(port, fetchImpl);
  const isDevtools = (u) => String(u || '').startsWith('devtools://');
  let page = list.find(
    (t) =>
      t &&
      t.type === 'page' &&
      typeof t.webSocketDebuggerUrl === 'string' &&
      !isDevtools(t.url),
  );
  if (!page) {
    page = list.find(
      (t) =>
        t &&
        typeof t.webSocketDebuggerUrl === 'string' &&
        String(t.webSocketDebuggerUrl).includes('/devtools/page/') &&
        !isDevtools(t.url) &&
        t.type !== 'browser',
    );
  }
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
      const ws = new WebSocket(this.wsUrl, {
        perMessageDeflate: false,
        handshakeTimeout: 15_000,
      });
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
  const profileRoot =
    userDataPath && pathMod
      ? pathMod.join(userDataPath, 'ham-desktop', 'local-control', 'real-browser-sessions')
      : '';

  /** @type {import('node:child_process').ChildProcess | null} */
  let child = null;
  let debugPort = /** @type {number | null} */ (null);
  let sessionProfileDir = '';
  /** @type {CdpSession | null} */
  let cdp = null;
  let candidateEpoch = 0;
  /** @type {Set<string>} */
  let lastCandidateIds = new Set();
  let lastCandidateAt = 0;

  function isChildAlive() {
    return !!(child && child.exitCode === null && !child.killed);
  }

  function cleanupSessionProfile(dir) {
    if (!dir) return;
    try {
      fsMod.rmSync(dir, { recursive: true, force: true });
    } catch {
      /* best effort */
    }
    if (sessionProfileDir === dir) sessionProfileDir = '';
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

  /**
   * Compact observe: title, URL, display URL, optional viewport (no DOM / storage).
   */
  async function observeCompact() {
    if (!isChildAlive() || !cdp) return { ok: false, error: 'not_running' };
    try {
      const expr =
        '(() => ({ title: document.title || "", href: location.href || "", viewport: { innerWidth: window.innerWidth, innerHeight: window.innerHeight, scrollX: window.scrollX, scrollY: window.scrollY } }))()';
      const r = await cdp.send('Runtime.evaluate', { expression: expr, returnByValue: true });
      const v = r && r.result && 'value' in r.result ? r.result.value : null;
      const title = v && typeof v.title === 'string' ? v.title : '';
      const href = v && typeof v.href === 'string' ? v.href : '';
      const vp = v && v.viewport && typeof v.viewport === 'object' ? v.viewport : null;
      return {
        ok: true,
        title,
        url: href,
        display_url: safeDisplayUrl(href),
        viewport: vp
          ? {
              innerWidth: Number(vp.innerWidth) || 0,
              innerHeight: Number(vp.innerHeight) || 0,
              scrollX: Number(vp.scrollX) || 0,
              scrollY: Number(vp.scrollY) || 0,
            }
          : undefined,
      };
    } catch {
      return { ok: false, error: 'observe_failed' };
    }
  }

  /**
   * Bounded vertical scroll via CDP mouse wheel at layout viewport center.
   *
   * @param {number} deltaY
   */
  async function scrollVerticalBounded(deltaY) {
    if (!isChildAlive() || !cdp) return { ok: false, error: 'not_running' };
    const dy = clampScrollDelta(deltaY);
    if (dy === 0) {
      return { ok: true, delta_applied: 0 };
    }
    try {
      const lm = await cdp.send('Page.getLayoutMetrics');
      const lv = lm && typeof lm === 'object' && lm.layoutViewport ? lm.layoutViewport : null;
      const cw = lv && typeof lv.clientWidth === 'number' ? lv.clientWidth : 800;
      const ch = lv && typeof lv.clientHeight === 'number' ? lv.clientHeight : 600;
      const cx = Math.max(1, Math.round(cw / 2));
      const cy = Math.max(1, Math.round(ch / 2));
      await cdp.send('Input.dispatchMouseEvent', {
        type: 'mouseWheel',
        x: cx,
        y: cy,
        deltaX: 0,
        deltaY: dy,
      });
      const scrollR = await cdp.send('Runtime.evaluate', {
        expression: '({ scrollY: window.scrollY, innerHeight: window.innerHeight })',
        returnByValue: true,
      });
      const sv = scrollR && scrollR.result && 'value' in scrollR.result ? scrollR.result.value : null;
      return {
        ok: true,
        delta_applied: dy,
        scroll_y: sv && typeof sv.scrollY === 'number' ? sv.scrollY : undefined,
        inner_height: sv && typeof sv.innerHeight === 'number' ? sv.innerHeight : undefined,
      };
    } catch {
      return { ok: false, error: 'scroll_failed' };
    }
  }

  /**
   * @param {unknown} ms
   */
  async function waitBoundedMs(ms) {
    if (!isChildAlive() || !cdp) return { ok: false, error: 'not_running' };
    const w = clampWaitMs(ms);
    if (w === null) return { ok: false, error: 'wait_out_of_range' };
    await new Promise((resolve) => setTimeout(resolve, w));
    return { ok: true, waited_ms: w };
  }

  async function enumerateClickCandidates() {
    if (!isChildAlive() || !cdp) return { ok: false, error: 'not_running' };
    candidateEpoch += 1;
    const epoch = candidateEpoch;
    try {
      const expr = buildCandidateEnumerationExpression(epoch);
      const r = await cdp.send('Runtime.evaluate', { expression: expr, returnByValue: true });
      const val = r && r.result && 'value' in r.result ? r.result.value : null;
      let list = [];
      if (Array.isArray(val)) {
        list = val.slice(0, MAX_CLICK_CANDIDATES).map((c) => ({
          id: String((c && c.id) || ''),
          tag: String((c && c.tag) || ''),
          role: c && c.role != null ? String(c.role) : null,
          text: String((c && c.text) || '').slice(0, CANDIDATE_TEXT_SNIPPET + 8),
          risk: String((c && c.risk) || 'low'),
          box:
            c && c.box && typeof c.box === 'object'
              ? {
                  x: Number(c.box.x) || 0,
                  y: Number(c.box.y) || 0,
                  w: Number(c.box.w) || 0,
                  h: Number(c.box.h) || 0,
                }
              : { x: 0, y: 0, w: 0, h: 0 },
        }));
      }
      lastCandidateIds = new Set(list.map((x) => x.id).filter((id) => isValidCandidateId(id)));
      lastCandidateAt = Date.now();
      return { ok: true, candidates: list, count: list.length };
    } catch {
      lastCandidateIds.clear();
      lastCandidateAt = 0;
      return { ok: false, error: 'candidates_failed' };
    }
  }

  /**
   * @param {string} candidateId
   */
  async function clickCandidate(candidateId) {
    if (!isChildAlive() || !cdp) return { ok: false, error: 'not_running' };
    const id = String(candidateId || '').trim();
    if (!isValidCandidateId(id)) return { ok: false, error: 'invalid_candidate_id' };
    if (Date.now() - lastCandidateAt > CANDIDATE_TTL_MS) return { ok: false, error: 'candidates_stale' };
    if (!lastCandidateIds.has(id)) return { ok: false, error: 'unknown_candidate_id' };
    try {
      const expr = buildClickCandidateExpression(id);
      const r = await cdp.send('Runtime.evaluate', { expression: expr, returnByValue: true });
      const val = r && r.result && 'value' in r.result ? r.result.value : null;
      if (!val || typeof val !== 'object') return { ok: false, error: 'click_eval_invalid' };
      if (val.ok === true) return { ok: true };
      const err = val.err != null ? String(val.err) : 'click_failed';
      if (err === 'blocked' || err === 'invisible' || err === 'offscreen' || err === 'gone') {
        return { ok: false, error: err === 'blocked' ? 'click_blocked' : err === 'gone' ? 'target_gone' : err };
      }
      return { ok: false, error: 'click_failed' };
    } catch {
      return { ok: false, error: 'click_failed' };
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
      } catch (e) {
        return mapAttachExceptionToResult(e);
      }
    }

    const exe = discoverChromiumExecutable(execFileSyncImpl, process.platform);
    if (!exe) return { ok: false, error: 'chromium_not_found' };

    if (!profileRoot) return { ok: false, error: 'profile_root_missing' };
    try {
      fsMod.mkdirSync(profileRoot, { recursive: true });
    } catch {
      return { ok: false, error: 'profile_mkdir_failed' };
    }
    let launchProfileDir = '';
    try {
      launchProfileDir = fsMod.mkdtempSync(pathMod.join(profileRoot, 'session-'));
      sessionProfileDir = launchProfileDir;
    } catch {
      return { ok: false, error: 'profile_mkdir_failed' };
    }

    const port = pickDebugPort();
    const args = [
      `--user-data-dir=${launchProfileDir}`,
      `--remote-debugging-port=${port}`,
      '--remote-debugging-address=127.0.0.1',
      // Recent Chromium rejects CDP WebSocket upgrades that include an Origin header unless
      // explicitly allowed; Node's `ws` client may send Origin → attach fails after /json/version is up.
      '--remote-allow-origins=*',
      '--no-first-run',
      '--no-default-browser-check',
      '--disable-extensions',
      '--disable-dev-shm-usage',
      '--disable-background-networking',
    ];
    // Linux: Chromium often exits immediately when spawned from Electron unless the
    // sandbox is disabled for this dedicated profile (same pattern as Puppeteer/CI).
    if (process.platform === 'linux') {
      args.push('--no-sandbox', '--disable-setuid-sandbox');
    }
    args.push('about:blank');

    try {
      child = spawnImpl(exe, args, {
        stdio: 'ignore',
        detached: false,
        env: { ...process.env },
      });
    } catch {
      cleanupSessionProfile(launchProfileDir);
      return { ok: false, error: 'spawn_failed' };
    }

    debugPort = port;
    const spawnedProc = child;
    const spawnedPort = port;
    const spawnedProfileDir = launchProfileDir;
    spawnedProc.on('exit', () => {
      // A *previous* Chrome child's exit can fire after we've already spawned a replacement;
      // without this guard we'd clear debugPort for the live session → :null CDP URLs.
      if (child !== spawnedProc) {
        return;
      }
      child = null;
      if (debugPort === spawnedPort) {
        debugPort = null;
      }
      lastCandidateIds.clear();
      lastCandidateAt = 0;
      candidateEpoch = 0;
      if (cdp) {
        cdp.close();
        cdp = null;
      }
      cleanupSessionProfile(spawnedProfileDir);
    });

    try {
      await waitForDevtoolsJsonVersion(port, fetchImpl, CDP_READY_MS);
    } catch {
      stopSession();
      return { ok: false, error: 'cdp_devtools_timeout' };
    }
    try {
      await attachCdp();
    } catch (e) {
      stopSession();
      return mapAttachExceptionToResult(e);
    }

    return { ok: true };
  }

  async function attachCdp() {
    const portForAttach = debugPort;
    if (!Number.isFinite(portForAttach)) {
      throw new Error('no_debug_port');
    }
    const deadline = Date.now() + CDP_ATTACH_RETRY_MS;
    /** @type {Error} */
    let lastErr = new Error('cdp_attach_exhausted_retries');
    while (Date.now() < deadline) {
      // If the managed Chrome process exits (or stopSession clears state) while we retry,
      // debugPort becomes null but this loop would keep running and call fetch with a null
      // port → "http://127.0.0.1:null/json/list". Abort instead.
      if (!isChildAlive()) {
        throw new Error('managed_browser_exited_during_cdp_attach');
      }
      if (debugPort !== portForAttach) {
        throw new Error('cdp_debug_port_changed');
      }
      /** @type {CdpSession | null} */
      let session = null;
      try {
        const wsUrlRaw = await fetchPageDebuggerWebSocketUrl(portForAttach, fetchImpl);
        const wsUrl = normalizeLoopbackWebSocketUrl(wsUrlRaw);
        session = new CdpSession(wsUrl);
        await session.connect();
        await session.send('Page.enable', {});
        await session.send('Runtime.enable', {});
        if (cdp) cdp.close();
        cdp = session;
        return;
      } catch (e) {
        if (session) session.close();
        lastErr = e instanceof Error ? e : new Error(String(e));
        await new Promise((r) => setTimeout(r, 100));
      }
    }
    throw lastErr;
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
    lastCandidateIds.clear();
    lastCandidateAt = 0;
    candidateEpoch = 0;
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
      const dir = sessionProfileDir;
      setTimeout(() => {
        try {
          if (c && c.exitCode === null && !c.killed) c.kill('SIGKILL');
        } catch {
          /* ignore */
        }
      }, 3500).unref?.();
      setTimeout(() => cleanupSessionProfile(dir), 4500).unref?.();
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
    observeCompact,
    scrollVerticalBounded,
    waitBoundedMs,
    enumerateClickCandidates,
    clickCandidate,
    discoverChromiumExecutableLinux: () => discoverChromiumExecutableLinux(execFileSyncImpl),
    discoverChromiumExecutableWindows,
    discoverChromiumExecutable: (platform = process.platform) =>
      discoverChromiumExecutable(execFileSyncImpl, platform),
    MAX_SCREENSHOT_DATA_URL_CHARS,
  };
}

module.exports = {
  createRealBrowserCdpController,
  realBrowserActionGates,
  isRealBrowserRuntimeDiscoverable,
  discoverPlaywrightChromiumLinux,
  discoverChromiumExecutableLinux,
  discoverChromiumExecutableWindows,
  discoverChromiumExecutable,
  reloadPageViaCdp,
  MAX_SCREENSHOT_DATA_URL_CHARS,
  pickDebugPort,
  waitForDevtoolsJsonVersion,
  fetchDebuggerTargets,
  normalizeLoopbackWebSocketUrl,
  fetchPageDebuggerWebSocketUrl,
  clampScrollDelta,
  clampWaitMs,
  isValidCandidateId,
  MAX_SCROLL_DELTA_PX,
  MIN_WAIT_MS,
  MAX_WAIT_MS,
  MAX_CLICK_CANDIDATES,
  CANDIDATE_TTL_MS,
  buildCandidateEnumerationExpression,
  buildClickCandidateExpression,
};
