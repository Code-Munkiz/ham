'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { createLocalControlWebBridge } = require('./local_control_web_bridge.cjs');

const ORIGIN = 'https://ham-nine-mu.vercel.app';
const STALE = 'https://ham-kappa-fawn.vercel.app';
const AARON = 'https://aaron-bundys-projects-ham.vercel.app';

async function jfetch(url, opts = {}) {
  const res = await fetch(url, opts);
  const text = await res.text();
  let body = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  return { status: res.status, body, headers: res.headers };
}

test('web bridge binds 127.0.0.1 only', async () => {
  const bridge = createLocalControlWebBridge({ port: 0 });
  try {
    const addr = await bridge.start();
    assert.equal(addr.host, '127.0.0.1');
  } finally {
    await bridge.stop();
  }
});

test('health denies non-canonical and stale origins', async () => {
  const bridge = createLocalControlWebBridge({ port: 0 });
  try {
    const addr = await bridge.start();
    const base = `http://${addr.host}:${addr.port}/ham/local-control/v1`;
    const bad = await jfetch(`${base}/health`, { headers: { Origin: STALE } });
    assert.equal(bad.status, 403);
    assert.equal(bad.body.origin_allowed, false);

    const bad2 = await jfetch(`${base}/health`, { headers: { Origin: AARON } });
    assert.equal(bad2.status, 403);
    assert.equal(bad2.body.error, 'origin_not_allowed');
  } finally {
    await bridge.stop();
  }
});

test('health returns minimal payload for canonical origin', async () => {
  const bridge = createLocalControlWebBridge({ port: 0 });
  try {
    const addr = await bridge.start();
    const base = `http://${addr.host}:${addr.port}/ham/local-control/v1`;
    const r = await jfetch(`${base}/health`, { headers: { Origin: ORIGIN } });
    assert.equal(r.status, 200);
    assert.equal(r.body.ok, true);
    assert.equal(r.body.bridge_version, 'v1');
    assert.equal(r.body.pairing_required, true);
    assert.equal(typeof r.body.paired, 'boolean');
    assert.equal(r.body.origin_allowed, true);
    assert.equal(Object.keys(r.body).sort().join(','), 'bridge_version,ok,origin_allowed,paired,pairing_required');
  } finally {
    await bridge.stop();
  }
});

test('no cookies used for auth; missing bearer denied', async () => {
  const bridge = createLocalControlWebBridge({ port: 0 });
  try {
    const addr = await bridge.start();
    const base = `http://${addr.host}:${addr.port}/ham/local-control/v1`;
    const r = await jfetch(`${base}/status`, {
      headers: {
        Origin: ORIGIN,
        Cookie: 'session=abc',
      },
    });
    assert.equal(r.status, 401);
    assert.equal(r.body.error, 'token_missing');
    assert.equal(r.headers.get('set-cookie'), null);
  } finally {
    await bridge.stop();
  }
});

test('pairing code single-use and invalid code denied', async () => {
  const bridge = createLocalControlWebBridge({ port: 0 });
  try {
    const addr = await bridge.start();
    const base = `http://${addr.host}:${addr.port}/ham/local-control/v1`;
    const issued = bridge.issuePairingCode();

    const one = await jfetch(`${base}/pairing/exchange`, {
      method: 'POST',
      headers: { Origin: ORIGIN, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pairing_code: issued.code,
        client_nonce: 'n1',
        requested_origin: ORIGIN,
      }),
    });
    assert.equal(one.status, 200);
    assert.equal(one.body.ok, true);
    assert.deepEqual(one.body.scopes, ['status.read', 'browser.intent', 'machine.escalation.request']);

    const two = await jfetch(`${base}/pairing/exchange`, {
      method: 'POST',
      headers: { Origin: ORIGIN, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pairing_code: issued.code,
        client_nonce: 'n2',
        requested_origin: ORIGIN,
      }),
    });
    assert.equal(two.status, 401);
    assert.equal(two.body.error, 'pairing_code_invalid');

    const invalid = await jfetch(`${base}/pairing/exchange`, {
      method: 'POST',
      headers: { Origin: ORIGIN, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pairing_code: '999-999',
        client_nonce: 'n3',
        requested_origin: ORIGIN,
      }),
    });
    assert.equal(invalid.status, 401);
    assert.equal(invalid.body.error, 'pairing_code_invalid');
  } finally {
    await bridge.stop();
  }
});

test('pairing code expires', async () => {
  let now = Date.now();
  const bridge = createLocalControlWebBridge({
    port: 0,
    nowMs: () => now,
    pairCodeTtlMs: 30_000,
  });
  try {
    const addr = await bridge.start();
    const base = `http://${addr.host}:${addr.port}/ham/local-control/v1`;
    const issued = bridge.issuePairingCode();
    now += 30_001;
    const r = await jfetch(`${base}/pairing/exchange`, {
      method: 'POST',
      headers: { Origin: ORIGIN, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pairing_code: issued.code,
        client_nonce: 'n4',
        requested_origin: ORIGIN,
      }),
    });
    assert.equal(r.status, 401);
    assert.equal(r.body.error, 'pairing_code_expired');
  } finally {
    await bridge.stop();
  }
});

test('pairing TTL defaults and clamp are enforced', async () => {
  const bridge = createLocalControlWebBridge({ port: 0 });
  try {
    const cfg0 = bridge.getPairingConfig();
    assert.equal(cfg0.pairing_code_ttl_sec, 120);
    assert.equal(cfg0.pairing_code_ttl_min_sec, 30);
    assert.equal(cfg0.pairing_code_ttl_max_sec, 600);
    assert.equal(cfg0.token_ttl_sec, 900);

    const low = bridge.setPairingCodeTtlSec(1);
    assert.equal(low.pairing_code_ttl_sec, 30);

    const high = bridge.setPairingCodeTtlSec(9999);
    assert.equal(high.pairing_code_ttl_sec, 600);

    const fallback = bridge.setPairingCodeTtlSec(Number.NaN);
    assert.equal(fallback.pairing_code_ttl_sec, 120);
  } finally {
    await bridge.stop();
  }
});

test('changing TTL does not extend existing active pairing code expiry', async () => {
  let now = Date.now();
  const bridge = createLocalControlWebBridge({
    port: 0,
    nowMs: () => now,
    pairCodeTtlMs: 120_000,
  });
  try {
    const addr = await bridge.start();
    const base = `http://${addr.host}:${addr.port}/ham/local-control/v1`;
    const issued = bridge.issuePairingCode();
    bridge.setPairingCodeTtlSec(600);
    now += 120_001;
    const expired = await jfetch(`${base}/pairing/exchange`, {
      method: 'POST',
      headers: { Origin: ORIGIN, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pairing_code: issued.code,
        client_nonce: 'n-ttl-old',
        requested_origin: ORIGIN,
      }),
    });
    assert.equal(expired.status, 401);
    assert.equal(expired.body.error, 'pairing_code_expired');
  } finally {
    await bridge.stop();
  }
});

test('new pairing codes use updated TTL setting', async () => {
  let now = Date.now();
  const bridge = createLocalControlWebBridge({
    port: 0,
    nowMs: () => now,
  });
  try {
    const addr = await bridge.start();
    const base = `http://${addr.host}:${addr.port}/ham/local-control/v1`;
    bridge.setPairingCodeTtlSec(30);
    const issued = bridge.issuePairingCode();
    now += 30_001;
    const expired = await jfetch(`${base}/pairing/exchange`, {
      method: 'POST',
      headers: { Origin: ORIGIN, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pairing_code: issued.code,
        client_nonce: 'n-ttl-new',
        requested_origin: ORIGIN,
      }),
    });
    assert.equal(expired.status, 401);
    assert.equal(expired.body.error, 'pairing_code_expired');
  } finally {
    await bridge.stop();
  }
});

test('token issued only for valid canonical origin', async () => {
  const bridge = createLocalControlWebBridge({ port: 0 });
  try {
    const addr = await bridge.start();
    const base = `http://${addr.host}:${addr.port}/ham/local-control/v1`;
    const issued = bridge.issuePairingCode();

    const bad = await jfetch(`${base}/pairing/exchange`, {
      method: 'POST',
      headers: { Origin: STALE, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pairing_code: issued.code,
        client_nonce: 'n5',
        requested_origin: STALE,
      }),
    });
    assert.equal(bad.status, 403);

    const issued2 = bridge.issuePairingCode();
    const ok = await jfetch(`${base}/pairing/exchange`, {
      method: 'POST',
      headers: { Origin: ORIGIN, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pairing_code: issued2.code,
        client_nonce: 'n6',
        requested_origin: ORIGIN,
      }),
    });
    assert.equal(ok.status, 200);
    assert.equal(typeof ok.body.access_token, 'string');
  } finally {
    await bridge.stop();
  }
});

test('expired token denied and revoked token denied', async () => {
  let now = Date.now();
  const bridge = createLocalControlWebBridge({
    port: 0,
    nowMs: () => now,
    tokenTtlMs: 1000,
  });
  try {
    const addr = await bridge.start();
    const base = `http://${addr.host}:${addr.port}/ham/local-control/v1`;
    const issued = bridge.issuePairingCode();
    const ex = await jfetch(`${base}/pairing/exchange`, {
      method: 'POST',
      headers: { Origin: ORIGIN, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pairing_code: issued.code,
        client_nonce: 'n7',
        requested_origin: ORIGIN,
      }),
    });
    const token = ex.body.access_token;

    now += 1001;
    const expired = await jfetch(`${base}/status`, {
      headers: { Origin: ORIGIN, Authorization: `Bearer ${token}` },
    });
    assert.equal(expired.status, 401);
    assert.equal(expired.body.error, 'token_invalid');

    const issued2 = bridge.issuePairingCode();
    const ex2 = await jfetch(`${base}/pairing/exchange`, {
      method: 'POST',
      headers: { Origin: ORIGIN, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pairing_code: issued2.code,
        client_nonce: 'n8',
        requested_origin: ORIGIN,
      }),
    });
    const token2 = ex2.body.access_token;
    const rv = await jfetch(`${base}/pairing/revoke`, {
      method: 'POST',
      headers: { Origin: ORIGIN, Authorization: `Bearer ${token2}` },
    });
    assert.equal(rv.status, 200);
    assert.equal(rv.body.ok, true);
    const revoked = await jfetch(`${base}/status`, {
      headers: { Origin: ORIGIN, Authorization: `Bearer ${token2}` },
    });
    assert.equal(revoked.status, 401);
    assert.equal(revoked.body.error, 'token_invalid');
  } finally {
    await bridge.stop();
  }
});

test('authenticated endpoint denies wrong origin', async () => {
  const bridge = createLocalControlWebBridge({ port: 0 });
  try {
    const addr = await bridge.start();
    const base = `http://${addr.host}:${addr.port}/ham/local-control/v1`;
    const issued = bridge.issuePairingCode();
    const ex = await jfetch(`${base}/pairing/exchange`, {
      method: 'POST',
      headers: { Origin: ORIGIN, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pairing_code: issued.code,
        client_nonce: 'n9',
        requested_origin: ORIGIN,
      }),
    });
    const token = ex.body.access_token;
    const bad = await jfetch(`${base}/status`, {
      headers: {
        Origin: STALE,
        Authorization: `Bearer ${token}`,
      },
    });
    assert.equal(bad.status, 403);
    assert.equal(bad.body.error, 'origin_not_allowed');
  } finally {
    await bridge.stop();
  }
});

test('browser and machine routes require bearer token', async () => {
  const bridge = createLocalControlWebBridge({
    port: 0,
    executeBrowserIntent: async () => ({ ok: true, status: 'executed', browser_bridge: { status: 'executed' } }),
    executeMachineEscalationRequest: async () => ({
      ok: true,
      selected_mode: 'machine',
      escalated_from: 'browser',
      escalation_trigger: 'partial',
      status: 'approved_pending_execution',
    }),
  });
  try {
    const addr = await bridge.start();
    const base = `http://${addr.host}:${addr.port}/ham/local-control/v1`;
    const b = await jfetch(`${base}/browser/intent`, {
      method: 'POST',
      headers: { Origin: ORIGIN, 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'navigate_and_capture', url: 'https://example.com' }),
    });
    assert.equal(b.status, 401);
    assert.equal(b.body.error, 'token_missing');

    const m = await jfetch(`${base}/machine/escalation-request`, {
      method: 'POST',
      headers: { Origin: ORIGIN, 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    assert.equal(m.status, 401);
    assert.equal(m.body.error, 'token_missing');
  } finally {
    await bridge.stop();
  }
});

test('/browser/intent requires browser scope and canonical origin', async () => {
  const bridge = createLocalControlWebBridge({
    port: 0,
    executeBrowserIntent: async () => ({ ok: true, status: 'executed', browser_bridge: { status: 'executed' } }),
  });
  try {
    const addr = await bridge.start();
    const base = `http://${addr.host}:${addr.port}/ham/local-control/v1`;
    const issued = bridge.issuePairingCode();
    const ex = await jfetch(`${base}/pairing/exchange`, {
      method: 'POST',
      headers: { Origin: ORIGIN, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pairing_code: issued.code,
        client_nonce: 'n-browser-scope',
        requested_origin: ORIGIN,
      }),
    });
    const token = ex.body.access_token;

    const allowed = await jfetch(`${base}/browser/intent`, {
      method: 'POST',
      headers: {
        Origin: ORIGIN,
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        action: 'navigate_and_capture',
        url: 'https://example.com',
      }),
    });
    assert.equal(allowed.status, 200);
    assert.equal(allowed.body.ok, true);

    const deniedOrigin = await jfetch(`${base}/browser/intent`, {
      method: 'POST',
      headers: {
        Origin: STALE,
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        action: 'navigate_and_capture',
        url: 'https://example.com',
      }),
    });
    assert.equal(deniedOrigin.status, 403);
    assert.equal(deniedOrigin.body.error, 'origin_not_allowed');
  } finally {
    await bridge.stop();
  }
});

test('/machine/escalation-request validates trigger, context, confirmation and scope', async () => {
  const bridge = createLocalControlWebBridge({
    port: 0,
    executeMachineEscalationRequest: async (payload) => ({
      ok: true,
      selected_mode: 'machine',
      escalated_from: payload.escalated_from,
      escalation_trigger: payload.trigger,
      status: 'approved_pending_execution',
    }),
  });
  try {
    const addr = await bridge.start();
    const base = `http://${addr.host}:${addr.port}/ham/local-control/v1`;
    const issued = bridge.issuePairingCode();
    const ex = await jfetch(`${base}/pairing/exchange`, {
      method: 'POST',
      headers: { Origin: ORIGIN, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pairing_code: issued.code,
        client_nonce: 'n-machine-scope',
        requested_origin: ORIGIN,
      }),
    });
    const token = ex.body.access_token;

    const missingConfirm = await jfetch(`${base}/machine/escalation-request`, {
      method: 'POST',
      headers: {
        Origin: ORIGIN,
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        intent_id: 'i1',
        escalated_from: 'browser',
        trigger: 'partial',
        user_confirmed: false,
      }),
    });
    assert.equal(missingConfirm.status, 409);
    assert.equal(missingConfirm.body.error, 'user_confirmation_required');

    const badTrigger = await jfetch(`${base}/machine/escalation-request`, {
      method: 'POST',
      headers: {
        Origin: ORIGIN,
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        intent_id: 'i2',
        escalated_from: 'browser',
        trigger: 'unknown',
        user_confirmed: true,
      }),
    });
    assert.equal(badTrigger.status, 400);
    assert.equal(badTrigger.body.error, 'trigger_not_allowed');

    const noBrowserContext = await jfetch(`${base}/machine/escalation-request`, {
      method: 'POST',
      headers: {
        Origin: ORIGIN,
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        intent_id: 'i3',
        escalated_from: 'chat',
        trigger: 'partial',
        user_confirmed: true,
      }),
    });
    assert.equal(noBrowserContext.status, 409);
    assert.equal(noBrowserContext.body.error, 'browser_context_required');

    const ok = await jfetch(`${base}/machine/escalation-request`, {
      method: 'POST',
      headers: {
        Origin: ORIGIN,
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        intent_id: 'i4',
        escalated_from: 'browser',
        trigger: 'partial',
        user_confirmed: true,
        requested_scope: 'narrow_task',
        browser_bridge_status: 'partial',
      }),
    });
    assert.equal(ok.status, 200);
    assert.equal(ok.body.ok, true);
    assert.equal(ok.body.status, 'approved_pending_execution');
  } finally {
    await bridge.stop();
  }
});

