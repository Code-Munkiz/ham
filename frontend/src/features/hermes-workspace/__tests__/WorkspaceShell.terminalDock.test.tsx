/**
 * Local terminal is not docked on `/workspace/chat` — use Workbench Terminal tab
 * and `/workspace/terminal` instead.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { mockUseHamWorkspace } = vi.hoisted(() => ({
  mockUseHamWorkspace: vi.fn(),
}));

vi.mock("@/lib/ham/HamWorkspaceContext", () => ({
  useHamWorkspace: mockUseHamWorkspace,
}));

import { WorkspaceShell } from "../WorkspaceShell";
import type { HamWorkspaceContextValue } from "@/lib/ham/HamWorkspaceContext";

function readyCtx(overrides: Partial<HamWorkspaceContextValue> = {}): HamWorkspaceContextValue {
  return {
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
    workspaces: [],
    active: null,
    authMode: "clerk",
    hostedAuth: { clerkConfigured: true, isLoaded: true, isSignedIn: true },
    refresh: vi.fn(async () => undefined),
    selectWorkspace: vi.fn(),
    createWorkspace: vi.fn(),
    patchActiveWorkspace: vi.fn(),
    archiveWorkspaceById: vi.fn(),
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

describe("WorkspaceShell chat route — no docked local terminal strip", () => {
  beforeEach(() => {
    localStorage.clear();
    mockUseHamWorkspace.mockReturnValue(readyCtx());
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("never renders the docked terminal strip for hosted users with no local runtime", async () => {
    renderShell();
    await waitFor(() => {
      expect(screen.getByText("workspace child")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("hww-chat-terminal-dock")).toBeNull();
    expect(screen.queryByText(/Local terminal/i)).toBeNull();
  });

  it("does not render the dock when a local runtime is configured in storage", async () => {
    localStorage.setItem("hww.localRuntimeBase", "http://127.0.0.1:8001");
    renderShell();
    await waitFor(() => {
      expect(screen.getByText("workspace child")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("hww-chat-terminal-dock")).toBeNull();
    expect(screen.queryByText(/Local terminal/i)).toBeNull();
  });

  it("does not render the dock when developer mode env is enabled", async () => {
    vi.stubEnv("VITE_HAM_SHOW_LOCAL_DEV_HINTS", "true");
    renderShell();
    await waitFor(() => {
      expect(screen.getByText("workspace child")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("hww-chat-terminal-dock")).toBeNull();
    expect(screen.queryByText(/Local terminal/i)).toBeNull();
  });
});
