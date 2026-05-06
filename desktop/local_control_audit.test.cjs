"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const fs = require("node:fs");
const os = require("node:os");

const { getAuditStatus, appendAuditEvent, eventsFilePath } = require("./local_control_audit.cjs");

test("appendAuditEvent rejects unknown type", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "ham-lc-audit-"));
  try {
    const r = appendAuditEvent({
      userDataPath: tmp,
      type: "evil_arbitrary",
      fs,
      path,
    });
    assert.equal(r.ok, false);
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("appendAuditEvent lines contain no path segments", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "ham-lc-audit2-"));
  const secret = "SECRET_PATH_MARKER_XYZ";
  try {
    const ud = path.join(tmp, secret);
    fs.mkdirSync(ud, { recursive: true });
    appendAuditEvent({
      userDataPath: ud,
      type: "local_control_status_read",
      fs,
      path,
    });
    const fp = eventsFilePath(ud, path);
    const line = fs.readFileSync(fp, "utf8").trim();
    assert.ok(!line.includes(secret));
    const row = JSON.parse(line);
    assert.equal(row.type, "local_control_status_read");
    assert.ok(typeof row.ts_iso === "string");
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("appendAuditEvent accepts sidecar lifecycle types", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "ham-lc-audit-sc-"));
  try {
    for (const t of [
      "local_control_sidecar_start_blocked",
      "local_control_sidecar_status_read",
      "local_control_sidecar_health_ping",
      "local_control_sidecar_stop",
    ]) {
      const r = appendAuditEvent({ userDataPath: tmp, type: t, fs, path });
      assert.equal(r.ok, true);
    }
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("appendAuditEvent accepts managed real-browser (4B) lifecycle types", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "ham-lc-audit-real-"));
  try {
    for (const t of [
      "local_control_real_browser_arm",
      "local_control_real_browser_start",
      "local_control_real_browser_start_blocked",
      "local_control_real_browser_navigate",
      "local_control_real_browser_navigate_blocked",
      "local_control_real_browser_reload",
      "local_control_real_browser_reload_blocked",
      "local_control_real_browser_screenshot",
      "local_control_real_browser_stop",
      "local_control_real_browser_error",
      "local_control_real_browser_observe_compact",
      "local_control_real_browser_wait",
      "local_control_real_browser_scroll",
      "local_control_real_browser_candidates",
      "local_control_real_browser_click_candidate",
      "local_control_real_browser_click_candidate_blocked",
      "local_control_real_browser_observe_compact_blocked",
      "local_control_real_browser_wait_blocked",
      "local_control_real_browser_scroll_blocked",
      "local_control_real_browser_candidates_blocked",
      "local_control_real_browser_click_candidate_gate_blocked",
    ]) {
      const r = appendAuditEvent({ userDataPath: tmp, type: t, fs, path });
      assert.equal(r.ok, true);
    }
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("appendAuditEvent accepts browser MVP lifecycle types", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "ham-lc-audit-br-"));
  try {
    for (const t of [
      "local_control_browser_arm",
      "local_control_browser_start",
      "local_control_browser_start_blocked",
      "local_control_browser_navigate",
      "local_control_browser_navigate_blocked",
      "local_control_browser_screenshot",
      "local_control_browser_stop",
      "local_control_browser_error",
      "local_control_kill_switch_disengaged_browser_mvp",
    ]) {
      const r = appendAuditEvent({ userDataPath: tmp, type: t, fs, path });
      assert.equal(r.ok, true);
    }
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});

test("getAuditStatus exposes redacted flag, no paths", () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "ham-lc-audit3-"));
  try {
    const st = getAuditStatus({ userDataPath: tmp, fs, path });
    assert.equal(st.redacted, true);
    const blob = JSON.stringify(st);
    assert.ok(!blob.includes(tmp));
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
