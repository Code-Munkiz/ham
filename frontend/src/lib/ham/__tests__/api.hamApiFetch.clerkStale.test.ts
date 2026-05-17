import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const clearCache = vi.fn();
const getToken = vi.fn();

vi.mock("@/lib/ham/clerkSession", () => ({
  clearClerkSessionTokenCache: () => clearCache(),
  getRegisteredClerkSessionToken: (opts?: { forceRefresh?: boolean }) => getToken(opts),
}));

import { hamApiFetch } from "@/lib/ham/api";

const ORIGINAL_FETCH = global.fetch;

describe("hamApiFetch stale Clerk-session retry surface", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_CLERK_PUBLISHABLE_KEY", "pk_test_mock");
    vi.stubEnv("VITE_HAM_API_BASE", "");
    clearCache.mockClear();
    getToken.mockReset();
    getToken.mockResolvedValue("jwt_refresh");
    global.fetch = ORIGINAL_FETCH;
  });

  afterEach(() => {
    global.fetch = ORIGINAL_FETCH;
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("does not retry POST on generic 401 (no Clerk stale signals)", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: "nope" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    );
    global.fetch = fetchMock as unknown as typeof fetch;
    const unauthorized = await hamApiFetch("/api/workspace/tools/connect", { method: "POST" });
    expect(unauthorized.status).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(clearCache).not.toHaveBeenCalled();
  });

  it("retries POST once after CLERK_SESSION_INVALID structured error", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            detail: { error: { code: "CLERK_SESSION_INVALID", message: "Signature has expired" } },
          }),
          {
            status: 401,
            headers: { "Content-Type": "application/json" },
          },
        ),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    global.fetch = fetchMock as unknown as typeof fetch;

    const authorized = await hamApiFetch("/api/workspace/tools/connect", { method: "POST" });
    expect(authorized.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(clearCache).toHaveBeenCalled();
    expect(getToken).toHaveBeenCalledWith({ forceRefresh: true });
  });
});
