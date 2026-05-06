/**
 * Phase 1c: workspaceApi.ts contract tests.
 *
 * Mocks the global `fetch` since the helpers go through `hamApiFetch`.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  HamWorkspaceApiError,
  createWorkspace,
  getMe,
  getWorkspace,
  listWorkspaces,
  patchWorkspace,
} from "@/lib/ham/workspaceApi";

const ORIGINAL_FETCH = global.fetch;

function jsonResponse(status: number, payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  // Reset Vite-injected env hooks consumed by api.ts; tests don't need a Clerk
  // pk and can run without it (no Authorization header attached).
  vi.stubEnv("VITE_HAM_API_BASE", "");
  vi.stubEnv("VITE_CLERK_PUBLISHABLE_KEY", "");
});

afterEach(() => {
  global.fetch = ORIGINAL_FETCH;
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("getMe", () => {
  it("returns parsed payload on 200", async () => {
    const me = {
      user: {
        user_id: "u_1",
        email: null,
        display_name: null,
        photo_url: null,
        primary_org_id: null,
      },
      orgs: [],
      workspaces: [],
      default_workspace_id: null,
      auth_mode: "local_dev_bypass",
    };
    global.fetch = vi.fn(async () => jsonResponse(200, me)) as typeof fetch;
    const out = await getMe();
    expect(out).toEqual(me);
    expect(global.fetch).toHaveBeenCalledWith(
      "/api/me",
      expect.objectContaining({ headers: expect.any(Headers) }),
    );
  });

  it("throws HamWorkspaceApiError with code on 401", async () => {
    global.fetch = vi.fn(async () =>
      jsonResponse(401, {
        detail: { error: { code: "HAM_WORKSPACE_AUTH_REQUIRED", message: "Set bypass" } },
      }),
    ) as typeof fetch;
    await expect(getMe()).rejects.toMatchObject({
      name: "HamWorkspaceApiError",
      status: 401,
      code: "HAM_WORKSPACE_AUTH_REQUIRED",
    });
  });

  it("falls back to a generic message when the body is empty", async () => {
    global.fetch = vi.fn(async () => new Response("", { status: 502 })) as typeof fetch;
    try {
      await getMe();
      throw new Error("expected throw");
    } catch (err) {
      expect(err).toBeInstanceOf(HamWorkspaceApiError);
      const e = err as HamWorkspaceApiError;
      expect(e.status).toBe(502);
      expect(e.code).toBeNull();
      expect(e.message).toMatch(/GET \/api\/me failed \(502\)/);
    }
  });
});

describe("listWorkspaces", () => {
  it("appends query params when provided", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { workspaces: [], default_workspace_id: null }),
    );
    global.fetch = fetchMock as unknown as typeof fetch;
    await listWorkspaces({ org_id: "org_x", include_archived: true });
    const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit?]>;
    const url = calls[0]?.[0] ?? "";
    expect(url).toContain("/api/workspaces");
    expect(url).toContain("org_id=org_x");
    expect(url).toContain("include_archived=true");
  });

  it("hits the bare path when no opts are given", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, { workspaces: [], default_workspace_id: null }),
    );
    global.fetch = fetchMock as unknown as typeof fetch;
    await listWorkspaces();
    const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit?]>;
    expect(calls[0]?.[0]).toBe("/api/workspaces");
  });
});

describe("createWorkspace", () => {
  it("sends POST with JSON body", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(201, {
        workspace: {
          workspace_id: "ws_abcdef0123456789",
          org_id: null,
          name: "Solo",
          slug: "solo",
          description: "",
          status: "active",
          role: "owner",
          perms: ["workspace:read"],
          is_default: false,
          created_at: "2026-05-03T00:00:00+00:00",
          updated_at: "2026-05-03T00:00:00+00:00",
        },
        context: { role: "owner", perms: ["workspace:read"], org_role: null },
        audit_id: "audit_1",
      }),
    );
    global.fetch = fetchMock as unknown as typeof fetch;
    const out = await createWorkspace({ name: "Solo" });
    expect(out.workspace.slug).toBe("solo");
    const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit?]>;
    const init = calls[0]?.[1];
    expect(init?.method).toBe("POST");
    expect(typeof init?.body).toBe("string");
    expect(JSON.parse(String(init?.body))).toEqual({ name: "Solo" });
  });

  it("surfaces 409 conflict code", async () => {
    global.fetch = vi.fn(async () =>
      jsonResponse(409, {
        detail: {
          error: {
            code: "HAM_WORKSPACE_SLUG_CONFLICT",
            message: "already taken",
          },
        },
      }),
    ) as typeof fetch;
    await expect(createWorkspace({ name: "Solo" })).rejects.toMatchObject({
      status: 409,
      code: "HAM_WORKSPACE_SLUG_CONFLICT",
    });
  });
});

describe("getWorkspace", () => {
  it("returns 200 payload", async () => {
    global.fetch = vi.fn(async () =>
      jsonResponse(200, {
        workspace: {
          workspace_id: "ws_a",
          org_id: null,
          name: "Solo",
          slug: "solo",
          description: "",
          status: "active",
          role: "owner",
          perms: [],
          is_default: false,
          created_at: "x",
          updated_at: "x",
        },
        context: { role: "owner", perms: [], org_role: null },
      }),
    ) as typeof fetch;
    const out = await getWorkspace("ws_a");
    expect(out.workspace.workspace_id).toBe("ws_a");
  });
});

describe("patchWorkspace", () => {
  it("PATCH with JSON body", async () => {
    const fetchMock = vi.fn(async () =>
      jsonResponse(200, {
        workspace: {
          workspace_id: "ws_a",
          org_id: null,
          name: "Renamed",
          slug: "solo",
          description: "",
          status: "active",
          role: "owner",
          perms: [],
          is_default: false,
          created_at: "x",
          updated_at: "x",
        },
        context: { role: "owner", perms: [], org_role: null },
        audit_id: "audit_2",
      }),
    );
    global.fetch = fetchMock as unknown as typeof fetch;
    const out = await patchWorkspace("ws_a", { name: "Renamed" });
    expect(out.workspace.name).toBe("Renamed");
    const calls = fetchMock.mock.calls as unknown as Array<[string, RequestInit?]>;
    const init = calls[0]?.[1];
    expect(init?.method).toBe("PATCH");
  });
});
