'use strict';

const { app, BrowserWindow, ipcMain, Menu, shell } = require('electron');
const { execFile } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');

const { buildLocalControlStatus } = require('./local_control_status.cjs');

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

/** Read-only Local Control Phase 1 doctor — no paths or env returned (booleans only). */
ipcMain.handle('ham-desktop:local-control-get-status', () => {
  const userData = app.getPath('userData');
  return buildLocalControlStatus({
    platform: process.platform,
    userDataPath: userData,
    security: {
      context_isolation: true,
      node_integration: false,
      sandbox: true,
    },
    fs,
    path,
  });
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
