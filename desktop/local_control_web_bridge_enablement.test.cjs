'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');

const {
  parseEnvFlag,
  localWebBridgeEnabled,
  localWebBridgeDisabledReason,
} = require('./local_control_web_bridge_enablement.cjs');

test('parseEnvFlag: truthy/falsy env values', () => {
  assert.equal(parseEnvFlag('1'), true);
  assert.equal(parseEnvFlag('true'), true);
  assert.equal(parseEnvFlag('on'), true);
  assert.equal(parseEnvFlag('0'), false);
  assert.equal(parseEnvFlag('false'), false);
  assert.equal(parseEnvFlag('off'), false);
  assert.equal(parseEnvFlag(''), null);
  assert.equal(parseEnvFlag('junk'), null);
});

test('localWebBridgeEnabled: packaged default enabled when env unset', () => {
  assert.equal(localWebBridgeEnabled({ envValue: '', isPackaged: true }), true);
});

test('localWebBridgeEnabled: dev default disabled when env unset', () => {
  assert.equal(localWebBridgeEnabled({ envValue: '', isPackaged: false }), false);
});

test('localWebBridgeEnabled: explicit env override wins', () => {
  assert.equal(localWebBridgeEnabled({ envValue: '0', isPackaged: true }), false);
  assert.equal(localWebBridgeEnabled({ envValue: '1', isPackaged: false }), true);
});

test('localWebBridgeDisabledReason: explicit disable is reported', () => {
  assert.equal(localWebBridgeDisabledReason({ envValue: '0', isPackaged: true }), 'explicit_disabled');
  assert.equal(localWebBridgeDisabledReason({ envValue: 'off', isPackaged: false }), 'explicit_disabled');
});

test('localWebBridgeDisabledReason: dev default reason, packaged unset none', () => {
  assert.equal(localWebBridgeDisabledReason({ envValue: '', isPackaged: false }), 'disabled_by_default_dev');
  assert.equal(localWebBridgeDisabledReason({ envValue: '', isPackaged: true }), null);
});

