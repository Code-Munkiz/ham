import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { waitFor } from "@testing-library/react";

const clearClerkCache = vi.fn();
const getRegisteredClerkSessionTokenMock = vi.fn();

vi.mock("@/lib/ham/clerkSession", () => ({
  clearClerkSessionTokenCache: () => clearClerkCache(),
  getRegisteredClerkSessionToken: (opts?: { forceRefresh?: boolean }) =>
    getRegisteredClerkSessionTokenMock(opts),
}));

import { subscribeBuilderActivityStream } from "@/lib/ham/api";

const ORIGINAL_FETCH = global.fetch;
const ORIGINAL_SET_TIMEOUT = global.setTimeout;

function json401StaleClerk() {
  return new Response(
    JSON.stringify({
      detail: {
        error: {
          code: "CLERK_SESSION_INVALID",
          message: "Invalid Clerk session: Signature has expired",
        },
      },
    }),
    { status: 401, headers: { "Content-Type": "application/json" } },
  );
}

function sseDoneStream() {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode("event: done\ndata: {}\n\n"));
      controller.close();
    },
  });
}

describe("subscribeBuilderActivityStream Clerk stale-session retry", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_HAM_API_BASE", "");
    vi.stubEnv("VITE_CLERK_PUBLISHABLE_KEY", "pk_test_mock");
    clearClerkCache.mockClear();
    getRegisteredClerkSessionTokenMock.mockReset();
    global.setTimeout = ORIGINAL_SET_TIMEOUT;
  });

  afterEach(() => {
    global.fetch = ORIGINAL_FETCH;
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("refreshes Clerk token once on CLERK_SESSION_INVALID then opens the stream", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json401StaleClerk())
      .mockResolvedValueOnce(
        new Response(sseDoneStream(), {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        }),
      );
    global.fetch = fetchMock as unknown as typeof fetch;
    getRegisteredClerkSessionTokenMock.mockResolvedValue("clerk_jwt_mock");

    const onOpen = vi.fn();
    const sub = subscribeBuilderActivityStream("ws1", "p1", {
      onOpen,
      onActivity: vi.fn(),
    });

    await waitFor(() => expect(onOpen).toHaveBeenCalledTimes(1), { timeout: 4000 });
    sub.close();

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(clearClerkCache).toHaveBeenCalledTimes(1);
    expect(getRegisteredClerkSessionTokenMock.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(getRegisteredClerkSessionTokenMock.mock.calls.at(-1)?.[0]).toEqual({
      forceRefresh: true,
    });
  });
});
