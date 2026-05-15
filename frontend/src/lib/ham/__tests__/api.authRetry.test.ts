import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { clearClerkSessionTokenCacheMock, getRegisteredClerkSessionTokenMock } = vi.hoisted(() => ({
  clearClerkSessionTokenCacheMock: vi.fn(),
  getRegisteredClerkSessionTokenMock: vi.fn(),
}));

vi.mock("@/lib/ham/clerkSession", () => ({
  clearClerkSessionTokenCache: () => clearClerkSessionTokenCacheMock(),
  getRegisteredClerkSessionToken: (opts?: { forceRefresh?: boolean }) =>
    getRegisteredClerkSessionTokenMock(opts),
}));

import { hamApiFetch } from "@/lib/ham/api";

const ORIGINAL_FETCH = global.fetch;
const ORIGINAL_SET_TIMEOUT = global.setTimeout;

describe("hamApiFetch auth retry", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_HAM_API_BASE", "");
    vi.stubEnv("VITE_CLERK_PUBLISHABLE_KEY", "pk_test_mock");
    global.setTimeout = ((cb: TimerHandler) => {
      if (typeof cb === "function") cb();
      return 0 as unknown as ReturnType<typeof setTimeout>;
    }) as typeof setTimeout;
  });

  afterEach(() => {
    global.fetch = ORIGINAL_FETCH;
    global.setTimeout = ORIGINAL_SET_TIMEOUT;
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("retries once after a 401 and keeps auth in headers", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("unauthorized", { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    global.fetch = fetchMock as unknown as typeof fetch;
    getRegisteredClerkSessionTokenMock.mockResolvedValue("clerk_jwt_mock");

    const res = await hamApiFetch("/api/workspace/tools");
    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(2);

    const calls = fetchMock.mock.calls as Array<[string, RequestInit]>;
    expect(calls[0]?.[0]).toBe("/api/workspace/tools");
    expect(calls[1]?.[0]).toBe("/api/workspace/tools");
    expect(String(calls[0]?.[0])).not.toContain("token=");
    expect(String(calls[1]?.[0])).not.toContain("token=");
    expect(calls[0]?.[1]?.credentials).toBe("include");
    expect(calls[1]?.[1]?.credentials).toBe("include");

    const firstHeaders = calls[0]?.[1]?.headers as Headers;
    const secondHeaders = calls[1]?.[1]?.headers as Headers;
    expect(firstHeaders.get("Authorization")).toBe("Bearer clerk_jwt_mock");
    expect(secondHeaders.get("Authorization")).toBe("Bearer clerk_jwt_mock");
    expect(getRegisteredClerkSessionTokenMock).toHaveBeenNthCalledWith(1, { forceRefresh: false });
    expect(getRegisteredClerkSessionTokenMock).toHaveBeenNthCalledWith(2, { forceRefresh: true });
    expect(clearClerkSessionTokenCacheMock).toHaveBeenCalledTimes(1);
  });
});
