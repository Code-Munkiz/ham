'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('preload exposes narrow localControl methods only', () => {
  const src = fs.readFileSync(path.join(__dirname, 'preload.cjs'), 'utf8');
  assert.ok(src.includes('ham-desktop:local-control-engage-kill-switch'));
  assert.ok(src.includes('ham-desktop:local-control-get-sidecar-status'));
  assert.ok(src.includes('ham-desktop:local-control-sidecar-health'));
  assert.ok(src.includes('ham-desktop:local-control-sidecar-stop'));
  assert.ok(src.includes('ham-desktop:local-control-sidecar-start'));
  assert.ok(src.includes('ham-desktop:local-control-browser-arm'));
  assert.ok(src.includes('ham-desktop:local-control-get-browser-status'));
  assert.ok(src.includes('ham-desktop:local-control-browser-start-session'));
  assert.ok(src.includes('ham-desktop:local-control-browser-navigate'));
  assert.ok(src.includes('ham-desktop:local-control-browser-screenshot'));
  assert.ok(src.includes('ham-desktop:local-control-browser-stop-session'));
  assert.ok(src.includes('ham-desktop:local-control-browser-real-arm'));
  assert.ok(src.includes('ham-desktop:local-control-get-browser-real-status'));
  assert.ok(src.includes('ham-desktop:local-control-browser-real-start-session'));
  assert.ok(src.includes('ham-desktop:local-control-browser-real-navigate'));
  assert.ok(src.includes('ham-desktop:local-control-browser-real-reload'));
  assert.ok(src.includes('ham-desktop:local-control-browser-real-screenshot'));
  assert.ok(src.includes('ham-desktop:local-control-browser-real-observe-compact'));
  assert.ok(src.includes('ham-desktop:local-control-browser-real-wait'));
  assert.ok(src.includes('ham-desktop:local-control-browser-real-scroll'));
  assert.ok(src.includes('ham-desktop:local-control-browser-real-enumerate-candidates'));
  assert.ok(src.includes('ham-desktop:local-control-browser-real-click-candidate'));
  assert.ok(src.includes('ham-desktop:local-control-browser-real-stop-session'));
  assert.ok(src.includes("exposeInMainWorld('hamDesktop'"));
  const forbidden = [
    'local-control-enable',
    'local-control-disable',
    'local-control-disengage',
    'local-control-run',
    'local-control-execute',
    'local-control-shell',
    'local-control-spawn',
    'local-control-start-sidecar',
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
