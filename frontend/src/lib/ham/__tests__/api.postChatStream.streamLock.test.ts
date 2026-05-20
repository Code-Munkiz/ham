import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CHAT_STREAM_ALREADY_ACTIVE_USER_MESSAGE,
  HamChatStreamAlreadyActiveError,
  postChatStream,
  type HamChatRequest,
} from "@/lib/ham/api";

const ORIGINAL_FETCH = global.fetch;

describe("postChatStream STREAM_ALREADY_ACTIVE", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_HAM_API_BASE", "");
    vi.stubEnv("VITE_CLERK_PUBLISHABLE_KEY", "");
  });

  afterEach(() => {
    global.fetch = ORIGINAL_FETCH;
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("throws HamChatStreamAlreadyActiveError with the intended user message on HTTP 409", async () => {
    global.fetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            error: {
              code: "STREAM_ALREADY_ACTIVE",
              message: "A stream is already active for this session.",
              retry_after_ms: 4500,
              lock_age_sec: 12.5,
            },
          },
        }),
        {
          status: 409,
          headers: { "Content-Type": "application/json" },
        },
      ),
    ) as unknown as typeof fetch;

    const payload: HamChatRequest = {
      messages: [{ role: "user", content: "hi" }],
    };

    await expect(postChatStream(payload)).rejects.toSatisfy((err: unknown) => {
      expect(err).toBeInstanceOf(HamChatStreamAlreadyActiveError);
      const active = err as HamChatStreamAlreadyActiveError;
      expect(active.message).toBe(CHAT_STREAM_ALREADY_ACTIVE_USER_MESSAGE);
      expect(active.retryAfterMs).toBe(4500);
      expect(active.lockAgeSec).toBe(12.5);
      return true;
    });
    expect(global.fetch).toHaveBeenCalledTimes(1);
  });
});
