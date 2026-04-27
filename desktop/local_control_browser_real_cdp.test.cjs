'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');

const {
  realBrowserActionGates,
  createRealBrowserCdpController,
  discoverPlaywrightChromiumLinux,
  reloadPageViaCdp,
  pickDebugPort,
  waitForDevtoolsJsonVersion,
  fetchPageDebuggerWebSocketUrl,
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

test('realBrowserActionGates: linux required', () => {
  const g = realBrowserActionGates(baseRealPolicy({}), 'win32');
  assert.equal(g.ok, false);
  assert.equal(g.reason, 'platform_not_supported');
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
  assert.equal(g.ok, true);
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
