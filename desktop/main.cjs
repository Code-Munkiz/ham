'use strict';

const { app, BrowserWindow, ipcMain, Menu, shell } = require('electron');
const { execFile } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');

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
