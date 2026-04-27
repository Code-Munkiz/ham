'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');

const { buildLocalControlStatus, platformDerived, PHASE } = require('./local_control_status.cjs');

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

test('platformDerived: darwin unsupported', () => {
  assert.deepEqual(platformDerived('darwin'), {
    supported_platform: false,
    platform_status: 'unsupported',
  });
});

test('buildLocalControlStatus: enabled false, capabilities not_implemented', () => {
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
    assert.equal(st.phase, PHASE);
    assert.equal(st.enabled, false);
    assert.equal(st.available, true);
    assert.equal(st.supported_platform, true);
    assert.equal(st.platform_status, 'linux_first');
    for (const v of Object.values(st.capabilities)) {
      assert.equal(v, 'not_implemented');
    }
    assert.equal(st.paths.user_data_writable, true);
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
