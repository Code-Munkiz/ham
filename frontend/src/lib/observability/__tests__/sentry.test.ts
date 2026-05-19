/**
 * Tests for src/lib/observability/sentry.ts — Phase 1 #9 (ADR-0008).
 *
 * DSN-unset behaviour: init() must be a no-op; isActive() must return false.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@sentry/react", () => ({
  init: vi.fn(),
  browserTracingIntegration: vi.fn(() => ({})),
}));

import * as SentryMock from "@sentry/react";

// Obviously-fake placeholder — Sentry.init is mocked so format does not matter.
const FAKE_DSN = "sentry-dsn-placeholder-for-tests";

afterEach(() => {
  vi.resetAllMocks();
  vi.unstubAllEnvs();
});

describe("init — DSN unset", () => {
  it("does not call Sentry.init when VITE_SENTRY_DSN is absent", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "");
    const { init, resetForTests } = await import("../sentry");
    resetForTests();
    init();
    expect(SentryMock.init).not.toHaveBeenCalled();
    resetForTests();
  });

  it("isActive returns false when DSN is unset", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", "");
    const { init, isActive, resetForTests } = await import("../sentry");
    resetForTests();
    init();
    expect(isActive()).toBe(false);
    resetForTests();
  });
});

describe("init — DSN set", () => {
  it("calls Sentry.init and marks active", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", FAKE_DSN);
    const { init, isActive, resetForTests } = await import("../sentry");
    resetForTests();
    init();
    expect(SentryMock.init).toHaveBeenCalledOnce();
    expect(isActive()).toBe(true);
    resetForTests();
  });

  it("tracesSampleRate is 0 by default", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", FAKE_DSN);
    const { init, resetForTests } = await import("../sentry");
    resetForTests();
    init();
    const callArgs = vi.mocked(SentryMock.init).mock.calls[0][0] as Record<string, unknown>;
    expect(callArgs.tracesSampleRate).toBe(0);
    resetForTests();
  });

  it("second init call is idempotent", async () => {
    vi.stubEnv("VITE_SENTRY_DSN", FAKE_DSN);
    const { init, resetForTests } = await import("../sentry");
    resetForTests();
    init();
    init();
    expect(SentryMock.init).toHaveBeenCalledOnce();
    resetForTests();
  });
});
