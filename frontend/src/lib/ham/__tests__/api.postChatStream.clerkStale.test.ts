import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { waitFor } from "@testing-library/react";

const clearCache = vi.fn();
const getToken = vi.fn();

vi.mock("@/lib/ham/clerkSession", () => ({
  clearClerkSessionTokenCache: () => clearCache(),
  getRegisteredClerkSessionToken: (opts?: { forceRefresh?: boolean }) => getToken(opts),
}));

import { postChatStream, type HamChatRequest } from "@/lib/ham/api";

const ORIGINAL_FETCH = global.fetch;
const ORIGINAL_SET_TIMEOUT = global.setTimeout;

function ndjsonDoneStream(sessionId = "sess_x") {
  const line = `${JSON.stringify({ type: "done", session_id: sessionId, messages: [] })}\n`;
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode(line));
      controller.close();
    },
  });
}

describe("postChatStream Clerk stale-session retry", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_HAM_API_BASE", "");
    vi.stubEnv("VITE_CLERK_PUBLISHABLE_KEY", "pk_test_mock");
    clearCache.mockClear();
    getToken.mockReset();
    global.setTimeout = ORIGINAL_SET_TIMEOUT;
  });

  afterEach(() => {
    global.fetch = ORIGINAL_FETCH;
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("forces a Clerk token refresh on CLERK_SESSION_INVALID and retries POST once", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            detail: {
              error: {
                code: "CLERK_SESSION_INVALID",
                message: "Invalid Clerk session: Signature has expired",
              },
            },
          }),
          {
            status: 401,
            headers: { "Content-Type": "application/json" },
          },
        ),
      )
      .mockResolvedValueOnce(
        new Response(ndjsonDoneStream(), {
          status: 200,
          headers: { "Content-Type": "application/x-ndjson" },
        }),
      );
    global.fetch = fetchMock as unknown as typeof fetch;
    getToken.mockResolvedValue("jwt_refreshed");

    const payload: HamChatRequest = {
      messages: [{ role: "user", content: "hi" }],
    };

    await postChatStream(payload, {}, { sessionToken: "jwt_stale" });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(clearCache).toHaveBeenCalledTimes(1);
    expect(getToken).toHaveBeenCalledTimes(1);
    expect(getToken).toHaveBeenCalledWith({ forceRefresh: true });
    const secondHeaders = fetchMock.mock.calls[1]?.[1]?.headers as Record<string, string>;
    expect(secondHeaders.Authorization).toBe("Bearer jwt_refreshed");
  });

  it("does not retry for string-only Bearer auth payloads", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            error: {
              code: "CLERK_SESSION_INVALID",
              message: "Invalid Clerk session: Signature has expired",
            },
          },
        }),
        { status: 401, headers: { "Content-Type": "application/json" } },
      ),
    );
    global.fetch = fetchMock as unknown as typeof fetch;
    getToken.mockResolvedValue("jwt");

    const payload: HamChatRequest = {
      messages: [{ role: "user", content: "hi" }],
    };

    await expect(postChatStream(payload, {}, "Bearer legacy")).rejects.toThrow(/Signature has expired/);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    expect(getToken).not.toHaveBeenCalled();
  });
});
