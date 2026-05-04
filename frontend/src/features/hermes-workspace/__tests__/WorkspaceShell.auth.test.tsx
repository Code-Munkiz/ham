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

function baseCtx(
  overrides: Partial<HamWorkspaceContextValue> = {},
): HamWorkspaceContextValue {
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

describe("WorkspaceShell auth gating", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
  });

  it("does not load chat sessions while Clerk is signed out", async () => {
    const list = vi.spyOn(workspaceSessionAdapter, "list").mockRejectedValue(
      new Error("HTTP 401 Authorization: Bearer <Clerk session JWT> required"),
    );
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
    mockUseHamWorkspace.mockReturnValue(
      baseCtx({
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
            default_workspace_id: null,
            auth_mode: "clerk",
          },
          activeWorkspaceId: null,
        },
        hostedAuth: { clerkConfigured: true, isLoaded: true, isSignedIn: true },
      }),
    );

    renderShell();

    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));
  });
});
