'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('path');

test('preload exposes narrow localControl methods only (no browser IPC)', () => {
  const src = fs.readFileSync(path.join(__dirname, 'preload.cjs'), 'utf8');
  assert.ok(src.includes('ham-desktop:local-control-engage-kill-switch'));
  assert.ok(src.includes('ham-desktop:local-control-get-sidecar-status'));
  assert.ok(src.includes('ham-desktop:local-control-sidecar-health'));
  assert.ok(src.includes('ham-desktop:local-control-sidecar-stop'));
  assert.ok(src.includes('ham-desktop:local-control-sidecar-start'));
  assert.ok(src.includes("exposeInMainWorld('hamDesktop'"));
  assert.ok(!src.includes('local-control-browser'), 'preload must not register browser IPC');
  assert.ok(!src.includes('local-control-browser-real'), 'preload must not register real-browser IPC');

  const forbidden = [
    'local-control-enable',
    'local-control-disable',
    'local-control-disengage',
    'local-control-run',
    'local-control-execute',
    'local-control-shell',
    'local-control-spawn',
    'local-control-browser',
    'sidecar-execute',
    'sidecar-run',
    'sidecar-shell',
    'sidecar-fs',
    'sidecar-browser',
    'sidecar-mcp',
  ];
  for (const f of forbidden) {
    assert.ok(!src.includes(f), `must not include ${f}`);
  }
});
