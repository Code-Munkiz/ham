'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('preload exposes narrow localControl methods only', () => {
  const src = fs.readFileSync(path.join(__dirname, 'preload.cjs'), 'utf8');
  assert.ok(src.includes('ham-desktop:local-control-engage-kill-switch'));
  assert.ok(src.includes("exposeInMainWorld('hamDesktop'"));
  const forbidden = [
    'local-control-enable',
    'local-control-disable',
    'local-control-disengage',
    'local-control-run',
    'local-control-execute',
    'local-control-shell',
  ];
  for (const f of forbidden) {
    assert.ok(!src.includes(f), `must not include ${f}`);
  }
});
