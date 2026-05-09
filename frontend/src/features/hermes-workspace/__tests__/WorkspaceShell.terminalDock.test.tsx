/**
 * PR-1: hide the docked "Local terminal" strip on `/workspace/chat` for hosted
 * users with no paired local runtime. Existing chat shell still mounts; runtime-
 * connected and developer-mode states keep the dock available.
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

vi.mock("../screens/terminal/WorkspaceTerminalView", () => ({
  WorkspaceTerminalView: () => null,
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

describe("WorkspaceShell chat terminal dock gating (PR-1)", () => {
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

  it("does not render the docked terminal strip for hosted users with no local runtime", async () => {
    renderShell();

    await waitFor(() => {
      expect(screen.getByText("workspace child")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("hww-chat-terminal-dock")).toBeNull();
    expect(screen.queryByText(/Local terminal/i)).toBeNull();
    expect(screen.queryByText(/Local runtime not connected/i)).toBeNull();
  });

  it("renders the docked terminal strip when a local runtime is configured", async () => {
    localStorage.setItem("hww.localRuntimeBase", "http://127.0.0.1:8001");

    renderShell();

    await waitFor(() => {
      expect(screen.getByTestId("hww-chat-terminal-dock")).toBeInTheDocument();
    });
    expect(screen.getByText("Local terminal")).toBeInTheDocument();
  });

  it("renders the docked terminal strip when developer mode is enabled (no runtime saved)", async () => {
    vi.stubEnv("VITE_HAM_SHOW_LOCAL_DEV_HINTS", "true");

    renderShell();

    await waitFor(() => {
      expect(screen.getByTestId("hww-chat-terminal-dock")).toBeInTheDocument();
    });
    expect(screen.getByText("Local terminal")).toBeInTheDocument();
  });
});
