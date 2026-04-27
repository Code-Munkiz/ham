'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');

const {
  defaultPolicy,
  loadPolicy,
  engageKillSwitch,
  normalizePolicyForPhase2,
  getPolicyStatusPayload,
} = require('./local_control_policy.cjs');

test('defaultPolicy: disabled, kill switch engaged, allowlists empty', () => {
  const p = defaultPolicy('linux');
  assert.equal(p.enabled, false);
  assert.equal(p.kill_switch.engaged, true);
  assert.equal(p.allowlists.browser_origins.length, 0);
  assert.equal(p.permissions.browser_automation, false);
});

test('normalizePolicyForPhase2: remands disengaged kill_switch', () => {
  const raw = {
    kill_switch: { engaged: false, reason: 'bad' },
    updated_at: '2020-01-01T00:00:00.000Z',
  };
  const n = normalizePolicyForPhase2(raw, 'linux');
  assert.equal(n.kill_switch.engaged, true);
  assert.equal(n.kill_switch.reason, 'auto_remanded_phase2');
});

test('engageKillSwitch: idempotent when already operator_engaged on disk', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ham-lc-pol-'));
  try {
    const o = { userDataPath: tmp, platform: 'linux', fs, path };
    engageKillSwitch(o);
    const second = engageKillSwitch(o);
    assert.equal(second.changed, false);
    assert.equal(second.policy.kill_switch.reason, 'operator_engaged');
    const blob = JSON.stringify(second.policy);
    assert.ok(!blob.includes(tmp));
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('getPolicyStatusPayload: no filesystem paths in JSON', () => {
  const p = defaultPolicy('win32');
  const st = getPolicyStatusPayload(p, { persisted: true });
  const blob = JSON.stringify(st);
  assert.ok(!blob.includes(':\\'), 'no windows path leaked');
  assert.ok(!blob.includes('/home/'), 'no unix home leaked');
  assert.equal(st.enabled, false);
});

test('loadPolicy: missing file is not persisted', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ham-lc-pol2-'));
  try {
    const { policy, persisted } = loadPolicy({
      userDataPath: tmp,
      platform: 'linux',
      fs,
      path,
    });
    assert.equal(persisted, false);
    assert.equal(policy.enabled, false);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
