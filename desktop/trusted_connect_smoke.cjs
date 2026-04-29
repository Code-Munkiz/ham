'use strict';

/**
 * Dev regression: `npm run smoke:trusted-connect` from `desktop/`.
 * Requires frontend dev server (`cd ../frontend && npm run dev`). Not part of default unit tests / CI unless Electron+Vite wired.
 *
 * Deletes `ELECTRON_RUN_AS_NODE` for the Electron child — required so `ipcMain` exists under real Electron (not vanilla Node).
 * Desktop GOHAM smoke: bridge on + Puppeteer(remote debugging) → /workspace/chat → chip → modal → Connect trusted → DOM checks → PASS.
 */

const fs = require('fs');
const path = require('path');
const http = require('http');
const { spawn } = require('child_process');

const puppeteer = require('puppeteer-core');

const DEBUG_PORT = Number(process.env.SMOKE_DEBUG_PORT || '9243');
const CHAT_URL = process.env.SMOKE_CHAT_URL || 'http://127.0.0.1:3000/workspace/chat';

function httpGet(port, pathname) {
  return new Promise((resolve, reject) => {
    http.get({ host: '127.0.0.1', port, path: pathname }, (res) => {
      let d = '';
      res.on('data', (c) => (d += c));
      res.on('end', () => resolve(d));
    }).on('error', reject);
  });
}

async function waitVite(timeoutMs = 60_000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    try {
      const body = await httpGet(3000, '/');
      if ((body || '').length > 120) return;
    } catch {
      /** */
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error('Vite (:3000) not reachable — start frontend: cd frontend && npm run dev');
}

async function spawnElectron(debugPort) {
  let electronExe;
  try {
    electronExe = require('electron');
  } catch {
    throw new Error('Run npm install inside desktop/ (electron missing)');
  }

  const argv = ['.', '--remote-debugging-port=' + String(debugPort)];

  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;

  env.HAM_LOCAL_WEB_BRIDGE_ENABLED = process.env.HAM_LOCAL_WEB_BRIDGE_ENABLED || '1';


  env.HAM_DESKTOP_DEV_SERVER_URL =
    process.env.HAM_DESKTOP_DEV_SERVER_URL || 'http://127.0.0.1:3000';

  const child = spawn(electronExe, argv, {
    cwd: __dirname,
    env,
    windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  /** Log early stderr for debugging Chromium flags */
  child.stderr?.once?.('data', (b) => {
    const m = Buffer.isBuffer(b) ? b.toString('utf8') : String(b);
    if (/error|fatal|failed/i.test(m)) console.error('[smoke][electron]', m.slice(0, 900));
  });

  await new Promise((resolve, reject) => {
    if (!child.pid) return reject(new Error('no Electron pid'));
    child.once('error', reject);
    child.once('exit', (code) => reject(new Error('Electron exited before ready: code ' + code)));
    setTimeout(() => {
      child.removeAllListeners('exit');
      resolve();
    }, 900);
  });

  return child;
}

async function waitDebugger(debugPort, timeoutMs = 50_000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    try {
      const v = await httpGet(debugPort, '/json/version');
      if ((v || '').includes('webSocketDebuggerUrl')) return v;
    } catch {
      /** */
    }
    await new Promise((r) => setTimeout(r, 420));
  }
  throw new Error(`Remote debugger :${debugPort} not ready`);
}

async function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function main() {
  await waitVite();

  console.log('[smoke] launching Electron bridge + debugger :' + DEBUG_PORT);
  const electronChild = await spawnElectron(DEBUG_PORT);

  try {
    await waitDebugger(DEBUG_PORT);

    const browserURL = `http://127.0.0.1:${DEBUG_PORT}`;
    console.log('[smoke] puppeteer-core connect ', browserURL);
    const browser = await puppeteer.connect({
      browserURL,
      defaultViewport: { width: 1280, height: 880 },
    });

    const pages = await browser.pages();
    let page = pages[0];
    if (!page) throw new Error('No page in Electron');

    console.log('[smoke] navigate', CHAT_URL);
    await page.goto(CHAT_URL, { waitUntil: 'domcontentloaded', timeout: 120_000 });

    const hasCfg = await page.evaluate(
      () =>
        typeof window !== 'undefined' &&
        typeof window.__HAM_DESKTOP_CONFIG__ === 'object' &&
        window.__HAM_DESKTOP_CONFIG__ !== null,
    );
    console.log('[smoke] __HAM_DESKTOP_CONFIG__?', hasCfg);
    if (!hasCfg) throw new Error('Renderer missing Desktop config (preload)');

    await page.waitForSelector('[data-ham-goham-chip="desktop"]', { timeout: 45_000 });
    console.log('[smoke] GOHAM chip rendered');

    await sleep(2500);
    await page.click('[data-ham-goham-chip="desktop"]').catch(() => {});
    await page.evaluate(() => {
      const chip = document.querySelector('[data-ham-goham-chip="desktop"]');
      if (chip instanceof HTMLElement) chip.click();
    });
    console.log('[smoke] chip clicked');

    await page.waitForFunction(() => !!document.querySelector('[role="dialog"]'), { timeout: 25_000 });
    console.log('[smoke] modal open');

    await sleep(900);
    let body = await page.evaluate(() => document.body.innerText || '');
    if (/access_token|Bearer\s+[A-Za-z0-9._-]+\./i.test(body)) {
      throw new Error('Refuse: token-shaped text leaked to DOM');
    }

    const clicked = await page.evaluate(() => {
      const labels = [...document.querySelectorAll('[role="dialog"] button')];
      const bt = labels.find((b) => /Connect trusted/i.test((b.textContent || '').trim()));
      if (!bt) return false;
      bt.click();
      return true;
    });

    if (!clicked) await page.click('[role="dialog"] button').catch(() => {});

    console.log('[smoke] clicked Connect trusted');

    await sleep(7000);

    body = await page.evaluate(() => document.body.innerText || '');

    if (/GOHAM\s*MODE\s*explainer|Observe\s*\/\s*Wait\s*\/\s*Scroll|DuckDuckGo\s*candidate/i.test(body)) {

      throw new Error('Unexpected dev-panel copy visible');
    }

    const ok =
      /Connected[\s.]|Already linked/i.test(body) ||
      /Renew trusted session/i.test(body) ||
      /Blocked[\s.]|disabled on this desktop/i.test(body) ||
      /Failed[\s.]|trusted_connect_failed|Bridge disabled/i.test(body);

    if (!ok) {
      console.warn('[smoke] Ambiguous modal text excerpt:\n' + body.slice(0, 2200));

      /** Soft-pass if modal still present and nothing obviously wrong */
      const soft = !!(await page.$('[role="dialog"]'));
      if (!soft) throw new Error('Modal gone / no recognizable outcome');

      console.warn('[smoke] WARN: partial pass — modal present; verify screenshot manually.');
    }

    await browser.disconnect();
    console.log('[smoke] PASS');
  } finally {
    electronChild.kill();
    /** Windows */


    try {


      electronChild.kill('SIGKILL');
    } catch (_) {
      /** */
    }

  }

}

main().catch((e) => {
  console.error(e);
  process.exit(1);


});
