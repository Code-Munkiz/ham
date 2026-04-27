'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const { browserActionGates } = require('./local_control_browser_mvp.cjs');

function basePolicy(over) {
  return {
    kill_switch: { engaged: false, reason: 'x' },
    browser_control_armed: true,
    permissions: { browser_automation: true },
    ...over,
  };
}

test('browserActionGates: linux required', () => {
  const g = browserActionGates(basePolicy({}), 'win32');
  assert.equal(g.ok, false);
  assert.equal(g.reason, 'platform_not_supported');
});

test('browserActionGates: kill switch blocks', () => {
  const g = browserActionGates(basePolicy({ kill_switch: { engaged: true, reason: 't' } }), 'linux');
  assert.equal(g.ok, false);
  assert.equal(g.reason, 'kill_switch_engaged');
});

test('browserActionGates: not armed blocks', () => {
  const g = browserActionGates(
    basePolicy({ browser_control_armed: false, permissions: { browser_automation: false } }),
    'linux',
  );
  assert.equal(g.ok, false);
  assert.equal(g.reason, 'browser_not_armed');
});

test('browserActionGates: ok when clear on linux', () => {
  const g = browserActionGates(basePolicy({}), 'linux');
  assert.equal(g.ok, true);
});
