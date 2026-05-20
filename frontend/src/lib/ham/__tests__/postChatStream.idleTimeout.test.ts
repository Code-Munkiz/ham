import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ham/clerkSession", () => ({
  clearClerkSessionTokenCache: () => {},
  getRegisteredClerkSessionToken: () => null,
}));

import { HamChatStreamIncompleteError, postChatStream, type HamChatRequest } from "@/lib/ham/api";

const ORIGINAL_FETCH = global.fetch;

/** Returns a Response whose body never emits any chunks. */
function neverResolvingNdjsonResponse(): Response {
  const stream = new ReadableStream<Uint8Array>({
    start() {
      // Intentionally do nothing: the reader will hang waiting forever.
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { "Content-Type": "application/x-ndjson" },
  });
}

describe("postChatStream idle timeout", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_HAM_API_BASE", "");
  });

  afterEach(() => {
    global.fetch = ORIGINAL_FETCH;
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("rejects with HamChatStreamIncompleteError when no NDJSON bytes arrive before the idle timeout", async () => {
    const fetchMock = vi.fn().mockResolvedValue(neverResolvingNdjsonResponse());
    global.fetch = fetchMock as unknown as typeof fetch;

    const payload: HamChatRequest = {
      messages: [{ role: "user", content: "ping" }],
    };

    await expect(
      postChatStream(payload, {}, undefined, { idleTimeoutMs: 50 }),
    ).rejects.toBeInstanceOf(HamChatStreamIncompleteError);
  });

  it("propagates the session id on the rejected error when the server emitted ``session`` before hanging", async () => {
    const sessionLine = JSON.stringify({ type: "session", session_id: "sess_idle_check" }) + "\n";
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode(sessionLine));
        // Then go silent — the idle timer should still fire.
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(stream, {
        status: 200,
        headers: { "Content-Type": "application/x-ndjson" },
      }),
    );
    global.fetch = fetchMock as unknown as typeof fetch;

    const payload: HamChatRequest = {
      messages: [{ role: "user", content: "ping" }],
    };

    try {
      await postChatStream(payload, {}, undefined, { idleTimeoutMs: 50 });
      throw new Error("postChatStream should have rejected on idle timeout");
    } catch (cause) {
      expect(cause).toBeInstanceOf(HamChatStreamIncompleteError);
      if (cause instanceof HamChatStreamIncompleteError) {
        expect(cause.streamSessionId).toBe("sess_idle_check");
      }
    }
  });
});
