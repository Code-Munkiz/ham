"use strict";

const { describe, it, afterEach } = require("node:test");
const assert = require("node:assert/strict");

const {
  semverGt,
  semverCmp,
  parseSemverToken,
  parseDownloadsManifest,
  isTrustedManifestURL,
  electronPlatformKey,
  manifestUrlFromEnv,
} = require("./desktop_updates.cjs");

describe("desktop_updates semver", () => {
  it("compares semver parts", () => {
    assert.equal(semverGt("0.1.4", "0.1.3"), true);
    assert.equal(semverGt("0.1.4", "0.1.4"), false);
    assert.equal(semverGt("0.1.3", "0.1.4"), false);
    assert.equal(semverGt("0.1.10", "0.1.9"), true);
    assert.strictEqual(parseSemverToken("bogus"), null);
    assert.strictEqual(semverCmp("bad", "0.1.0"), null);
  });
});

describe("desktop_updates manifest parsing", () => {
  const good = {
    schema_version: 1,
    channel: "internal",
    distribution: "unsigned_internal",
    platforms: {
      linux: null,
      windows: {
        label: "Windows",
        arch: "x64",
        type: "Portable",
        version: "0.1.10",
        url: "https://github.com/Code-Munkiz/ham/releases/download/foo/bar.exe",
        sha256: "abc",
        release_page_url: "https://github.com/Code-Munkiz/ham/releases/tag/foo",
      },
      macos: null,
    },
  };

  it("accepts canonical shape with nullable platforms", () => {
    const p = parseDownloadsManifest(structuredClone(good));
    assert.ok(p);
    assert.equal(p.platforms.windows.version, "0.1.10");
    assert.equal(p.platforms.linux, null);
    assert.equal(p.platforms.macos, null);
  });

  it("preserves parser-level acceptance of a populated linux entry for forward compat", () => {
    const j = structuredClone(good);
    j.platforms.linux = {
      label: "Linux",
      arch: "x64",
      type: "AppImage",
      version: "0.1.4",
      url: "https://github.com/Code-Munkiz/ham/releases/download/foo/bar.AppImage",
    };
    const p = parseDownloadsManifest(j);
    assert.ok(p);
    assert.equal(p.platforms.linux.version, "0.1.4");
  });

  it("rejects bad url scheme", () => {
    const j = structuredClone(good);
    j.platforms.windows.url = "http://insecure/";
    assert.equal(parseDownloadsManifest(j), null);
  });

  it("rejects missing schema", () => {
    assert.equal(parseDownloadsManifest({}), null);
  });
});

describe("desktop_updates trust URLs", () => {
  const orig = process.env.HAM_DESKTOP_DOWNLOADS_MANIFEST_URL;
  afterEach(() => {
    if (orig === undefined) delete process.env.HAM_DESKTOP_DOWNLOADS_MANIFEST_URL;
    else process.env.HAM_DESKTOP_DOWNLOADS_MANIFEST_URL = orig;
  });

  it("trusts canonical raw GH path", () => {
    assert.ok(
      isTrustedManifestURL(
        "https://raw.githubusercontent.com/Code-Munkiz/ham/main/frontend/public/desktop-downloads.json",
      ),
    );
    assert.equal(isTrustedManifestURL("https://evil.com/desktop-downloads.json"), false);
  });

  it("manifestUrlFromEnv default", () => {
    delete process.env.HAM_DESKTOP_DOWNLOADS_MANIFEST_URL;
    const u = manifestUrlFromEnv();
    assert.ok(String(u).includes("desktop-downloads.json"));
  });
});

describe("electronPlatformKey sanity", () => {
  const orig = process.platform;
  function setPlatform(p) {
    Object.defineProperty(process, "platform", { value: p, configurable: true });
  }
  afterEach(() => {
    Object.defineProperty(process, "platform", { value: orig, configurable: true });
  });

  it("maps win32 → windows", () => {
    setPlatform("win32");
    assert.equal(electronPlatformKey(), "windows");
  });

  it("maps darwin → macos", () => {
    setPlatform("darwin");
    assert.equal(electronPlatformKey(), "macos");
  });

  it("returns null on linux (no Linux update prompt)", () => {
    setPlatform("linux");
    assert.equal(electronPlatformKey(), null);
  });

  it("returns null on unknown platforms", () => {
    setPlatform("freebsd");
    assert.equal(electronPlatformKey(), null);
  });
});
