import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { previewCodingConductor } from "@/lib/ham/api";

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

describe("previewCodingConductor", () => {
  it("POSTs to /api/coding/conductor/preview with trimmed body", async () => {
    global.fetch = vi.fn(async () => {
      return new Response(
        JSON.stringify({
          kind: "coding_conductor_preview",
          preview_id: "p-1",
          task_kind: "audit",
          task_confidence: 0.85,
          chosen: null,
          candidates: [],
          blockers: [],
          recommendation_reason: "x",
          requires_approval: false,
          approval_kind: "none",
          project: {
            found: false,
            project_id: null,
            build_lane_enabled: false,
            has_github_repo: false,
          },
          is_operator: false,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }) as typeof fetch;

    const out = await previewCodingConductor({
      user_prompt: "  Audit the API.  ",
      project_id: "  proj.alpha  ",
      preferred_provider: "factory_droid_audit",
      workspace_id: "  ws_beta  ",
    });

    expect(out.kind).toBe("coding_conductor_preview");
    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, init] = (global.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0] as [
      string,
      RequestInit,
    ];
    expect(url).toBe("/api/coding/conductor/preview");
    expect(init.method).toBe("POST");
    const body = JSON.parse(String(init.body));
    expect(body).toEqual({
      user_prompt: "Audit the API.",
      project_id: "proj.alpha",
      preferred_provider: "factory_droid_audit",
      workspace_id: "ws_beta",
    });
  });

  it("omits empty optional fields", async () => {
    global.fetch = vi.fn(async () => {
      return new Response(
        JSON.stringify({
          kind: "coding_conductor_preview",
          preview_id: "p-2",
          task_kind: "explain",
          task_confidence: 0.9,
          chosen: null,
          candidates: [],
          blockers: [],
          recommendation_reason: "x",
          requires_approval: false,
          approval_kind: "none",
          project: {
            found: false,
            project_id: null,
            build_lane_enabled: false,
            has_github_repo: false,
          },
          is_operator: false,
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    }) as typeof fetch;

    await previewCodingConductor({ user_prompt: "Explain things." });

    const init = (global.fetch as unknown as ReturnType<typeof vi.fn>).mock
      .calls[0][1] as RequestInit;
    const body = JSON.parse(String(init.body));
    expect(body).toEqual({ user_prompt: "Explain things." });
    expect(body).not.toHaveProperty("project_id");
    expect(body).not.toHaveProperty("preferred_provider");
    expect(body).not.toHaveProperty("workspace_id");
  });

  it("includes workspace_id when provided and omits it when null/empty", async () => {
    const mockResponse = {
      kind: "coding_conductor_preview",
      preview_id: "p-3",
      task_kind: "explain",
      task_confidence: 0.9,
      chosen: null,
      candidates: [],
      blockers: [],
      recommendation_reason: "x",
      requires_approval: false,
      approval_kind: "none",
      project: {
        found: false,
        project_id: null,
        build_lane_enabled: false,
        has_github_repo: false,
      },
      is_operator: false,
    };
    global.fetch = vi.fn(async () => {
      return new Response(JSON.stringify(mockResponse), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }) as typeof fetch;

    await previewCodingConductor({ user_prompt: "Explain things.", workspace_id: "ws_gamma" });
    const body1 = JSON.parse(
      String(
        ((global.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1] as RequestInit)
          .body,
      ),
    );
    expect(body1.workspace_id).toBe("ws_gamma");

    (global.fetch as unknown as ReturnType<typeof vi.fn>).mockClear();
    await previewCodingConductor({ user_prompt: "Explain things.", workspace_id: null });
    const body2 = JSON.parse(
      String(
        ((global.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1] as RequestInit)
          .body,
      ),
    );
    expect(body2).not.toHaveProperty("workspace_id");
  });

  it("rethrows server detail messages on non-200", async () => {
    global.fetch = vi.fn(async () => {
      return new Response(
        JSON.stringify({
          detail: { error: { code: "CLERK_SESSION_REQUIRED", message: "Auth required" } },
        }),
        { status: 401, headers: { "content-type": "application/json" } },
      );
    }) as typeof fetch;

    await expect(previewCodingConductor({ user_prompt: "Audit the API." })).rejects.toThrow(
      /Auth required/,
    );
  });
});
