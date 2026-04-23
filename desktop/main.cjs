'use strict';

const { app, BrowserWindow, ipcMain } = require('electron');
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

function buildRendererConfig() {
  const persisted = readPersistedConfig();
  const envApi = (process.env.HAM_DESKTOP_API_BASE || '').trim();
  const envHash =
    process.env.HAM_DESKTOP_USE_HASH_ROUTER === '1' ||
    process.env.HAM_DESKTOP_USE_HASH_ROUTER === 'true';

  let apiBase = envApi || (typeof persisted.apiBase === 'string' ? persisted.apiBase.trim() : '');
  let useHashRouter =
    envHash ||
    persisted.useHashRouter === true ||
    persisted.useHashRouter === 'true';

  const loadMode = (process.env.HAM_DESKTOP_LOAD_MODE || 'devserver').trim().toLowerCase();
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
  return path.resolve(__dirname, '..', 'frontend', 'dist');
}

function createWindow() {
  rendererConfigPayload = buildRendererConfig();

  const win = new BrowserWindow({
    width: 1280,
    height: 800,
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

app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
