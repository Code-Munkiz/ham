"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const { validateNavigateUrl, safeDisplayUrl } = require("./local_control_browser_url.cjs");

test("validateNavigateUrl: http and https allowed", () => {
  const a = validateNavigateUrl("https://example.com/path?q=1", { allow_loopback: false });
  assert.equal(a.ok, true);
  if (a.ok) assert.ok(a.href.includes("example.com"));
});

test("validateNavigateUrl: rejects file javascript data chrome devtools", () => {
  for (const u of [
    "file:///etc/passwd",
    "javascript:alert(1)",
    "data:text/html,hi",
    "chrome://version",
    "devtools://foo",
  ]) {
    const r = validateNavigateUrl(u, { allow_loopback: true });
    assert.equal(r.ok, false, u);
  }
});

test("validateNavigateUrl: localhost blocked unless allowed", () => {
  const r = validateNavigateUrl("http://localhost:3000/", { allow_loopback: false });
  assert.equal(r.ok, false);
  assert.equal(r.error, "loopback_not_allowed");
  const r2 = validateNavigateUrl("http://localhost:3000/", { allow_loopback: true });
  assert.equal(r2.ok, true);
});

test("safeDisplayUrl strips query", () => {
  assert.equal(safeDisplayUrl("https://ex.test/a?token=secret"), "https://ex.test/a");
});
