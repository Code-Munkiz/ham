'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');

const {
  realBrowserActionGates,
  createRealBrowserCdpController,
  discoverPlaywrightChromiumLinux,
  discoverChromiumExecutableWindows,
  discoverChromiumExecutable,
  reloadPageViaCdp,
  pickDebugPort,
  waitForDevtoolsJsonVersion,
  fetchPageDebuggerWebSocketUrl,
  normalizeLoopbackWebSocketUrl,
  clampScrollDelta,
  clampWaitMs,
  isValidCandidateId,
  buildCandidateEnumerationExpression,
  buildClickCandidateExpression,
} = require('./local_control_browser_real_cdp.cjs');

function baseRealPolicy(over) {
  return {
    kill_switch: { engaged: false, reason: 'x' },
    real_browser_control_armed: true,
    permissions: { real_browser_automation: true },
    real_browser_allow_loopback: false,
    ...over,
  };
}

test('realBrowserActionGates: windows denied when runtime missing', () => {
  const prevEnv = {
    HAM_DESKTOP_CHROME_PATH: process.env.HAM_DESKTOP_CHROME_PATH,
    CHROME_PATH: process.env.CHROME_PATH,
    PROGRAMFILES: process.env.PROGRAMFILES,
    'PROGRAMFILES(X86)': process.env['PROGRAMFILES(X86)'],
    LOCALAPPDATA: process.env.LOCALAPPDATA,
  };
  const prevAccessSync = fs.accessSync;
  process.env.HAM_DESKTOP_CHROME_PATH = '';
  process.env.CHROME_PATH = '';
  process.env.PROGRAMFILES = '';
  process.env['PROGRAMFILES(X86)'] = '';
  process.env.LOCALAPPDATA = '';
  fs.accessSync = () => {
    throw new Error('missing');
  };
  try {
    const g = realBrowserActionGates(baseRealPolicy({}), 'win32');
    assert.equal(g.ok, false);
    assert.equal(g.reason, 'chromium_not_found');
  } finally {
    fs.accessSync = prevAccessSync;
    process.env.HAM_DESKTOP_CHROME_PATH = prevEnv.HAM_DESKTOP_CHROME_PATH;
    process.env.CHROME_PATH = prevEnv.CHROME_PATH;
    process.env.PROGRAMFILES = prevEnv.PROGRAMFILES;
    process.env['PROGRAMFILES(X86)'] = prevEnv['PROGRAMFILES(X86)'];
    process.env.LOCALAPPDATA = prevEnv.LOCALAPPDATA;
  }
});

test('realBrowserActionGates: kill switch blocks', () => {
  const g = realBrowserActionGates(baseRealPolicy({ kill_switch: { engaged: true, reason: 't' } }), 'linux');
  assert.equal(g.ok, false);
  assert.equal(g.reason, 'kill_switch_engaged');
});

test('realBrowserActionGates: not armed blocks', () => {
  const g = realBrowserActionGates(
    baseRealPolicy({ real_browser_control_armed: false, permissions: { real_browser_automation: false } }),
    'linux',
  );
  assert.equal(g.ok, false);
  assert.equal(g.reason, 'real_browser_not_armed');
});

test('realBrowserActionGates: ok when clear on linux', () => {
  const g = realBrowserActionGates(baseRealPolicy({}), 'linux');
  if (!g.ok) {
    assert.equal(g.reason, 'chromium_not_found');
    return;
  }
  assert.equal(g.ok, true);
});

test('realBrowserActionGates: unsupported platform denied', () => {
  const g = realBrowserActionGates(baseRealPolicy({}), 'darwin');
  assert.equal(g.ok, false);
  assert.equal(g.reason, 'platform_not_supported');
});

test('discoverChromiumExecutableWindows: env override wins', () => {
  const prev = {
    HAM_DESKTOP_CHROME_PATH: process.env.HAM_DESKTOP_CHROME_PATH,
    CHROME_PATH: process.env.CHROME_PATH,
  };
  process.env.HAM_DESKTOP_CHROME_PATH = 'C:\\custom\\chrome.exe';
  process.env.CHROME_PATH = '';
  try {
    assert.equal(discoverChromiumExecutableWindows(), 'C:\\custom\\chrome.exe');
  } finally {
    process.env.HAM_DESKTOP_CHROME_PATH = prev.HAM_DESKTOP_CHROME_PATH;
    process.env.CHROME_PATH = prev.CHROME_PATH;
  }
});

test('discoverChromiumExecutableWindows: finds Program Files chrome', () => {
  const prevEnv = {
    HAM_DESKTOP_CHROME_PATH: process.env.HAM_DESKTOP_CHROME_PATH,
    CHROME_PATH: process.env.CHROME_PATH,
    PROGRAMFILES: process.env.PROGRAMFILES,
    'PROGRAMFILES(X86)': process.env['PROGRAMFILES(X86)'],
    LOCALAPPDATA: process.env.LOCALAPPDATA,
  };
  const prevAccessSync = fs.accessSync;
  process.env.HAM_DESKTOP_CHROME_PATH = '';
  process.env.CHROME_PATH = '';
  process.env.PROGRAMFILES = 'C:\\Program Files';
  process.env['PROGRAMFILES(X86)'] = '';
  process.env.LOCALAPPDATA = '';
  fs.accessSync = (p) => {
    if (String(p).toLowerCase().includes('google\\chrome\\application\\chrome.exe')) return;
    throw new Error('missing');
  };
  try {
    const found = discoverChromiumExecutableWindows();
    assert.ok(found && found.toLowerCase().includes('google\\chrome\\application\\chrome.exe'));
  } finally {
    fs.accessSync = prevAccessSync;
    process.env.HAM_DESKTOP_CHROME_PATH = prevEnv.HAM_DESKTOP_CHROME_PATH;
    process.env.CHROME_PATH = prevEnv.CHROME_PATH;
    process.env.PROGRAMFILES = prevEnv.PROGRAMFILES;
    process.env['PROGRAMFILES(X86)'] = prevEnv['PROGRAMFILES(X86)'];
    process.env.LOCALAPPDATA = prevEnv.LOCALAPPDATA;
  }
});

test('discoverChromiumExecutableWindows: missing env vars does not crash', () => {
  const prevEnv = {
    HAM_DESKTOP_CHROME_PATH: process.env.HAM_DESKTOP_CHROME_PATH,
    CHROME_PATH: process.env.CHROME_PATH,
    PROGRAMFILES: process.env.PROGRAMFILES,
    'PROGRAMFILES(X86)': process.env['PROGRAMFILES(X86)'],
    LOCALAPPDATA: process.env.LOCALAPPDATA,
  };
  process.env.HAM_DESKTOP_CHROME_PATH = '';
  process.env.CHROME_PATH = '';
  process.env.PROGRAMFILES = '';
  process.env['PROGRAMFILES(X86)'] = '';
  process.env.LOCALAPPDATA = '';
  try {
    assert.equal(discoverChromiumExecutableWindows(), null);
  } finally {
    process.env.HAM_DESKTOP_CHROME_PATH = prevEnv.HAM_DESKTOP_CHROME_PATH;
    process.env.CHROME_PATH = prevEnv.CHROME_PATH;
    process.env.PROGRAMFILES = prevEnv.PROGRAMFILES;
    process.env['PROGRAMFILES(X86)'] = prevEnv['PROGRAMFILES(X86)'];
    process.env.LOCALAPPDATA = prevEnv.LOCALAPPDATA;
  }
});

test('discoverChromiumExecutable: routes by platform', () => {
  const linux = discoverChromiumExecutable(() => '/usr/bin/chromium', 'linux');
  const unsupported = discoverChromiumExecutable(() => '/bin/false', 'darwin');
  assert.equal(typeof linux, 'string');
  assert.equal(unsupported, null);
});

test('pickDebugPort: bounded range for localhost CDP', () => {
  const p = pickDebugPort();
  assert.ok(p >= 9200 && p <= 9998);
});

test('waitForDevtoolsJsonVersion: retries then ok', async () => {
  let n = 0;
  const fetchImpl = async () => {
    n += 1;
    if (n < 3) throw new Error('conn');
    return { ok: true };
  };
  await waitForDevtoolsJsonVersion(9222, fetchImpl, 8000);
  assert.ok(n >= 3);
});

test('fetchPageDebuggerWebSocketUrl: picks first page target', async () => {
  const fetchImpl = async () => ({
    ok: true,
    json: async () => [
      { type: 'service_worker', webSocketDebuggerUrl: 'ws://ignore' },
      { type: 'page', url: 'https://a/', webSocketDebuggerUrl: 'ws://127.0.0.1/devtools/page/1' },
    ],
  });
  const u = await fetchPageDebuggerWebSocketUrl(9222, fetchImpl);
  assert.equal(u, 'ws://127.0.0.1/devtools/page/1');
});

test('fetchPageDebuggerWebSocketUrl: falls back to /devtools/page/ when type omitted', async () => {
  const fetchImpl = async () => ({
    ok: true,
    json: async () => [
      { type: 'browser', webSocketDebuggerUrl: 'ws://127.0.0.1/devtools/browser/abc' },
      { url: 'about:blank', webSocketDebuggerUrl: 'ws://127.0.0.1/devtools/page/99' },
    ],
  });
  const u = await fetchPageDebuggerWebSocketUrl(9222, fetchImpl);
  assert.equal(u, 'ws://127.0.0.1/devtools/page/99');
});

test('fetchPageDebuggerWebSocketUrl: tries /json when /json/list is not ok', async () => {
  let calls = 0;
  const fetchImpl = async (url) => {
    calls += 1;
    if (String(url).includes('/json/list')) {
      return { ok: false, status: 404, json: async () => ({}) };
    }
    return {
      ok: true,
      json: async () => [
        { type: 'page', url: 'about:blank', webSocketDebuggerUrl: 'ws://localhost:9333/devtools/page/z' },
      ],
    };
  };
  const u = await fetchPageDebuggerWebSocketUrl(9333, fetchImpl);
  assert.equal(u, 'ws://localhost:9333/devtools/page/z');
  assert.ok(calls >= 2);
});

test('normalizeLoopbackWebSocketUrl: localhost and ::1 become 127.0.0.1', () => {
  assert.equal(
    normalizeLoopbackWebSocketUrl('ws://localhost:9222/devtools/page/x'),
    'ws://127.0.0.1:9222/devtools/page/x',
  );
  assert.equal(
    normalizeLoopbackWebSocketUrl('ws://[::1]:9222/devtools/page/x'),
    'ws://127.0.0.1:9222/devtools/page/x',
  );
});

test('createRealBrowserCdpController: stop idempotent without spawn', () => {
  const c = createRealBrowserCdpController({
    userDataPath: '/tmp/ham-real-browser-test',
    path,
    fs,
  });
  const a = c.stopSession();
  const b = c.stopSession();
  assert.equal(a.ok, true);
  assert.equal(b.ok, true);
});

test('createRealBrowserCdpController: getStatus JSON has no profile path segments', () => {
  const secret = 'secret-profile-segment-abc';
  const c = createRealBrowserCdpController({
    userDataPath: path.join('/tmp', secret, 'ud'),
    path,
    fs,
  });
  const blob = JSON.stringify(c.getStatus());
  assert.ok(!blob.includes(secret), 'must not echo userData path in status');
});

test('discoverPlaywrightChromiumLinux: null or plausible chrome path', () => {
  const p = discoverPlaywrightChromiumLinux();
  assert.ok(p === null || (typeof p === 'string' && p.includes('chrome')));
});

test('reloadPageViaCdp: sends Page.reload with ignoreCache false and waits for load', async () => {
  /** @type {(() => void) | undefined} */
  let loadHandler;
  const cdp = {
    onceEvent: (method, fn) => {
      assert.equal(method, 'Page.loadEventFired');
      loadHandler = fn;
    },
    send: async (method, params) => {
      assert.equal(method, 'Page.reload');
      assert.deepEqual(params, { ignoreCache: false });
      queueMicrotask(() => {
        if (loadHandler) loadHandler();
      });
    },
  };
  const r = await reloadPageViaCdp(cdp, 5000);
  assert.equal(r.ok, true);
});

test('reloadPageViaCdp: send failure', async () => {
  const cdp = {
    onceEvent: () => {},
    send: async () => {
      throw new Error('cdp_down');
    },
  };
  const r = await reloadPageViaCdp(cdp, 1000);
  assert.equal(r.ok, false);
  assert.equal(r.error, 'reload_failed');
});

test('createRealBrowserCdpController: reload returns not_running without session', async () => {
  const c = createRealBrowserCdpController({
    userDataPath: '/tmp/ham-real-browser-reload',
    path,
    fs,
  });
  assert.equal(typeof c.reload, 'function');
  const r = await c.reload();
  assert.equal(r.ok, false);
  assert.equal(r.error, 'not_running');
});

test('clampScrollDelta clamps magnitude', () => {
  assert.equal(clampScrollDelta(99999), 600);
  assert.equal(clampScrollDelta(-800), -600);
  assert.equal(clampScrollDelta(0), 0);
});

test('clampWaitMs accepts only bounded inclusive range', () => {
  assert.equal(clampWaitMs(499), null);
  assert.equal(clampWaitMs(3001), null);
  assert.equal(clampWaitMs(1500), 1500);
});

test('isValidCandidateId: ham prefix only', () => {
  assert.equal(isValidCandidateId('ham_cand_1_0'), true);
  assert.equal(isValidCandidateId('evil'), false);
});

test('buildCandidateEnumerationExpression embeds epoch', () => {
  const s = buildCandidateEnumerationExpression(42);
  assert.ok(s.includes('EPOCH = 42'));
});

test('buildClickCandidateExpression dispatches MouseEvent', () => {
  const s = buildClickCandidateExpression('ham_cand_1_0');
  assert.ok(s.includes('MouseEvent'));
});

test('createRealBrowserCdpController: slice1 helpers return not_running without session', async () => {
  const c = createRealBrowserCdpController({
    userDataPath: '/tmp/ham-slice1',
    path,
    fs,
  });
  const o = await c.observeCompact();
  assert.equal(o.ok, false);
  assert.equal(o.error, 'not_running');
  const w = await c.waitBoundedMs(1000);
  assert.equal(w.ok, false);
  assert.equal(w.error, 'not_running');
  const s = await c.scrollVerticalBounded(100);
  assert.equal(s.ok, false);
  assert.equal(s.error, 'not_running');
  const e = await c.enumerateClickCandidates();
  assert.equal(e.ok, false);
  assert.equal(e.error, 'not_running');
  const k = await c.clickCandidate('ham_cand_1_0');
  assert.equal(k.ok, false);
  assert.equal(k.error, 'not_running');
});

test('createRealBrowserCdpController: clickCandidate rejects without session before id validation', async () => {
  const c = createRealBrowserCdpController({
    userDataPath: '/tmp/ham-click-id',
    path,
    fs,
  });
  const k = await c.clickCandidate('ham_cand_1_0');
  assert.equal(k.ok, false);
  assert.equal(k.error, 'not_running');
});
