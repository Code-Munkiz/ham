import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import {
  fetchLocalWorkspaceHealth,
  resetLocalWorkspaceHealthBackoffForTests,
  setLocalRuntimeBase,
} from "../localRuntime";

describe("fetchLocalWorkspaceHealth backoff", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    localStorage.clear();
    resetLocalWorkspaceHealthBackoffForTests();
    setLocalRuntimeBase("http://127.0.0.1:9999");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    vi.useRealTimers();
    resetLocalWorkspaceHealthBackoffForTests();
    setLocalRuntimeBase(null);
    localStorage.clear();
  });

  it("suppresses repeats while local API refuses and clears after backoff elapses", async () => {
    const fetchSpy = vi.fn(async () =>
      Promise.reject(new TypeError("Failed to fetch (ECONNREFUSED)")),
    );
    vi.stubGlobal("fetch", fetchSpy);

    await expect(fetchLocalWorkspaceHealth()).resolves.toBeNull();
    await expect(fetchLocalWorkspaceHealth()).resolves.toBeNull();
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(5_500);
    await expect(fetchLocalWorkspaceHealth()).resolves.toBeNull();
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });

  it("successful health clears backoff for immediate follow-up probes", async () => {
    const payload = JSON.stringify({ ok: true, features: ["terminal"] });
    const fetchSpy = vi.fn(async () =>
      Promise.resolve({
        ok: true,
        status: 200,
        headers: new Headers({ "Content-Type": "application/json" }),
        json: async () => JSON.parse(payload) as unknown,
      } as Response),
    );
    vi.stubGlobal("fetch", fetchSpy);

    await expect(fetchLocalWorkspaceHealth()).resolves.not.toBeNull();
    await expect(fetchLocalWorkspaceHealth()).resolves.not.toBeNull();
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });
});
