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
  normalizePolicyV2FromDisk,
  getPolicyStatusPayload,
  armBrowserOnlyControl,
  disengageKillSwitchForBrowserMvp,
  BROWSER_MVP_KILL_SWITCH_RELEASE_TOKEN,
  POLICY_SCHEMA_VERSION,
} = require('./local_control_policy.cjs');

test('defaultPolicy: schema v2, browser arm false, kill switch engaged', () => {
  const p = defaultPolicy('linux');
  assert.equal(p.schema_version, POLICY_SCHEMA_VERSION);
  assert.equal(p.enabled, false);
  assert.equal(p.kill_switch.engaged, true);
  assert.equal(p.browser_control_armed, false);
  assert.equal(p.permissions.browser_automation, false);
  assert.equal(p.permissions.filesystem_access, false);
});

test('normalizePolicyForPhase2 (v1 migration): remands disengaged kill_switch', () => {
  const raw = {
    kill_switch: { engaged: false, reason: 'bad' },
    updated_at: '2020-01-01T00:00:00.000Z',
  };
  const n = normalizePolicyForPhase2(raw, 'linux');
  assert.equal(n.kill_switch.engaged, true);
  assert.equal(n.kill_switch.reason, 'auto_remanded_phase2');
});

test('normalizePolicyV2FromDisk: preserves disengaged kill_switch', () => {
  const n = normalizePolicyV2FromDisk(
    {
      schema_version: 2,
      kill_switch: { engaged: false, reason: 'browser_mvp_operator_ack' },
      browser_control_armed: true,
      permissions: { browser_automation: true },
    },
    'linux',
  );
  assert.equal(n.kill_switch.engaged, false);
  assert.equal(n.browser_control_armed, true);
  assert.equal(n.permissions.browser_automation, true);
});

test('normalizePolicyV2FromDisk: clamps non-browser permissions false', () => {
  const n = normalizePolicyV2FromDisk(
    {
      schema_version: 2,
      kill_switch: { engaged: false, reason: 'x' },
      browser_control_armed: true,
      permissions: {
        browser_automation: true,
        filesystem_access: true,
        shell_commands: true,
        app_window_control: true,
        mcp_adapters: true,
      },
    },
    'linux',
  );
  assert.equal(n.permissions.filesystem_access, false);
  assert.equal(n.permissions.shell_commands, false);
  assert.equal(n.permissions.app_window_control, false);
  assert.equal(n.permissions.mcp_adapters, false);
});

test('engageKillSwitch: clears browser arm', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ham-lc-pol-'));
  try {
    armBrowserOnlyControl({ userDataPath: tmp, platform: 'linux', fs, path });
    engageKillSwitch({ userDataPath: tmp, platform: 'linux', fs, path });
    const { policy } = loadPolicy({ userDataPath: tmp, platform: 'linux', fs, path });
    assert.equal(policy.browser_control_armed, false);
    assert.equal(policy.permissions.browser_automation, false);
    assert.equal(policy.kill_switch.engaged, true);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('armBrowserOnlyControl: sets narrow browser permission', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ham-lc-pol2-'));
  try {
    armBrowserOnlyControl({ userDataPath: tmp, platform: 'linux', fs, path });
    const { policy } = loadPolicy({ userDataPath: tmp, platform: 'linux', fs, path });
    assert.equal(policy.browser_control_armed, true);
    assert.equal(policy.permissions.browser_automation, true);
    assert.equal(policy.permissions.filesystem_access, false);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('disengageKillSwitchForBrowserMvp: requires token', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ham-lc-pol3-'));
  try {
    const bad = disengageKillSwitchForBrowserMvp({
      userDataPath: tmp,
      platform: 'linux',
      fs,
      path,
      token: 'wrong',
    });
    assert.equal(bad.ok, false);
    const ok = disengageKillSwitchForBrowserMvp({
      userDataPath: tmp,
      platform: 'linux',
      fs,
      path,
      token: BROWSER_MVP_KILL_SWITCH_RELEASE_TOKEN,
    });
    assert.equal(ok.ok, true);
    const { policy } = loadPolicy({ userDataPath: tmp, platform: 'linux', fs, path });
    assert.equal(policy.kill_switch.engaged, false);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('getPolicyStatusPayload: browser flags present', () => {
  const p = defaultPolicy('linux');
  p.browser_control_armed = true;
  p.browser_allow_loopback = false;
  const st = getPolicyStatusPayload(p, { persisted: true });
  assert.equal(st.browser_control_armed, true);
  assert.equal(st.browser_allow_loopback, false);
});

test('loadPolicy: missing file is not persisted', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ham-lc-pol4-'));
  try {
    const { policy, persisted } = loadPolicy({
      userDataPath: tmp,
      platform: 'linux',
      fs,
      path,
    });
    assert.equal(persisted, false);
    assert.equal(policy.schema_version, POLICY_SCHEMA_VERSION);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
