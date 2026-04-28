'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');

const { buildLocalControlStatus, platformDerived, PHASE, SCHEMA_VERSION } = require('./local_control_status.cjs');

test('platformDerived: linux_first', () => {
  assert.deepEqual(platformDerived('linux'), {
    supported_platform: true,
    platform_status: 'linux_first',
  });
});

test('platformDerived: windows_planned', () => {
  assert.deepEqual(platformDerived('win32'), {
    supported_platform: true,
    platform_status: 'windows_planned',
  });
});

test('buildLocalControlStatus: windows browser_real not categorically unsupported', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ham-lc-test-win-'));
  try {
    const st = buildLocalControlStatus({
      platform: 'win32',
      userDataPath: tmp,
      security: { context_isolation: true, node_integration: false, sandbox: true },
      fs,
      path,
    });
    assert.equal(st.supported_platform, true);
    assert.equal(st.browser_real.supported, true);
    assert.notEqual(st.browser_real.gate_blocked_reason, 'platform_not_supported');
    assert.ok(['available_guarded', 'not_implemented'].includes(st.capabilities.real_browser_cdp));
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('platformDerived: darwin unsupported', () => {
  assert.deepEqual(platformDerived('darwin'), {
    supported_platform: false,
    platform_status: 'unsupported',
  });
});

test('buildLocalControlStatus: phase 4b aggregate + browser MVP + real browser fields, enabled false', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ham-lc-test-'));
  try {
    const st = buildLocalControlStatus({
      platform: 'linux',
      userDataPath: tmp,
      security: { context_isolation: true, node_integration: false, sandbox: true },
      fs,
      path,
    });
    assert.equal(st.kind, 'ham_desktop_local_control_status');
    assert.equal(SCHEMA_VERSION, 6);
    assert.equal(st.schema_version, 6);
    assert.equal(st.phase, PHASE);
    assert.equal(st.phase, 'browser_real_4b');
    assert.equal(st.enabled, false);
    assert.equal(st.available, true);
    assert.equal(st.supported_platform, true);
    assert.equal(st.platform_status, 'linux_first');
    assert.equal(st.capabilities.browser_automation, 'available_guarded');
    assert.equal(st.capabilities.filesystem_access, 'not_implemented');
    assert.equal(st.capabilities.shell_commands, 'not_implemented');
    assert.equal(st.capabilities.app_window_control, 'not_implemented');
    assert.equal(st.capabilities.mcp_adapters, 'not_implemented');
    assert.equal(st.paths.user_data_writable, true);
    assert.ok(st.policy);
    assert.equal(st.policy.enabled, false);
    assert.equal(st.policy.default_deny, true);
    assert.equal(st.kill_switch.engaged, true);
    assert.ok(st.sidecar);
    assert.equal(st.sidecar.mode, 'inert_process_shell');
    assert.equal(st.sidecar.implemented, true);
    assert.equal(st.sidecar.running, false);
    assert.equal(st.sidecar.start_allowed, false);
    assert.equal(st.sidecar.blocked_reason, 'kill_switch_engaged');
    assert.equal(st.sidecar.inbound_network, false);
    assert.equal(st.sidecar.droid_access, 'not_enabled');
    for (const v of Object.values(st.sidecar.capabilities)) {
      assert.equal(v, 'not_implemented');
    }
    assert.ok(st.browser_mvp);
    assert.equal(st.browser_mvp.supported, true);
    assert.equal(st.browser_mvp.armed, false);
    assert.equal(st.browser_mvp.gate_blocked_reason, 'kill_switch_engaged');
    assert.ok(st.browser_real);
    assert.equal(st.browser_real.supported, true);
    assert.equal(st.browser_real.managed_profile, true);
    assert.equal(st.browser_real.cdp_localhost_only, true);
    assert.equal(st.browser_real.uses_default_profile, false);
    assert.equal(st.browser_real.gate_blocked_reason, 'kill_switch_engaged');
    assert.ok(['available_guarded', 'not_implemented'].includes(st.capabilities.real_browser_cdp));
    assert.ok(st.audit);
    assert.equal(st.audit.redacted, true);
    assert.ok(Array.isArray(st.warnings));
    assert.ok(!JSON.stringify(st).includes(tmp), 'payload must not leak userData path');
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('buildLocalControlStatus: no raw path strings in serialized payload', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ham-lc-test-'));
  const secret = path.join(tmp, 'secret-segment-xyz');
  try {
    const st = buildLocalControlStatus({
      platform: 'linux',
      userDataPath: secret,
      security: { context_isolation: true, node_integration: false, sandbox: true },
      fs,
      path,
    });
    const blob = JSON.stringify(st);
    assert.ok(!blob.includes('secret-segment'), 'no path segments in JSON');
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
