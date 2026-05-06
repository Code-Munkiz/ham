import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const { mockUseHamWorkspace } = vi.hoisted(() => ({
  mockUseHamWorkspace: vi.fn(),
}));

vi.mock("@/lib/ham/HamWorkspaceContext", () => ({
  useHamWorkspace: mockUseHamWorkspace,
}));

vi.mock("../screens/terminal/WorkspaceTerminalView", () => ({
  WorkspaceTerminalView: () => null,
}));

import { WorkspaceShell } from "../WorkspaceShell";
import { workspaceSessionAdapter } from "../workspaceAdapters";
import type { HamWorkspaceContextValue } from "@/lib/ham/HamWorkspaceContext";

function baseCtx(overrides: Partial<HamWorkspaceContextValue> = {}): HamWorkspaceContextValue {
  return {
    state: { status: "auth_required" },
    workspaces: [],
    active: null,
    authMode: null,
    hostedAuth: { clerkConfigured: true, isLoaded: true, isSignedIn: false },
    refresh: vi.fn(async () => undefined),
    selectWorkspace: vi.fn(),
    createWorkspace: vi.fn(),
    patchActiveWorkspace: vi.fn(),
    hasPerm: vi.fn(() => false),
    ...overrides,
  };
}

function renderShell() {
  return render(
    <MemoryRouter initialEntries={["/workspace/chat"]}>
      <WorkspaceShell>
        <div>workspace child</div>
      </WorkspaceShell>
    </MemoryRouter>,
  );
}

function readyCtx(workspaceId: string | null): HamWorkspaceContextValue {
  return baseCtx({
    state: {
      status: "ready",
      me: {
        user: {
          user_id: "u_alice",
          email: "alice@example.com",
          display_name: null,
          photo_url: null,
          primary_org_id: null,
        },
        orgs: [],
        workspaces: [],
        default_workspace_id: workspaceId,
        auth_mode: "clerk",
      },
      activeWorkspaceId: workspaceId,
    },
    hostedAuth: { clerkConfigured: true, isLoaded: true, isSignedIn: true },
  });
}

describe("WorkspaceShell auth gating", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
  });

  it("does not load chat sessions while Clerk is signed out", async () => {
    const list = vi
      .spyOn(workspaceSessionAdapter, "list")
      .mockRejectedValue(new Error("HTTP 401 Authorization: Bearer <Clerk session JWT> required"));
    mockUseHamWorkspace.mockReturnValue(baseCtx());

    renderShell();

    await waitFor(() => {
      expect(list).not.toHaveBeenCalled();
    });
    expect(screen.queryByText(/HTTP 401/i)).not.toBeInTheDocument();
  });

  it("loads chat sessions once workspace auth is ready", async () => {
    const list = vi.spyOn(workspaceSessionAdapter, "list").mockResolvedValue({
      sessions: [],
    });
    mockUseHamWorkspace.mockReturnValue(readyCtx(null));

    renderShell();

    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));
  });

  it("passes active workspace id when loading chat sessions", async () => {
    const list = vi.spyOn(workspaceSessionAdapter, "list").mockResolvedValue({
      sessions: [],
    });
    mockUseHamWorkspace.mockReturnValue(readyCtx("ws_a"));

    renderShell();

    await waitFor(() => expect(list).toHaveBeenCalledWith(50, 0, "ws_a"));
  });

  it("clears stale session list and ignores old workspace list responses after switching workspaces", async () => {
    let resolveA: (
      value: Awaited<ReturnType<typeof workspaceSessionAdapter.list>>,
    ) => void = () => {};
    const list = vi
      .spyOn(workspaceSessionAdapter, "list")
      .mockImplementation((_limit = 50, _offset = 0, workspaceId?: string | null) => {
        if (workspaceId === "ws_a") {
          return new Promise((resolve) => {
            resolveA = resolve;
          });
        }
        return Promise.resolve({
          sessions: [
            {
              session_id: "sid-b",
              preview: "Workspace B session",
              turn_count: 2,
              created_at: "2026-05-05T01:00:00Z",
            },
          ],
        });
      });

    mockUseHamWorkspace.mockReturnValue(readyCtx("ws_a"));
    const view = renderShell();
    await waitFor(() => expect(list).toHaveBeenCalledWith(50, 0, "ws_a"));

    mockUseHamWorkspace.mockReturnValue(readyCtx("ws_b"));
    view.rerender(
      <MemoryRouter initialEntries={["/workspace/chat"]}>
        <WorkspaceShell>
          <div>workspace child</div>
        </WorkspaceShell>
      </MemoryRouter>,
    );

    await waitFor(() => expect(list).toHaveBeenCalledWith(50, 0, "ws_b"));
    expect(await screen.findByText("Workspace B session")).toBeInTheDocument();

    resolveA({
      sessions: [
        {
          session_id: "sid-a",
          preview: "Workspace A session",
          turn_count: 2,
          created_at: "2026-05-05T00:00:00Z",
        },
      ],
    });

    await waitFor(() => expect(screen.queryByText("Workspace A session")).not.toBeInTheDocument());
    expect(screen.getByText("Workspace B session")).toBeInTheDocument();
  });
});
