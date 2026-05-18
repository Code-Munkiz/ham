import { afterEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/ham/api";
import {
  builderStudioAdapter,
  type BuilderDraft,
  type BuilderPublic,
} from "@/features/hermes-workspace/adapters/builderStudioAdapter";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function emptyResponse(status: number, body: unknown = { detail: "" }): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function draft(overrides: Partial<BuilderDraft> = {}): BuilderDraft {
  return {
    builder_id: "game-builder",
    workspace_id: "ws_abc",
    name: "Game Builder",
    description: "Small 2D games.",
    intent_tags: ["games"],
    task_kinds: ["feature"],
    permission_preset: "game_build",
    allowed_paths: [],
    denied_paths: [],
    denied_operations: [],
    review_mode: "always",
    deletion_policy: "require_review",
    external_network_policy: "deny",
    model_source: "ham_default",
    model_ref: null,
    enabled: true,
    ...overrides,
  };
}

function fakeBuilder(overrides: Partial<BuilderPublic> = {}): BuilderPublic {
  return {
    ...draft(),
    created_at: "2026-05-17T10:00:00Z",
    updated_at: "2026-05-17T10:00:00Z",
    updated_by: "user_1",
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("builderStudioAdapter.list", () => {
  it("returns builders on a 200 happy path", async () => {
    vi.spyOn(api, "hamApiFetch").mockResolvedValue(jsonResponse({ builders: [fakeBuilder()] }));
    const { builders, error } = await builderStudioAdapter.list("ws_abc");
    expect(error).toBeUndefined();
    expect(builders).toHaveLength(1);
    expect(builders[0].builder_id).toBe("game-builder");
  });

  it("returns feature_disabled error on 503 with CUSTOM_BUILDER_FEATURE_DISABLED", async () => {
    vi.spyOn(api, "hamApiFetch").mockResolvedValue(
      emptyResponse(503, { detail: "CUSTOM_BUILDER_FEATURE_DISABLED" }),
    );
    const { builders, error } = await builderStudioAdapter.list("ws_abc");
    expect(builders).toEqual([]);
    expect(error).toEqual({ kind: "feature_disabled" });
  });

  it("returns unavailable error on 503 without feature flag body", async () => {
    vi.spyOn(api, "hamApiFetch").mockResolvedValue(emptyResponse(503, { detail: "service down" }));
    const { error } = await builderStudioAdapter.list("ws_abc");
    expect(error?.kind).toBe("unavailable");
  });

  it("returns builders_list_not_found error on list 404 (distinct from single-builder not_found)", async () => {
    vi.spyOn(api, "hamApiFetch").mockResolvedValue(emptyResponse(404, { detail: "nope" }));
    const { builders, error } = await builderStudioAdapter.list("ws_abc");
    expect(builders).toEqual([]);
    expect(error).toEqual({ kind: "builders_list_not_found" });
  });

  it("wraps thrown network errors instead of re-throwing", async () => {
    vi.spyOn(api, "hamApiFetch").mockRejectedValue(new Error("network down"));
    const { builders, error } = await builderStudioAdapter.list("ws_abc");
    expect(builders).toEqual([]);
    expect(error?.kind).toBe("unknown");
  });
});

describe("builderStudioAdapter.create", () => {
  it("returns validation copy on 422 (normie-safe; no raw HTTP)", async () => {
    vi.spyOn(api, "hamApiFetch").mockResolvedValue(emptyResponse(422, { detail: "validation" }));
    const { builder, error } = await builderStudioAdapter.create("ws_abc", draft());
    expect(builder).toBeNull();
    expect(error?.kind).toBe("validation");
    if (error?.kind === "validation") {
      expect(error.message.toLowerCase()).not.toContain("422");
      expect(error.message.toLowerCase()).not.toContain("http");
    }
  });

  it("POST create body omits workspace_id", async () => {
    const fetchSpy = vi
      .spyOn(api, "hamApiFetch")
      .mockResolvedValue(jsonResponse({ builder: fakeBuilder() }));
    await builderStudioAdapter.create("ws_abc", draft());
    const init = fetchSpy.mock.calls[0][1] as RequestInit;
    const posted = JSON.parse(String(init.body));
    expect(posted).not.toHaveProperty("workspace_id");
    expect(posted.name).toBe("Game Builder");
  });

  it("returns duplicate error on 409", async () => {
    vi.spyOn(api, "hamApiFetch").mockResolvedValue(emptyResponse(409, { detail: "exists" }));
    const { error } = await builderStudioAdapter.create("ws_abc", draft());
    expect(error?.kind).toBe("duplicate");
  });

  it("returns builder on 200 happy path", async () => {
    vi.spyOn(api, "hamApiFetch").mockResolvedValue(jsonResponse({ builder: fakeBuilder() }));
    const { builder, error } = await builderStudioAdapter.create("ws_abc", draft());
    expect(error).toBeUndefined();
    expect(builder?.builder_id).toBe("game-builder");
  });
});

describe("builderStudioAdapter.get", () => {
  it("returns not_found error on 404", async () => {
    vi.spyOn(api, "hamApiFetch").mockResolvedValue(emptyResponse(404, { detail: "missing" }));
    const { builder, error } = await builderStudioAdapter.get("ws_abc", "ghost");
    expect(builder).toBeNull();
    expect(error?.kind).toBe("not_found");
  });
});

describe("builderStudioAdapter.preview", () => {
  it("returns a formatted summary when the API reports valid with an object summary", async () => {
    vi.spyOn(api, "hamApiFetch").mockResolvedValue(
      jsonResponse({
        valid: true,
        summary: {
          name: "Game Builder",
          permission_preset: "game_build",
          review_mode: "on_mutation",
          model_source: "ham_default",
        },
        errors: [],
      }),
    );
    const { summary, error } = await builderStudioAdapter.preview("ws_abc", draft());
    expect(error).toBeUndefined();
    expect(summary).toContain("Game Builder");
    expect(summary?.toLowerCase()).toContain("safety");
  });

  it("returns a structured validation error when preview reports valid: false", async () => {
    vi.spyOn(api, "hamApiFetch").mockResolvedValue(
      jsonResponse({
        valid: false,
        summary: {},
        errors: [
          "Value error, custom preset requires at least one allowed_paths, denied_paths, or denied_operations entry",
        ],
      }),
    );
    const { summary, error } = await builderStudioAdapter.preview("ws_abc", draft());
    expect(summary).toBeNull();
    expect(error?.kind).toBe("validation");
    if (error?.kind === "validation") {
      expect(error.wizardStep).toBe("safety");
      expect(error.message.toLowerCase()).toContain("advanced");
    }
  });

  it("returns the compiled summary string when the API still returns a string summary (legacy)", async () => {
    vi.spyOn(api, "hamApiFetch").mockResolvedValue(
      jsonResponse({ summary: "edit allowed; delete review; no network" }),
    );
    const { summary, error } = await builderStudioAdapter.preview("ws_abc", draft());
    expect(error).toBeUndefined();
    expect(summary).toBe("edit allowed; delete review; no network");
  });

  it("POST body omits workspace_id (path-only workspace scope)", async () => {
    const fetchSpy = vi.spyOn(api, "hamApiFetch").mockResolvedValue(
      jsonResponse({
        valid: true,
        summary: {
          name: "x",
          permission_preset: "app_build",
          review_mode: "always",
          model_source: "ham_default",
        },
        errors: [],
      }),
    );
    await builderStudioAdapter.preview("ws_abc", draft());
    const init = fetchSpy.mock.calls[0][1] as RequestInit;
    const posted = JSON.parse(String(init.body));
    expect(posted).not.toHaveProperty("workspace_id");
    expect(posted.builder_id).toBe("game-builder");
  });

  it("does not leak byok:<record-id> through the URL", async () => {
    const fetchSpy = vi
      .spyOn(api, "hamApiFetch")
      .mockResolvedValue(jsonResponse({ summary: "ok" }));
    await builderStudioAdapter.preview(
      "ws_abc",
      draft({ model_source: "connected_tools_byok", model_ref: "byok:secret-record" }),
    );
    const calls = fetchSpy.mock.calls;
    expect(calls.length).toBe(1);
    const url = String(calls[0][0]);
    expect(url).not.toContain("byok:");
  });
});

describe("builderStudioAdapter.testPlan", () => {
  it("returns the candidates list on a happy path", async () => {
    vi.spyOn(api, "hamApiFetch").mockResolvedValue(
      jsonResponse({ candidates: [{ label: "Open Builder" }] }),
    );
    const { candidates, error } = await builderStudioAdapter.testPlan(
      "ws_abc",
      "game-builder",
      "Build a tiny game",
    );
    expect(error).toBeUndefined();
    expect(candidates).toHaveLength(1);
  });
});

describe("builderStudioAdapter.softDelete", () => {
  it("returns ok on a 204 response", async () => {
    vi.spyOn(api, "hamApiFetch").mockResolvedValue(new Response(null, { status: 204 }));
    const { ok, error } = await builderStudioAdapter.softDelete("ws_abc", "game-builder");
    expect(error).toBeUndefined();
    expect(ok).toBe(true);
  });
});

describe("builderStudioAdapter — never throws raw network errors", () => {
  it.each([
    ["list", () => builderStudioAdapter.list("ws_abc")],
    ["get", () => builderStudioAdapter.get("ws_abc", "x")],
    ["create", () => builderStudioAdapter.create("ws_abc", draft())],
    ["update", () => builderStudioAdapter.update("ws_abc", "x", { enabled: false })],
    ["softDelete", () => builderStudioAdapter.softDelete("ws_abc", "x")],
    ["preview", () => builderStudioAdapter.preview("ws_abc", draft())],
    ["testPlan", () => builderStudioAdapter.testPlan("ws_abc", "x", "y")],
  ] as const)("%s wraps thrown errors as AdapterError", async (_name, run) => {
    vi.spyOn(api, "hamApiFetch").mockRejectedValue(new Error("network kaboom"));
    const out = await run();
    if ("error" in out) {
      expect(out.error?.kind).toBe("unknown");
    }
  });
});
