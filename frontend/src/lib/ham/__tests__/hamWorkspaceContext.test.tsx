/**
 * Phase 1c: HamWorkspaceProvider state-machine tests.
 *
 * Mocks `@/lib/ham/workspaceApi` so we don't hit `hamApiFetch`. Uses RTL +
 * jsdom for hook composition with the provider.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, renderHook, waitFor } from "@testing-library/react";
import * as React from "react";

vi.mock("@/lib/ham/workspaceApi", async () => {
  const actual = await vi.importActual<typeof import("@/lib/ham/workspaceApi")>(
    "@/lib/ham/workspaceApi",
  );
  return {
    ...actual,
    getMe: vi.fn(),
    listWorkspaces: vi.fn(),
    createWorkspace: vi.fn(),
    getWorkspace: vi.fn(),
    patchWorkspace: vi.fn(),
  };
});

import {
  HamWorkspaceApiError,
  type HamMeResponse,
  type HamWorkspaceSummary,
} from "@/lib/ham/workspaceApi";
import * as api from "@/lib/ham/workspaceApi";
import {
  HamWorkspaceProvider,
  useHamWorkspace,
} from "@/lib/ham/HamWorkspaceContext";
import { activeWorkspaceStorageKey } from "@/lib/ham/hamWorkspaceStorage";

const mockedGetMe = api.getMe as unknown as ReturnType<typeof vi.fn>;
const mockedCreate = api.createWorkspace as unknown as ReturnType<typeof vi.fn>;
const mockedPatch = api.patchWorkspace as unknown as ReturnType<typeof vi.fn>;

function summary(overrides: Partial<HamWorkspaceSummary> = {}): HamWorkspaceSummary {
  return {
    workspace_id: "ws_a",
    org_id: null,
    name: "Alpha",
    slug: "alpha",
    description: "",
    status: "active",
    role: "owner",
    perms: ["workspace:read", "workspace:write", "workspace:admin"],
    is_default: false,
    created_at: "2026-05-03T00:00:00+00:00",
    updated_at: "2026-05-03T00:00:00+00:00",
    ...overrides,
  };
}

function meWith(workspaces: HamWorkspaceSummary[], opts: Partial<HamMeResponse> = {}): HamMeResponse {
  return {
    user: {
      user_id: "u_alice",
      email: "alice@example.com",
      display_name: null,
      photo_url: null,
      primary_org_id: null,
    },
    orgs: [],
    workspaces,
    default_workspace_id: opts.default_workspace_id ?? null,
    auth_mode: opts.auth_mode ?? "clerk",
    ...opts,
  };
}

function withProvider() {
  return ({ children }: { children: React.ReactNode }) => (
    <HamWorkspaceProvider>{children}</HamWorkspaceProvider>
  );
}

function withHostedProvider(
  hostedAuth: React.ComponentProps<typeof HamWorkspaceProvider>["hostedAuth"],
) {
  return ({ children }: { children: React.ReactNode }) => (
    <HamWorkspaceProvider hostedAuth={hostedAuth}>{children}</HamWorkspaceProvider>
  );
}

beforeEach(() => {
  window.localStorage.clear();
  mockedGetMe.mockReset();
  mockedCreate.mockReset();
  mockedPatch.mockReset();
});

afterEach(() => {
  window.localStorage.clear();
  vi.restoreAllMocks();
});

describe("HamWorkspaceProvider initial fetch", () => {
  it("auto-selects when there is exactly one workspace", async () => {
    mockedGetMe.mockResolvedValue(meWith([summary({ workspace_id: "ws_only" })]));
    const { result } = renderHook(() => useHamWorkspace(), { wrapper: withProvider() });
    await waitFor(() => {
      expect(result.current.state.status).toBe("ready");
    });
    expect(result.current.active?.workspace_id).toBe("ws_only");
    expect(window.localStorage.getItem(activeWorkspaceStorageKey("u_alice"))).toBe(
      "ws_only",
    );
  });

  it("uses default_workspace_id when multiple are returned and storage is empty", async () => {
    const ws_a = summary({ workspace_id: "ws_a", name: "Alpha" });
    const ws_b = summary({ workspace_id: "ws_b", name: "Beta", role: "member", perms: ["workspace:read"] });
    mockedGetMe.mockResolvedValue(
      meWith([ws_a, ws_b], { default_workspace_id: "ws_b" }),
    );
    const { result } = renderHook(() => useHamWorkspace(), { wrapper: withProvider() });
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    expect(result.current.active?.workspace_id).toBe("ws_b");
  });

  it("prefers localStorage hit over default_workspace_id", async () => {
    window.localStorage.setItem(activeWorkspaceStorageKey("u_alice"), "ws_a");
    const ws_a = summary({ workspace_id: "ws_a" });
    const ws_b = summary({ workspace_id: "ws_b" });
    mockedGetMe.mockResolvedValue(
      meWith([ws_a, ws_b], { default_workspace_id: "ws_b" }),
    );
    const { result } = renderHook(() => useHamWorkspace(), { wrapper: withProvider() });
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    expect(result.current.active?.workspace_id).toBe("ws_a");
  });

  it("renders picker prompt (active=null) when multiple, no default, no storage", async () => {
    const ws_a = summary({ workspace_id: "ws_a" });
    const ws_b = summary({ workspace_id: "ws_b" });
    mockedGetMe.mockResolvedValue(meWith([ws_a, ws_b]));
    const { result } = renderHook(() => useHamWorkspace(), { wrapper: withProvider() });
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    expect(result.current.active).toBeNull();
  });

  it("transitions to onboarding when zero workspaces are returned", async () => {
    mockedGetMe.mockResolvedValue(meWith([]));
    const { result } = renderHook(() => useHamWorkspace(), { wrapper: withProvider() });
    await waitFor(() => expect(result.current.state.status).toBe("onboarding"));
  });

  it("classifies HAM_WORKSPACE_AUTH_REQUIRED as setup_needed", async () => {
    mockedGetMe.mockRejectedValue(
      new HamWorkspaceApiError(401, "HAM_WORKSPACE_AUTH_REQUIRED", "Set bypass"),
    );
    const { result } = renderHook(() => useHamWorkspace(), { wrapper: withProvider() });
    await waitFor(() => expect(result.current.state.status).toBe("setup_needed"));
  });

  it("classifies CLERK_SESSION_REQUIRED as auth_required", async () => {
    mockedGetMe.mockRejectedValue(
      new HamWorkspaceApiError(401, "CLERK_SESSION_REQUIRED", "Sign in"),
    );
    const { result } = renderHook(() => useHamWorkspace(), { wrapper: withProvider() });
    await waitFor(() => expect(result.current.state.status).toBe("auth_required"));
  });

  it("does not call /api/me until Clerk auth has loaded", async () => {
    const { result } = renderHook(() => useHamWorkspace(), {
      wrapper: withHostedProvider({
        clerkConfigured: true,
        isLoaded: false,
        isSignedIn: false,
      }),
    });
    await waitFor(() => expect(result.current.state.status).toBe("auth_loading"));
    expect(mockedGetMe).not.toHaveBeenCalled();
  });

  it("does not call /api/me when Clerk is configured but signed out", async () => {
    const { result } = renderHook(() => useHamWorkspace(), {
      wrapper: withHostedProvider({
        clerkConfigured: true,
        isLoaded: true,
        isSignedIn: false,
      }),
    });
    await waitFor(() => expect(result.current.state.status).toBe("auth_required"));
    expect(mockedGetMe).not.toHaveBeenCalled();
  });

  it("shows auth_not_configured without calling /api/me when Clerk key is missing", async () => {
    const { result } = renderHook(() => useHamWorkspace(), {
      wrapper: withHostedProvider({
        clerkConfigured: false,
        isLoaded: true,
        isSignedIn: false,
      }),
    });
    await waitFor(() => expect(result.current.state.status).toBe("auth_not_configured"));
    expect(mockedGetMe).not.toHaveBeenCalled();
  });

  it("calls /api/me when Clerk is configured, loaded, and signed in", async () => {
    mockedGetMe.mockResolvedValue(meWith([summary()]));
    const { result } = renderHook(() => useHamWorkspace(), {
      wrapper: withHostedProvider({
        clerkConfigured: true,
        isLoaded: true,
        isSignedIn: true,
      }),
    });
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    expect(mockedGetMe).toHaveBeenCalledTimes(1);
  });

  it("transitions to error on 5xx and recovers via refresh", async () => {
    mockedGetMe.mockRejectedValueOnce(new HamWorkspaceApiError(503, null, "down"));
    const { result } = renderHook(() => useHamWorkspace(), { wrapper: withProvider() });
    await waitFor(() => expect(result.current.state.status).toBe("error"));
    mockedGetMe.mockResolvedValueOnce(meWith([summary()]));
    await act(async () => {
      await result.current.refresh();
    });
    expect(result.current.state.status).toBe("ready");
  });
});

describe("selectWorkspace", () => {
  it("updates active id and persists to storage", async () => {
    const ws_a = summary({ workspace_id: "ws_a" });
    const ws_b = summary({ workspace_id: "ws_b" });
    mockedGetMe.mockResolvedValue(meWith([ws_a, ws_b]));
    const { result } = renderHook(() => useHamWorkspace(), { wrapper: withProvider() });
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    act(() => {
      result.current.selectWorkspace("ws_b");
    });
    expect(result.current.active?.workspace_id).toBe("ws_b");
    expect(
      window.localStorage.getItem(activeWorkspaceStorageKey("u_alice")),
    ).toBe("ws_b");
  });

  it("ignores selection of an unknown workspace id", async () => {
    mockedGetMe.mockResolvedValue(meWith([summary()]));
    const { result } = renderHook(() => useHamWorkspace(), { wrapper: withProvider() });
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    act(() => result.current.selectWorkspace("ws_unknown"));
    expect(result.current.active?.workspace_id).toBe("ws_a");
  });
});

describe("createWorkspace", () => {
  it("auto-selects the new workspace and refetches /api/me", async () => {
    mockedGetMe.mockResolvedValueOnce(meWith([])); // initial: empty
    const newWs = summary({ workspace_id: "ws_new", name: "New" });
    mockedCreate.mockResolvedValue({
      workspace: newWs,
      context: { role: "owner", perms: newWs.perms, org_role: null },
      audit_id: "a_1",
    });
    mockedGetMe.mockResolvedValueOnce(meWith([newWs])); // after create
    const { result } = renderHook(() => useHamWorkspace(), { wrapper: withProvider() });
    await waitFor(() => expect(result.current.state.status).toBe("onboarding"));
    await act(async () => {
      await result.current.createWorkspace({ name: "New" });
    });
    expect(result.current.state.status).toBe("ready");
    expect(result.current.active?.workspace_id).toBe("ws_new");
  });
});

describe("hasPerm", () => {
  it("reflects active workspace perm set", async () => {
    mockedGetMe.mockResolvedValue(
      meWith([summary({ perms: ["workspace:read", "workspace:write"] })]),
    );
    const { result } = renderHook(() => useHamWorkspace(), { wrapper: withProvider() });
    await waitFor(() => expect(result.current.state.status).toBe("ready"));
    expect(result.current.hasPerm("workspace:read")).toBe(true);
    expect(result.current.hasPerm("workspace:admin")).toBe(false);
  });
});

describe("provider error swallowing", () => {
  it("never throws during render even when getMe rejects synchronously", async () => {
    mockedGetMe.mockImplementation(() => {
      throw new Error("blew up");
    });
    expect(() =>
      render(
        <HamWorkspaceProvider>
          <span>child</span>
        </HamWorkspaceProvider>,
      ),
    ).not.toThrow();
  });
});
