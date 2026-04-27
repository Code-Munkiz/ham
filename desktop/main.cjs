'use strict';

const { app, BrowserWindow, ipcMain, Menu, shell } = require('electron');
const { execFile } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');

const { buildLocalControlStatus } = require('./local_control_status.cjs');
const {
  loadPolicy,
  getPolicyStatusPayload,
  engageKillSwitch,
  armBrowserOnlyControl,
  armRealBrowserControl,
  disengageKillSwitchForBrowserMvp,
} = require('./local_control_policy.cjs');
const { getAuditStatus, appendAuditEvent } = require('./local_control_audit.cjs');
const { buildSidecarStatus } = require('./local_control_sidecar_status.cjs');
const { createSidecarManager, defaultChildScriptPath } = require('./local_control_sidecar_manager.cjs');
const { createBrowserMvpController, browserActionGates } = require('./local_control_browser_mvp.cjs');
const { createRealBrowserCdpController, realBrowserActionGates } = require('./local_control_browser_real_cdp.cjs');

const CONFIG_FILENAME = 'ham-desktop-config.json';

/** Updated before each window load; preload reads via sendSync. */
let rendererConfigPayload = {};

/**
 * Merge order (later wins): persisted userData file < process env.
 * apiBase: non-empty string forces absolute API origin in the renderer.
 * useHashRouter: required for file:// SPA loads (BrowserRouter breaks on file).
 */
function readPersistedConfig() {
  try {
    const p = path.join(app.getPath('userData'), CONFIG_FILENAME);
    if (!fs.existsSync(p)) return {};
    const raw = fs.readFileSync(p, 'utf8');
    const j = JSON.parse(raw);
    return j && typeof j === 'object' ? j : {};
  } catch {
    return {};
  }
}

/** Shipped next to main.cjs in the asar — default API for download-and-run (overridable). */
function readPackagedPublicApiDefault() {
  if (!app.isPackaged) return '';
  try {
    const p = path.join(__dirname, 'default-public-api.json');
    if (!fs.existsSync(p)) return '';
    const j = JSON.parse(fs.readFileSync(p, 'utf8'));
    return typeof j.apiBase === 'string' ? j.apiBase.trim() : '';
  } catch {
    return '';
  }
}

function defaultLoadMode() {
  const fromEnv = (process.env.HAM_DESKTOP_LOAD_MODE || '').trim().toLowerCase();
  if (fromEnv) return fromEnv;
  return app.isPackaged ? 'file' : 'devserver';
}

function buildRendererConfig() {
  const persisted = readPersistedConfig();
  const envApi = (process.env.HAM_DESKTOP_API_BASE || '').trim();
  const envHash =
    process.env.HAM_DESKTOP_USE_HASH_ROUTER === '1' ||
    process.env.HAM_DESKTOP_USE_HASH_ROUTER === 'true';

  const packagedDefault = readPackagedPublicApiDefault();
  let apiBase =
    envApi ||
    (typeof persisted.apiBase === 'string' ? persisted.apiBase.trim() : '') ||
    packagedDefault;
  let useHashRouter =
    envHash ||
    persisted.useHashRouter === true ||
    persisted.useHashRouter === 'true';

  const loadMode = defaultLoadMode();
  if (loadMode === 'file') {
    useHashRouter = true;
  }

  const out = {};
  if (apiBase) out.apiBase = apiBase;
  if (useHashRouter) out.useHashRouter = true;
  out.loadMode = loadMode;
  return out;
}

function resolveWebRoot() {
  const fromEnv = (process.env.HAM_DESKTOP_WEB_ROOT || '').trim();
  if (fromEnv) return path.resolve(fromEnv);
  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'renderer');
  }
  return path.resolve(__dirname, '..', 'frontend', 'dist');
}

/** Bundled docs + default skill pins (shipped in app asar). */
function resolveCuratedDir() {
  return path.join(__dirname, 'curated');
}

const CURATED_FILE_ALLOWLIST = new Set([
  'README.md',
  'default-curated-skills.json',
  'ham-api-env.snippet',
]);

/** Preset id -> argv (after binary). No free-form user argv (security). */
const HERMES_PRESET_ARGV = {
  version: ['--version'],
  plugins_list: ['plugins', 'list'],
  mcp_list: ['mcp', 'list'],
};

const HERMES_PRESET_TIMEOUT_MS = 25_000;
const HERMES_PRESET_MAX_CHARS = 32_000;

function resolveHermesBinary() {
  const p = (process.env.HAM_HERMES_CLI_PATH || '').trim();
  if (p) return p;
  return 'hermes';
}

/**
 * @returns {Promise<
 *   | { ok: true, preset: string, argv: string[], stdout: string, stderr: string, exitCode: number, truncated: boolean }
 *   | { ok: false, error: string, code?: string, preset?: string }
 * >}
 */
function runHermesPreset(preset) {
  const key = String(preset || '').trim();
  if (!Object.prototype.hasOwnProperty.call(HERMES_PRESET_ARGV, key)) {
    return Promise.resolve({ ok: false, error: 'unknown preset', preset: key });
  }
  const extra = HERMES_PRESET_ARGV[key];
  const bin = resolveHermesBinary();
  const argv = Array.isArray(extra) ? extra : [];
  return new Promise((resolve) => {
    execFile(
      bin,
      argv,
      {
        timeout: HERMES_PRESET_TIMEOUT_MS,
        maxBuffer: 512 * 1024,
        env: process.env,
        windowsHide: true,
      },
      (err, stdout, stderr) => {
        if (err) {
          const e = err;
          if (e.killed && e.signal === 'SIGTERM') {
            resolve({ ok: false, error: 'timeout', preset: key, code: 'ETIMEDOUT' });
            return;
          }
          if (e.code === 'ETIMEDOUT' || e.code === 'ESRCH') {
            resolve({ ok: false, error: err.message || 'timeout', preset: key, code: String(e.code) });
            return;
          }
          if (e.code === 'ENOENT') {
            resolve({
              ok: false,
              error: 'Hermes binary not found (PATH or HAM_HERMES_CLI_PATH).',
              preset: key,
              code: 'ENOENT',
            });
            return;
          }
          if (e.code === 'ENOBUFS') {
            resolve({ ok: false, error: 'output too large', preset: key, code: 'ENOBUFS' });
            return;
          }
        }
        let out = String(stdout || '');
        let serr = String(stderr || '');
        let truncated = false;
        if (out.length + serr.length > HERMES_PRESET_MAX_CHARS * 2) {
          truncated = true;
          if (out.length > HERMES_PRESET_MAX_CHARS) {
            out = out.slice(0, HERMES_PRESET_MAX_CHARS) + '\n… [stdout truncated]';
          }
          if (serr.length > HERMES_PRESET_MAX_CHARS) {
            serr = serr.slice(0, HERMES_PRESET_MAX_CHARS) + '\n… [stderr truncated]';
          }
        }
        let exitCode = 0;
        if (err) {
          if (typeof err.code === 'number' && !Number.isNaN(err.code)) {
            exitCode = err.code;
          } else {
            exitCode = 1;
          }
        }
        resolve({
          ok: true,
          preset: key,
          argv: [bin, ...argv],
          stdout: out,
          stderr: serr,
          exitCode,
          truncated,
        });
      }
    );
  });
}

/**
 * @returns {Promise<{ ok: true, versionLine: string } | { ok: false, error: string, code?: string }>}
 */
function probeHermesCli() {
  return new Promise((resolve) => {
    execFile(
      'hermes',
      ['--version'],
      { timeout: 12_000, env: process.env, windowsHide: true },
      (err, stdout) => {
        if (err) {
          const code = err && typeof err === 'object' && 'code' in err ? String(/** @type {NodeJS.ErrnoException} */ (err).code) : '';
          resolve({
            ok: false,
            error: err.message || String(err),
            code: code || undefined,
          });
          return;
        }
        const line = String(stdout || '')
          .trim()
          .split(/\r?\n/)[0]
          .trim();
        resolve({ ok: true, versionLine: line || 'hermes' });
      }
    );
  });
}

function createWindow() {
  rendererConfigPayload = buildRendererConfig();

  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    backgroundColor: '#000000',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  const loadMode = rendererConfigPayload.loadMode || 'devserver';

  if (loadMode === 'file') {
    const root = resolveWebRoot();
    const indexHtml = path.join(root, 'index.html');
    void win.loadFile(indexHtml);
  } else {
    const url = (process.env.HAM_DESKTOP_DEV_SERVER_URL || 'http://127.0.0.1:3000').trim();
    void win.loadURL(url);
  }
}

ipcMain.on('ham-desktop:get-config-sync', (event) => {
  event.returnValue = rendererConfigPayload;
});

ipcMain.handle('ham-desktop:hermes-cli-probe', () => probeHermesCli());

ipcMain.handle('ham-desktop:hermes-preset', (event, preset) => runHermesPreset(preset));

ipcMain.handle('ham-desktop:read-curated-file', (event, name) => {
  const base = String(name || '').replace(/[/\\]/g, '');
  if (!CURATED_FILE_ALLOWLIST.has(base)) {
    return { ok: false, error: 'file not allowed' };
  }
  const p = path.join(resolveCuratedDir(), base);
  if (!p.startsWith(resolveCuratedDir())) {
    return { ok: false, error: 'path rejected' };
  }
  try {
    const text = fs.readFileSync(p, 'utf8');
    return { ok: true, name: base, text };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
});

ipcMain.handle('ham-desktop:open-hermes-upstream-docs', () => {
  const u = (process.env.HAM_HERMES_UPSTREAM_URL || 'https://github.com/NousResearch/hermes-agent').trim();
  return shell.openExternal(u || 'https://github.com/NousResearch/hermes-agent').then(() => ({ ok: true }));
});

function localControlPaths() {
  return {
    userDataPath: app.getPath('userData'),
    platform: process.platform,
    fs,
    path,
  };
}

/** Avoid wedging the renderer when CDP is slow or stuck (status refresh must stay snappy). */
function withTimeoutMs(promise, ms) {
  return Promise.race([
    promise,
    new Promise((_, reject) => {
      const t = setTimeout(() => reject(new Error('local_control_ipc_timeout')), ms);
      t.unref?.();
    }),
  ]);
}

const REAL_BROWSER_STATUS_IPC_MS = 5000;

/** @type {ReturnType<typeof createSidecarManager> | null} */
let sidecarManagerSingleton = null;

function getSidecarManager() {
  if (!sidecarManagerSingleton) {
    sidecarManagerSingleton = createSidecarManager({
      childScriptPath: defaultChildScriptPath(),
      onAuditEvent: (type) => {
        const c = localControlPaths();
        appendAuditEvent({
          userDataPath: c.userDataPath,
          type,
          fs: c.fs,
          path: c.path,
        });
      },
    });
  }
  return sidecarManagerSingleton;
}

/** @type {ReturnType<typeof createBrowserMvpController> | null} */
let browserMvpSingleton = null;

function getBrowserMvp() {
  if (!browserMvpSingleton) {
    browserMvpSingleton = createBrowserMvpController({ BrowserWindow });
  }
  return browserMvpSingleton;
}

/** @type {ReturnType<typeof createRealBrowserCdpController> | null} */
let realBrowserSingleton = null;

function getRealBrowser() {
  if (!realBrowserSingleton) {
    const c = localControlPaths();
    realBrowserSingleton = createRealBrowserCdpController({
      userDataPath: c.userDataPath,
      path: c.path,
      fs: c.fs,
    });
  }
  return realBrowserSingleton;
}

/** Local Control Phase 2 — full status; appends redacted audit line. */
ipcMain.handle('ham-desktop:local-control-get-status', async () => {
  const c = localControlPaths();
  const rb = getRealBrowser();
  let browserRealSnapshot = rb.getStatus();
  try {
    if (browserRealSnapshot.running) {
      browserRealSnapshot = await withTimeoutMs(rb.getStatusForIpc(), REAL_BROWSER_STATUS_IPC_MS);
    }
  } catch {
    browserRealSnapshot = rb.getStatus();
  }
  const st = buildLocalControlStatus({
    platform: c.platform,
    userDataPath: c.userDataPath,
    security: {
      context_isolation: true,
      node_integration: false,
      sandbox: true,
    },
    fs: c.fs,
    path: c.path,
    sidecarManager: getSidecarManager(),
    browserMvpGetStatus: () => getBrowserMvp().getStatus(),
    browserRealSnapshot,
  });
  appendAuditEvent({
    userDataPath: c.userDataPath,
    type: 'local_control_status_read',
    fs: c.fs,
    path: c.path,
  });
  return st;
});

ipcMain.handle('ham-desktop:local-control-get-policy-status', () => {
  const c = localControlPaths();
  const { policy, persisted } = loadPolicy({
    userDataPath: c.userDataPath,
    platform: c.platform,
    fs: c.fs,
    path: c.path,
  });
  appendAuditEvent({
    userDataPath: c.userDataPath,
    type: 'local_control_policy_read',
    fs: c.fs,
    path: c.path,
  });
  return getPolicyStatusPayload(policy, { persisted });
});

ipcMain.handle('ham-desktop:local-control-get-audit-status', () => {
  const c = localControlPaths();
  const st = getAuditStatus({
    userDataPath: c.userDataPath,
    fs: c.fs,
    path: c.path,
  });
  appendAuditEvent({
    userDataPath: c.userDataPath,
    type: 'local_control_audit_status_read',
    fs: c.fs,
    path: c.path,
  });
  return st;
});

ipcMain.handle('ham-desktop:local-control-get-kill-switch-status', () => {
  const c = localControlPaths();
  const { policy } = loadPolicy({
    userDataPath: c.userDataPath,
    platform: c.platform,
    fs: c.fs,
    path: c.path,
  });
  appendAuditEvent({
    userDataPath: c.userDataPath,
    type: 'local_control_kill_switch_status_read',
    fs: c.fs,
    path: c.path,
  });
  return {
    kind: 'ham_desktop_local_control_kill_switch_status',
    engaged: policy.kill_switch.engaged,
    reason: policy.kill_switch.reason,
  };
});

/** Phase 3B — live sidecar status (inert child optional); read-only payload. */
ipcMain.handle('ham-desktop:local-control-get-sidecar-status', () => {
  const c = localControlPaths();
  const { policy } = loadPolicy({
    userDataPath: c.userDataPath,
    platform: c.platform,
    fs: c.fs,
    path: c.path,
  });
  appendAuditEvent({
    userDataPath: c.userDataPath,
    type: 'local_control_sidecar_status_read',
    fs: c.fs,
    path: c.path,
  });
  return buildSidecarStatus({
    killSwitchEngaged: policy.kill_switch.engaged,
    manager: getSidecarManager(),
  });
});

ipcMain.handle('ham-desktop:local-control-sidecar-start', async () => {
  const c = localControlPaths();
  const { policy } = loadPolicy({
    userDataPath: c.userDataPath,
    platform: c.platform,
    fs: c.fs,
    path: c.path,
  });
  return getSidecarManager().start({ killSwitchEngaged: policy.kill_switch.engaged });
});

ipcMain.handle('ham-desktop:local-control-sidecar-stop', async () => {
  return getSidecarManager().stop();
});

ipcMain.handle('ham-desktop:local-control-sidecar-health', async () => {
  const c = localControlPaths();
  appendAuditEvent({
    userDataPath: c.userDataPath,
    type: 'local_control_sidecar_health_ping',
    fs: c.fs,
    path: c.path,
  });
  return getSidecarManager().pingHealth();
});

/** Engage only — idempotent; persists safer policy; never disengages. */
ipcMain.handle('ham-desktop:local-control-engage-kill-switch', () => {
  const c = localControlPaths();
  const r = engageKillSwitch({
    userDataPath: c.userDataPath,
    platform: c.platform,
    fs: c.fs,
    path: c.path,
  });
  appendAuditEvent({
    userDataPath: c.userDataPath,
    type: 'local_control_kill_switch_engaged',
    fs: c.fs,
    path: c.path,
  });
  return {
    ok: true,
    changed: r.changed,
    kill_switch: r.policy.kill_switch,
  };
});

/** Phase 4A — narrow browser MVP (Electron BrowserWindow in main). */
ipcMain.handle('ham-desktop:local-control-browser-arm', () => {
  const c = localControlPaths();
  armBrowserOnlyControl({
    userDataPath: c.userDataPath,
    platform: c.platform,
    fs: c.fs,
    path: c.path,
  });
  appendAuditEvent({
    userDataPath: c.userDataPath,
    type: 'local_control_browser_arm',
    fs: c.fs,
    path: c.path,
  });
  return { ok: true };
});

ipcMain.handle('ham-desktop:local-control-browser-release-kill-switch', (event, token) => {
  const c = localControlPaths();
  const r = disengageKillSwitchForBrowserMvp({
    userDataPath: c.userDataPath,
    platform: c.platform,
    fs: c.fs,
    path: c.path,
    token,
  });
  if (r.ok) {
    appendAuditEvent({
      userDataPath: c.userDataPath,
      type: 'local_control_kill_switch_disengaged_browser_mvp',
      fs: c.fs,
      path: c.path,
    });
  }
  return r;
});

ipcMain.handle('ham-desktop:local-control-get-browser-status', () => {
  const c = localControlPaths();
  const { policy } = loadPolicy({
    userDataPath: c.userDataPath,
    platform: c.platform,
    fs: c.fs,
    path: c.path,
  });
  const snap = getBrowserMvp().getStatus();
  const g = browserActionGates(policy, c.platform);
  return {
    kind: 'ham_desktop_local_control_browser_mvp_public',
    running: snap.running,
    title: snap.title,
    display_url: snap.display_url,
    armed: policy.browser_control_armed === true,
    allow_loopback: policy.browser_allow_loopback === true,
    gate_blocked_reason: g.ok ? null : g.reason,
    kill_switch_engaged: policy.kill_switch.engaged,
  };
});

ipcMain.handle('ham-desktop:local-control-browser-start-session', async () => {
  const c = localControlPaths();
  const { policy } = loadPolicy({
    userDataPath: c.userDataPath,
    platform: c.platform,
    fs: c.fs,
    path: c.path,
  });
  const g = browserActionGates(policy, c.platform);
  if (!g.ok) {
    appendAuditEvent({
      userDataPath: c.userDataPath,
      type: 'local_control_browser_start_blocked',
      fs: c.fs,
      path: c.path,
    });
    return { ok: false, blocked: true, reason: g.reason };
  }
  appendAuditEvent({
    userDataPath: c.userDataPath,
    type: 'local_control_browser_start',
    fs: c.fs,
    path: c.path,
  });
  try {
    return await getBrowserMvp().startSession();
  } catch {
    appendAuditEvent({
      userDataPath: c.userDataPath,
      type: 'local_control_browser_error',
      fs: c.fs,
      path: c.path,
    });
    return { ok: false, error: 'start_failed' };
  }
});

ipcMain.handle('ham-desktop:local-control-browser-navigate', async (event, url) => {
  const c = localControlPaths();
  const { policy } = loadPolicy({
    userDataPath: c.userDataPath,
    platform: c.platform,
    fs: c.fs,
    path: c.path,
  });
  const g = browserActionGates(policy, c.platform);
  if (!g.ok) {
    appendAuditEvent({
      userDataPath: c.userDataPath,
      type: 'local_control_browser_navigate_blocked',
      fs: c.fs,
      path: c.path,
    });
    return { ok: false, blocked: true, reason: g.reason };
  }
  appendAuditEvent({
    userDataPath: c.userDataPath,
    type: 'local_control_browser_navigate',
    fs: c.fs,
    path: c.path,
  });
  try {
    return await getBrowserMvp().navigate(String(url || ''), {
      allow_loopback: policy.browser_allow_loopback === true,
    });
  } catch {
    appendAuditEvent({
      userDataPath: c.userDataPath,
      type: 'local_control_browser_error',
      fs: c.fs,
      path: c.path,
    });
    return { ok: false, error: 'navigate_failed' };
  }
});

ipcMain.handle('ham-desktop:local-control-browser-screenshot', async () => {
  const c = localControlPaths();
  const { policy } = loadPolicy({
    userDataPath: c.userDataPath,
    platform: c.platform,
    fs: c.fs,
    path: c.path,
  });
  const g = browserActionGates(policy, c.platform);
  if (!g.ok) {
    return { ok: false, blocked: true, reason: g.reason };
  }
  appendAuditEvent({
    userDataPath: c.userDataPath,
    type: 'local_control_browser_screenshot',
    fs: c.fs,
    path: c.path,
  });
  try {
    return await getBrowserMvp().screenshot();
  } catch {
    appendAuditEvent({
      userDataPath: c.userDataPath,
      type: 'local_control_browser_error',
      fs: c.fs,
      path: c.path,
    });
    return { ok: false, error: 'screenshot_failed' };
  }
});

ipcMain.handle('ham-desktop:local-control-browser-stop-session', () => {
  const c = localControlPaths();
  const running = getBrowserMvp().getStatus().running;
  if (running) {
    appendAuditEvent({
      userDataPath: c.userDataPath,
      type: 'local_control_browser_stop',
      fs: c.fs,
      path: c.path,
    });
  }
  return getBrowserMvp().stopSession();
});

/** Phase 4B — managed Chromium + localhost CDP (Linux). */
ipcMain.handle('ham-desktop:local-control-browser-real-arm', () => {
  const c = localControlPaths();
  armRealBrowserControl({
    userDataPath: c.userDataPath,
    platform: c.platform,
    fs: c.fs,
    path: c.path,
  });
  appendAuditEvent({
    userDataPath: c.userDataPath,
    type: 'local_control_real_browser_arm',
    fs: c.fs,
    path: c.path,
  });
  return { ok: true };
});

ipcMain.handle('ham-desktop:local-control-get-browser-real-status', async () => {
  const c = localControlPaths();
  const { policy } = loadPolicy({
    userDataPath: c.userDataPath,
    platform: c.platform,
    fs: c.fs,
    path: c.path,
  });
  const rb = getRealBrowser();
  let snap = rb.getStatus();
  try {
    if (snap.running) snap = await withTimeoutMs(rb.getStatusForIpc(), REAL_BROWSER_STATUS_IPC_MS);
  } catch {
    snap = rb.getStatus();
  }
  const g = realBrowserActionGates(policy, c.platform);
  return {
    kind: 'ham_desktop_local_control_browser_real_public',
    running: snap.running,
    title: snap.title || '',
    display_url: snap.display_url || '',
    armed: policy.real_browser_control_armed === true,
    allow_loopback: policy.real_browser_allow_loopback === true,
    managed_profile: true,
    cdp_localhost_only: true,
    gate_blocked_reason: g.ok ? null : g.reason,
    kill_switch_engaged: policy.kill_switch.engaged,
  };
});

ipcMain.handle('ham-desktop:local-control-browser-real-start-session', async () => {
  const c = localControlPaths();
  const { policy } = loadPolicy({
    userDataPath: c.userDataPath,
    platform: c.platform,
    fs: c.fs,
    path: c.path,
  });
  const g = realBrowserActionGates(policy, c.platform);
  if (!g.ok) {
    appendAuditEvent({
      userDataPath: c.userDataPath,
      type: 'local_control_real_browser_start_blocked',
      fs: c.fs,
      path: c.path,
    });
    return { ok: false, blocked: true, reason: g.reason };
  }
  appendAuditEvent({
    userDataPath: c.userDataPath,
    type: 'local_control_real_browser_start',
    fs: c.fs,
    path: c.path,
  });
  try {
    return await getRealBrowser().startSession();
  } catch {
    appendAuditEvent({
      userDataPath: c.userDataPath,
      type: 'local_control_real_browser_error',
      fs: c.fs,
      path: c.path,
    });
    return { ok: false, error: 'start_failed' };
  }
});

ipcMain.handle('ham-desktop:local-control-browser-real-navigate', async (event, url) => {
  const c = localControlPaths();
  const { policy } = loadPolicy({
    userDataPath: c.userDataPath,
    platform: c.platform,
    fs: c.fs,
    path: c.path,
  });
  const g = realBrowserActionGates(policy, c.platform);
  if (!g.ok) {
    appendAuditEvent({
      userDataPath: c.userDataPath,
      type: 'local_control_real_browser_navigate_blocked',
      fs: c.fs,
      path: c.path,
    });
    return { ok: false, blocked: true, reason: g.reason };
  }
  appendAuditEvent({
    userDataPath: c.userDataPath,
    type: 'local_control_real_browser_navigate',
    fs: c.fs,
    path: c.path,
  });
  try {
    return await getRealBrowser().navigate(String(url || ''), {
      allow_loopback: policy.real_browser_allow_loopback === true,
    });
  } catch {
    appendAuditEvent({
      userDataPath: c.userDataPath,
      type: 'local_control_real_browser_error',
      fs: c.fs,
      path: c.path,
    });
    return { ok: false, error: 'navigate_failed' };
  }
});

ipcMain.handle('ham-desktop:local-control-browser-real-reload', async () => {
  const c = localControlPaths();
  const { policy } = loadPolicy({
    userDataPath: c.userDataPath,
    platform: c.platform,
    fs: c.fs,
    path: c.path,
  });
  const g = realBrowserActionGates(policy, c.platform);
  if (!g.ok) {
    appendAuditEvent({
      userDataPath: c.userDataPath,
      type: 'local_control_real_browser_reload_blocked',
      fs: c.fs,
      path: c.path,
    });
    return { ok: false, blocked: true, reason: g.reason };
  }
  appendAuditEvent({
    userDataPath: c.userDataPath,
    type: 'local_control_real_browser_reload',
    fs: c.fs,
    path: c.path,
  });
  try {
    return await getRealBrowser().reload();
  } catch {
    appendAuditEvent({
      userDataPath: c.userDataPath,
      type: 'local_control_real_browser_error',
      fs: c.fs,
      path: c.path,
    });
    return { ok: false, error: 'reload_failed' };
  }
});

ipcMain.handle('ham-desktop:local-control-browser-real-screenshot', async () => {
  const c = localControlPaths();
  const { policy } = loadPolicy({
    userDataPath: c.userDataPath,
    platform: c.platform,
    fs: c.fs,
    path: c.path,
  });
  const g = realBrowserActionGates(policy, c.platform);
  if (!g.ok) {
    return { ok: false, blocked: true, reason: g.reason };
  }
  appendAuditEvent({
    userDataPath: c.userDataPath,
    type: 'local_control_real_browser_screenshot',
    fs: c.fs,
    path: c.path,
  });
  try {
    return await getRealBrowser().screenshot();
  } catch {
    appendAuditEvent({
      userDataPath: c.userDataPath,
      type: 'local_control_real_browser_error',
      fs: c.fs,
      path: c.path,
    });
    return { ok: false, error: 'screenshot_failed' };
  }
});

ipcMain.handle('ham-desktop:local-control-browser-real-stop-session', () => {
  const c = localControlPaths();
  const running = getRealBrowser().getStatus().running;
  if (running) {
    appendAuditEvent({
      userDataPath: c.userDataPath,
      type: 'local_control_real_browser_stop',
      fs: c.fs,
      path: c.path,
    });
  }
  return getRealBrowser().stopSession();
});

app.on('before-quit', () => {
  if (sidecarManagerSingleton) void sidecarManagerSingleton.stop();
  if (browserMvpSingleton) browserMvpSingleton.stopSession();
  if (realBrowserSingleton) realBrowserSingleton.stopSession();
});

app.whenReady().then(() => {
  // Native File/Edit/View menu uses the OS theme (often light on Linux) — drop it for a darker shell.
  // macOS keeps the default menu so app/window semantics stay familiar.
  if (process.platform !== 'darwin') {
    Menu.setApplicationMenu(null);
  }

  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
