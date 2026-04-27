'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const { buildSidecarStatus, KIND, createIdleSidecarManagerView } = require('./local_control_sidecar_status.cjs');

test('buildSidecarStatus: phase 3b shape, capabilities not_implemented', () => {
  const s = buildSidecarStatus({
    killSwitchEngaged: true,
    manager: createIdleSidecarManagerView(),
  });
  assert.equal(s.kind, KIND);
  assert.equal(s.implemented, true);
  assert.equal(s.mode, 'inert_process_shell');
  assert.equal(s.transport, 'stdio_json_rpc');
  assert.equal(s.running, false);
  assert.equal(s.start_allowed, false);
  assert.equal(s.blocked_reason, 'kill_switch_engaged');
  assert.equal(s.health, 'unavailable');
  assert.equal(s.droid_access, 'not_enabled');
  assert.equal(s.inbound_network, false);
  for (const v of Object.values(s.capabilities)) {
    assert.equal(v, 'not_implemented');
  }
  const blob = JSON.stringify(s);
  assert.ok(!blob.includes(path.sep));
});

test('buildSidecarStatus: start_allowed when kill switch not engaged', () => {
  const mgr = {
    getSnapshot: () => ({ running: true, health_last: 'ok' }),
  };
  const s = buildSidecarStatus({ killSwitchEngaged: false, manager: mgr });
  assert.equal(s.start_allowed, true);
  assert.equal(s.blocked_reason, null);
  assert.equal(s.running, true);
  assert.equal(s.health, 'ok');
});
