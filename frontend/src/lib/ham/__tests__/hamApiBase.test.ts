import { describe, expect, it } from "vitest";

import * as hamApi from "@/lib/ham/api";

const { buildHamApiStatusUrl, getHamApiOriginLabel, resolveHamApiBase } = hamApi;

describe("resolveHamApiBase", () => {
  it("prefers desktop apiBase", () => {
    expect(
      resolveHamApiBase({
        desktopApiBase: "https://desktop-api.example.com",
        viteHamApiBase: "https://vite.example.com",
        hostname: "ham-nine-mu.vercel.app",
        isDev: false,
      }),
    ).toBe("https://desktop-api.example.com");
  });

  it("forces same-origin on Vercel hosts even when VITE would point elsewhere", () => {
    expect(
      resolveHamApiBase({
        viteHamApiBase: "https://ham-api-xxxxx.run.app",
        hostname: "ham-nine-mu.vercel.app",
        isDev: false,
      }),
    ).toBe("");
    expect(
      resolveHamApiBase({
        viteHamApiBase: "https://ham-api-xxxxx.run.app",
        hostname: "some-branch-my-team.vercel.app",
        isDev: false,
      }),
    ).toBe("");
  });

  it("uses VITE base off Vercel when hostname is not vercel.app", () => {
    expect(
      resolveHamApiBase({
        viteHamApiBase: "https://ham-api-xxxxx.run.app",
        hostname: "localhost",
        isDev: false,
      }),
    ).toBe("https://ham-api-xxxxx.run.app");
  });

  it("normalizes trailing slashes and stray /api suffix on vite base", () => {
    expect(
      resolveHamApiBase({
        viteHamApiBase: "https://example.com/",
        hostname: "localhost",
        isDev: false,
      }),
    ).toBe("https://example.com");
    expect(
      resolveHamApiBase({
        viteHamApiBase: "https://example.com/api",
        hostname: "localhost",
        isDev: false,
      }),
    ).toBe("https://example.com");
  });

  it("returns empty same-origin base when vite unset off Vercel (static prod)", () => {
    expect(
      resolveHamApiBase({
        hostname: "cdn.example.com",
        isDev: false,
      }),
    ).toBe("");
  });

  it("returns empty in dev when vite unset regardless of hostname", () => {
    expect(
      resolveHamApiBase({
        hostname: "localhost",
        isDev: true,
      }),
    ).toBe("");
  });
});

describe("same-origin diagnostics URLs", () => {
  it("getHamApiOriginLabel ends with /api when same-origin routing", () => {
    expect(getHamApiOriginLabel()).toMatch(/\/api$/);
  });

  it("buildHamApiStatusUrl ends with /api/status when same-origin routing", () => {
    expect(buildHamApiStatusUrl()).toMatch(/\/api\/status$/);
  });
});
