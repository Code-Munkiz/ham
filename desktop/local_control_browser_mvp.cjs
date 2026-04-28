'use strict';

const { validateNavigateUrl, safeDisplayUrl } = require('./local_control_browser_url.cjs');

const MAX_SCREENSHOT_DATA_URL_CHARS = 1_500_000;

/**
 * @param {object} policy normalized policy v2+
 * @param {string} platform process.platform
 */
function browserActionGates(policy, platform) {
  if (platform !== 'linux') return { ok: false, reason: 'platform_not_supported' };
  if (policy.kill_switch.engaged) return { ok: false, reason: 'kill_switch_engaged' };
  if (!policy.browser_control_armed) return { ok: false, reason: 'browser_not_armed' };
  if (!policy.permissions.browser_automation) return { ok: false, reason: 'browser_automation_off' };
  return { ok: true };
}

/**
 * @param {{ BrowserWindow: typeof import('electron').BrowserWindow }} deps
 */
function createBrowserMvpController(deps) {
  const { BrowserWindow } = deps;
  /** @type {import('electron').BrowserWindow | null} */
  let win = null;

  function getStatus() {
    if (!win || win.isDestroyed()) {
      return { running: false, title: '', href: '', display_url: '' };
    }
    const wc = win.webContents;
    const href = wc.getURL();
    const title = wc.getTitle();
    return {
      running: true,
      title,
      href,
      display_url: safeDisplayUrl(href),
    };
  }

  async function startSession() {
    if (win && !win.isDestroyed()) {
      return { ok: true };
    }
    win = new BrowserWindow({
      width: 1024,
      height: 768,
      show: true,
      webPreferences: {
        sandbox: true,
        contextIsolation: true,
        nodeIntegration: false,
      },
    });
    win.on('closed', () => {
      win = null;
    });
    await win.loadURL('about:blank');
    return { ok: true };
  }

  /**
   * @param {string} urlString
   * @param {{ allow_loopback: boolean }} urlOpts
   */
  async function navigate(urlString, urlOpts) {
    const v = validateNavigateUrl(urlString, { allow_loopback: urlOpts.allow_loopback });
    if (!v.ok) return { ok: false, error: v.error };
    if (!win || win.isDestroyed()) return { ok: false, error: 'not_running' };
    await win.loadURL(v.href);
    return { ok: true };
  }

  async function screenshot() {
    if (!win || win.isDestroyed()) return { ok: false, error: 'not_running' };
    const img = await win.webContents.capturePage();
    const dataUrl = img.toDataURL();
    if (dataUrl.length > MAX_SCREENSHOT_DATA_URL_CHARS) {
      return { ok: false, error: 'screenshot_too_large' };
    }
    return { ok: true, data_url: dataUrl };
  }

  function stopSession() {
    if (!win || win.isDestroyed()) {
      return { ok: true, idempotent: true };
    }
    win.destroy();
    win = null;
    return { ok: true };
  }

  return {
    getStatus,
    startSession,
    navigate,
    screenshot,
    stopSession,
    MAX_SCREENSHOT_DATA_URL_CHARS,
  };
}

module.exports = {
  createBrowserMvpController,
  browserActionGates,
  MAX_SCREENSHOT_DATA_URL_CHARS,
};
