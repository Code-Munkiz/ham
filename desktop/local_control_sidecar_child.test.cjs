'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const readline = require('node:readline');
const path = require('node:path');

function lineReader(stdout) {
  return readline.createInterface({ input: stdout, crlfDelay: Infinity });
}

test('sidecar child: health, status, shutdown; unknown rejected', async () => {
  const childPath = path.join(__dirname, 'local_control_sidecar_child.cjs');
  const proc = spawn(process.execPath, [childPath], {
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
  });
  const rl = lineReader(proc.stdout);
  const next = () =>
    new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error('timeout')), 5000);
      rl.once('line', (line) => {
        clearTimeout(t);
        resolve(JSON.parse(line));
      });
    });

  proc.stdin.write(`${JSON.stringify({ method: 'health', id: 'h1' })}\n`);
  const h = await next();
  assert.equal(h.ok, true);
  assert.equal(h.method, 'health');

  proc.stdin.write(`${JSON.stringify({ method: 'status', id: 's1' })}\n`);
  const s = await next();
  assert.equal(s.ok, true);
  assert.equal(s.result.capabilities.browser_automation, 'not_implemented');

  proc.stdin.write(`${JSON.stringify({ method: 'evil', id: 'x1' })}\n`);
  const bad = await next();
  assert.equal(bad.ok, false);
  assert.equal(bad.error, 'method_not_allowed');

  proc.stdin.write(`${JSON.stringify({ method: 'shutdown', id: 'q1' })}\n`);
  const q = await next();
  assert.equal(q.ok, true);
  assert.equal(q.method, 'shutdown');

  await new Promise((resolve, reject) => {
    const t = setTimeout(() => reject(new Error('exit timeout')), 5000);
    proc.once('exit', (code) => {
      clearTimeout(t);
      assert.equal(code, 0);
      resolve(undefined);
    });
  });
  rl.close();
});
