import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const { mockUseHamWorkspace } = vi.hoisted(() => ({
  mockUseHamWorkspace: vi.fn(),
}));

vi.mock("@/lib/ham/HamWorkspaceContext", () => ({
  useHamWorkspace: mockUseHamWorkspace,
}));

import { WorkspaceHome } from "../WorkspaceHome";
import type { HamWorkspaceContextValue } from "@/lib/ham/HamWorkspaceContext";

function readyWs(): HamWorkspaceContextValue {
  return {
    state: {
      status: "ready",
      me: {
        user: {
          user_id: "u1",
          email: "a@example.com",
          display_name: null,
          photo_url: null,
          primary_org_id: null,
        },
        orgs: [],
        workspaces: [
          {
            workspace_id: "ws_1",
            org_id: null,
            name: "Acme Lab",
            slug: "acme-lab",
            description: "Primary workspace",
            status: "active",
            role: "owner",
            perms: [],
            is_default: true,
            created_at: "2026-01-01T00:00:00Z",
            updated_at: "2026-01-01T00:00:00Z",
          },
        ],
        default_workspace_id: "ws_1",
        auth_mode: "clerk",
      },
      activeWorkspaceId: "ws_1",
    },
    workspaces: [
      {
        workspace_id: "ws_1",
        org_id: null,
        name: "Acme Lab",
        slug: "acme-lab",
        description: "Primary workspace",
        status: "active",
        role: "owner",
        perms: [],
        is_default: true,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ],
    active: null,
    authMode: "clerk",
    hostedAuth: null,
    refresh: vi.fn(),
    selectWorkspace: vi.fn(),
    createWorkspace: vi.fn(),
    patchActiveWorkspace: vi.fn(),
    hasPerm: vi.fn(() => true),
  };
}

function renderHome(ctx = readyWs()) {
  mockUseHamWorkspace.mockReturnValue(ctx);
  return render(
    <MemoryRouter>
      <WorkspaceHome />
    </MemoryRouter>,
  );
}

describe("WorkspaceHome", () => {
  it("renders workspace cards when ready with workspaces", () => {
    renderHome();
    expect(screen.getByRole("heading", { name: "Projects" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Acme Lab" })).toBeInTheDocument();
    expect(screen.getByText(/acme-lab/i)).toBeInTheDocument();
    expect(screen.getByText(/Primary workspace/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open chat/i })).toHaveAttribute(
      "href",
      "/workspace/chat",
    );
    expect(screen.getByRole("link", { name: /Open files/i })).toHaveAttribute(
      "href",
      "/workspace/files",
    );
    expect(screen.getByRole("link", { name: /Open terminal/i })).toHaveAttribute(
      "href",
      "/workspace/terminal",
    );
    expect(screen.getByRole("link", { name: /Workspace settings/i })).toHaveAttribute(
      "href",
      "/workspace/settings",
    );
  });

  it("shows sign-in empty state when workspace context is not ready", () => {
    mockUseHamWorkspace.mockReturnValue({
      state: { status: "auth_required" },
      workspaces: [],
      active: null,
      authMode: null,
      hostedAuth: { clerkConfigured: true, isLoaded: true, isSignedIn: false },
      refresh: vi.fn(),
      selectWorkspace: vi.fn(),
      createWorkspace: vi.fn(),
      patchActiveWorkspace: vi.fn(),
      hasPerm: vi.fn(() => false),
    });
    render(
      <MemoryRouter>
        <WorkspaceHome />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Sign in to see your projects/i)).toBeInTheDocument();
  });

  it("does not regress to stale feature-grid copy", () => {
    renderHome();
    expect(screen.queryByText(/Surface map/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Every conversation, one click away/i)).not.toBeInTheDocument();
  });
});
