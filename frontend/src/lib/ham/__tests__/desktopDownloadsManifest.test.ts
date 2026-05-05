/**
 * Phase C.1 baseline test: the desktop downloads manifest parser is a
 * trust-boundary function (validates fetched JSON before it reaches
 * landing-page CTAs), so we lock its happy/sad paths here.
 *
 * Pure data in, pure data out. No DOM, no fetch.
 */
import { describe, expect, it } from "vitest";
import {
  manifestToDownloadCtas,
  parseDesktopDownloadsManifest,
  type DesktopDownloadsManifest,
} from "@/lib/ham/desktopDownloadsManifest";

const VALID_HTTPS_URL =
  "https://example.invalid/ham-desktop-1.0.0.AppImage";

function validManifest(): DesktopDownloadsManifest {
  return {
    schema_version: 1,
    channel: "stable",
    distribution: "github",
    summary: "v1.0.0",
    platforms: {
      linux: {
        label: "Linux AppImage",
        arch: "x86_64",
        type: "AppImage",
        version: "1.0.0",
        url: VALID_HTTPS_URL,
        sha256: "abc123",
        release_page_url: "https://example.invalid/releases/v1.0.0",
      },
      windows: null,
      macos: null,
    },
  };
}

describe("parseDesktopDownloadsManifest", () => {
  it("returns null for non-object input", () => {
    expect(parseDesktopDownloadsManifest(null)).toBeNull();
    expect(parseDesktopDownloadsManifest("nope")).toBeNull();
    expect(parseDesktopDownloadsManifest(42)).toBeNull();
  });

  it("returns null when schema_version is not 1", () => {
    expect(
      parseDesktopDownloadsManifest({
        schema_version: 2,
        channel: "stable",
        distribution: "github",
        platforms: {},
      }),
    ).toBeNull();
  });

  it("returns null when required string fields are missing", () => {
    expect(
      parseDesktopDownloadsManifest({
        schema_version: 1,
        channel: "stable",
        platforms: {},
      }),
    ).toBeNull();
  });

  it("returns null when a platform entry has a non-https url", () => {
    const out = parseDesktopDownloadsManifest({
      ...validManifest(),
      platforms: {
        linux: {
          label: "Linux",
          arch: "x86_64",
          type: "AppImage",
          version: "1.0.0",
          url: "ftp://example.invalid/bad",
        },
      },
    });
    expect(out).toBeNull();
  });

  it("parses a valid manifest and preserves the typed shape", () => {
    const out = parseDesktopDownloadsManifest(validManifest());
    expect(out).not.toBeNull();
    expect(out?.schema_version).toBe(1);
    expect(out?.channel).toBe("stable");
    expect(out?.distribution).toBe("github");
    expect(out?.platforms.linux?.url).toBe(VALID_HTTPS_URL);
    expect(out?.platforms.windows).toBeNull();
    expect(out?.platforms.macos).toBeNull();
  });
});

describe("manifestToDownloadCtas", () => {
  it("emits only Windows and macOS CTAs in stable order (Linux omitted)", () => {
    const ctas = manifestToDownloadCtas(validManifest());
    expect(ctas.map((c) => c.platform)).toEqual(["windows", "macos"]);
  });

  it("marks Windows/macOS availability from manifest; ignores Linux for CTAs", () => {
    const ctas = manifestToDownloadCtas(validManifest());
    const byPlatform = Object.fromEntries(ctas.map((c) => [c.platform, c]));
    expect(byPlatform.windows.available).toBe(false);
    expect(byPlatform.windows.href).toBe("");
    expect(byPlatform.macos.available).toBe(false);
    expect(byPlatform.macos.href).toBe("");
    expect(ctas.find((c) => c.platform === "linux")).toBeUndefined();
  });

  it("propagates sha256 as checksumHex on available Windows CTA", () => {
    const ctas = manifestToDownloadCtas({
      ...validManifest(),
      platforms: {
        linux: null,
        macos: null,
        windows: {
          label: "Windows",
          arch: "x64",
          type: "Portable",
          version: "1.0.0",
          url: VALID_HTTPS_URL,
          sha256: "abc123",
        },
      },
    });
    const win = ctas.find((c) => c.platform === "windows");
    expect(win?.available).toBe(true);
    expect(win?.checksumHex).toBe("abc123");
  });
});
