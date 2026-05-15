import { afterEach, describe, expect, it, vi } from "vitest";
import {
  clearClerkSessionTokenCache,
  getRegisteredClerkSessionToken,
  registerClerkSessionGetter,
} from "@/lib/ham/clerkSession";

describe("clerkSession token caching and single-flight", () => {
  afterEach(() => {
    clearClerkSessionTokenCache();
    registerClerkSessionGetter(null);
    vi.restoreAllMocks();
  });

  it("reuses one in-flight token request for concurrent callers", async () => {
    let resolveToken: ((value: string | null) => void) | null = null;
    const getter = vi.fn(
      () =>
        new Promise<string | null>((resolve) => {
          resolveToken = resolve;
        }),
    );
    registerClerkSessionGetter(getter);

    const p1 = getRegisteredClerkSessionToken();
    const p2 = getRegisteredClerkSessionToken();
    const p3 = getRegisteredClerkSessionToken();

    expect(getter).toHaveBeenCalledTimes(1);
    resolveToken?.("jwt_shared");
    await expect(Promise.all([p1, p2, p3])).resolves.toEqual([
      "jwt_shared",
      "jwt_shared",
      "jwt_shared",
    ]);
    expect(getter).toHaveBeenCalledTimes(1);
  });

  it("uses cached token on sequential calls inside TTL", async () => {
    const getter = vi.fn().mockResolvedValue("jwt_cached");
    registerClerkSessionGetter(getter);

    await expect(getRegisteredClerkSessionToken()).resolves.toBe("jwt_cached");
    await expect(getRegisteredClerkSessionToken()).resolves.toBe("jwt_cached");
    expect(getter).toHaveBeenCalledTimes(1);
  });

  it("forceRefresh bypasses cache and fetches a fresh token", async () => {
    const getter = vi.fn().mockResolvedValueOnce("jwt_first").mockResolvedValueOnce("jwt_second");
    registerClerkSessionGetter(getter);

    await expect(getRegisteredClerkSessionToken()).resolves.toBe("jwt_first");
    await expect(getRegisteredClerkSessionToken({ forceRefresh: true })).resolves.toBe(
      "jwt_second",
    );
    expect(getter).toHaveBeenCalledTimes(2);
  });
});
