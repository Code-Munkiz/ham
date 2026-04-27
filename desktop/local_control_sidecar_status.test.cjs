'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const { buildMockSidecarStatus, KIND } = require('./local_control_sidecar_status.cjs');

test('buildMockSidecarStatus: mock only, no automation', () => {
  const s = buildMockSidecarStatus();
  assert.equal(s.kind, KIND);
  assert.equal(s.mode, 'mock_status_only');
  assert.equal(s.implemented, false);
  assert.equal(s.running, false);
  assert.equal(s.inbound_network, false);
  assert.equal(s.droid_access, 'not_enabled');
  assert.equal(s.transport, 'stdio_json_rpc_planned');
  for (const v of Object.values(s.capabilities)) {
    assert.equal(v, 'not_implemented');
  }
  const blob = JSON.stringify(s);
  assert.ok(!blob.includes(path.sep));
});
