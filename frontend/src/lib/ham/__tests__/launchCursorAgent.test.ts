/**
 * Launch must use hamApiFetch (Clerk session) like GET /api/cursor/credentials-status.
 * Raw fetch caused READY + 401 on hosted dashboard (missing Authorization).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { launchCursorAgent } from "@/lib/ham/api";

const ORIGINAL_FETCH = global.fetch;

beforeEach(() => {
  vi.stubEnv("VITE_HAM_API_BASE", "");
  vi.stubEnv("VITE_CLERK_PUBLISHABLE_KEY", "");
});

afterEach(() => {
  global.fetch = ORIGINAL_FETCH;
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("launchCursorAgent", () => {
  it("POSTs via the shared Ham API fetch path (same-origin /api/cursor/agents/launch)", async () => {
    global.fetch = vi.fn(async () => {
      return new Response(JSON.stringify({ id: "bc-smoke" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }) as typeof fetch;

    const out = await launchCursorAgent({
      prompt_text: " task ",
      repository: " https://github.com/o/r ",
      mission_handling: "managed",
      project_id: "project.one",
    });

    expect(out.id).toBe("bc-smoke");
    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, init] = (global.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit,
    ];
    expect(url).toBe("/api/cursor/agents/launch");
    expect(init.method).toBe("POST");
    expect(init.body).toContain("prompt_text");
    expect(init.body).toContain("mission_handling");
  });
});
