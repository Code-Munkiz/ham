'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const { createSidecarManager, defaultChildScriptPath } = require('./local_control_sidecar_manager.cjs');

test('manager: default not running; snapshot has no pid', () => {
  const m = createSidecarManager({ childScriptPath: defaultChildScriptPath() });
  const snap = m.getSnapshot();
  assert.equal(snap.running, false);
  assert.equal(snap.health_last, null);
  const blob = JSON.stringify(snap);
  assert.ok(!blob.includes('pid'));
});

test('manager: start blocked when kill switch engaged', async () => {
  const events = [];
  const m = createSidecarManager({
    childScriptPath: defaultChildScriptPath(),
    onAuditEvent: (t) => events.push(t),
  });
  const r = await m.start({ killSwitchEngaged: true });
  assert.equal(r.ok, false);
  assert.equal(r.blocked, true);
  assert.equal(r.reason, 'kill_switch_engaged');
  assert.ok(events.includes('local_control_sidecar_start_blocked'));
  assert.equal(m.getSnapshot().running, false);
});

test('manager: start health stop; stop idempotent; no path in snapshot', async () => {
  const stops = [];
  const m = createSidecarManager({
    childScriptPath: defaultChildScriptPath(),
    onAuditEvent: (t) => {
      if (t === 'local_control_sidecar_stop') stops.push(t);
    },
  });
  const r = await m.start({ killSwitchEngaged: false });
  assert.equal(r.ok, true);
  assert.equal(m.getSnapshot().running, true);
  const ph = await m.pingHealth();
  assert.equal(ph.ok, true);
  const s1 = await m.stop();
  assert.equal(s1.ok, true);
  const s2 = await m.stop();
  assert.equal(s2.ok, true);
  assert.equal(s2.idempotent, true);
  assert.equal(m.getSnapshot().running, false);
  assert.equal(stops.length, 1);
  assert.ok(!JSON.stringify(m.getSnapshot()).includes(path.sep));
});

test('manager: pingHealth when not running', async () => {
  const m = createSidecarManager({ childScriptPath: defaultChildScriptPath() });
  const ph = await m.pingHealth();
  assert.equal(ph.ok, false);
  assert.equal(ph.reason, 'not_running');
});
