'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');

const { getAuditStatus, appendAuditEvent, eventsFilePath } = require('./local_control_audit.cjs');

test('appendAuditEvent rejects unknown type', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ham-lc-audit-'));
  try {
    const r = appendAuditEvent({
      userDataPath: tmp,
      type: 'evil_arbitrary',
      fs,
      path,
    });
    assert.equal(r.ok, false);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('appendAuditEvent lines contain no path segments', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ham-lc-audit2-'));
  const secret = 'SECRET_PATH_MARKER_XYZ';
  try {
    const ud = path.join(tmp, secret);
    fs.mkdirSync(ud, { recursive: true });
    appendAuditEvent({
      userDataPath: ud,
      type: 'local_control_status_read',
      fs,
      path,
    });
    const fp = eventsFilePath(ud, path);
    const line = fs.readFileSync(fp, 'utf8').trim();
    assert.ok(!line.includes(secret));
    const row = JSON.parse(line);
    assert.equal(row.type, 'local_control_status_read');
    assert.ok(typeof row.ts_iso === 'string');
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test('getAuditStatus exposes redacted flag, no paths', () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'ham-lc-audit3-'));
  try {
    const st = getAuditStatus({ userDataPath: tmp, fs, path });
    assert.equal(st.redacted, true);
    const blob = JSON.stringify(st);
    assert.ok(!blob.includes(tmp));
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
