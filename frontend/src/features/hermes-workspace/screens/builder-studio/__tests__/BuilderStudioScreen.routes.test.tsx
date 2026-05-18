import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const { mockUseHamWorkspace } = vi.hoisted(() => ({
  mockUseHamWorkspace: vi.fn(),
}));

vi.mock("@/lib/ham/HamWorkspaceContext", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/ham/HamWorkspaceContext")>();
  return {
    ...actual,
    useHamWorkspace: mockUseHamWorkspace,
  };
});

import { BuilderStudioScreen } from "../BuilderStudioScreen";
import type { HamWorkspaceContextValue } from "@/lib/ham/HamWorkspaceContext";
import { builderStudioAdapter } from "@/features/hermes-workspace/adapters/builderStudioAdapter";
import * as api from "@/lib/ham/api";
import * as codingAgentsAdapter from "@/features/hermes-workspace/adapters/codingAgentsAdapter";

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
    workspaces: [],
    active: null,
    authMode: "clerk",
    hostedAuth: null,
    refresh: vi.fn(),
    selectWorkspace: vi.fn(),
    createWorkspace: vi.fn(),
    patchActiveWorkspace: vi.fn(),
    archiveWorkspaceById: vi.fn(),
    hasPerm: vi.fn(() => true),
  };
}

function renderAt(path: string) {
  mockUseHamWorkspace.mockReturnValue(readyWs());
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/workspace/builder-studio" element={<BuilderStudioScreen />} />
        <Route path="/workspace/builder-studio/:builderId" element={<BuilderStudioScreen />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

beforeEach(() => {
  vi.spyOn(codingAgentsAdapter, "fetchCursorReadiness").mockResolvedValue({
    readiness: "ready",
    status: null,
    error: null,
  });
  vi.spyOn(codingAgentsAdapter, "fetchCodingReadinessSnapshot").mockResolvedValue({
    opencode: "needs_setup",
    claudeAgent: "ready",
  });
  vi.spyOn(api, "listHamProjects").mockResolvedValue({ projects: [] });
});

describe("BuilderStudioScreen routes", () => {
  it("hides all custom-builder list failure UI on the base route when the list endpoint returns list-not-found", async () => {
    vi.spyOn(builderStudioAdapter, "list").mockResolvedValue({
      builders: [],
      error: { kind: "builders_list_not_found" },
    });

    renderAt("/workspace/builder-studio");

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Builder Studio" })).toBeInTheDocument();
    });
    expect(
      screen.queryByText(/Custom builders aren't available here yet/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/Couldn't load custom builders/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Try again in a moment/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(
      screen.queryByText(/That builder may have been deleted or is no longer available/i),
    ).not.toBeInTheDocument();
  });

  it("hides list failure chrome on the base route for generic list errors", async () => {
    vi.spyOn(builderStudioAdapter, "list").mockResolvedValue({
      builders: [],
      error: { kind: "unknown", message: "Temporary outage" },
    });

    renderAt("/workspace/builder-studio");

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Builder Studio" })).toBeInTheDocument();
    });
    expect(screen.queryByText("Temporary outage")).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByText(/Couldn't load custom builders/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Try again in a moment/i)).not.toBeInTheDocument();
  });

  it("shows a scoped not-found card on detail route when the id is not in the loaded list", async () => {
    vi.spyOn(builderStudioAdapter, "list").mockResolvedValue({ builders: [] });

    renderAt("/workspace/builder-studio/missing-id");

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Builder not found" })).toBeInTheDocument();
    });
    expect(
      screen.getByText(/That builder may have been deleted or is no longer available/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Back to Builder Studio" })).toBeInTheDocument();
  });

  it("shows builder connection rows without preference toggles or native select", async () => {
    vi.spyOn(builderStudioAdapter, "list").mockResolvedValue({ builders: [] });

    renderAt("/workspace/builder-studio");

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Builder Studio" })).toBeInTheDocument();
    });

    expect(screen.getByRole("heading", { name: "Claude" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Cursor" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Factory Droid" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "OpenCode" })).toBeInTheDocument();
    expect(screen.queryByText("Premium reasoning builder")).not.toBeInTheDocument();
    expect(document.querySelector("input[type='checkbox']")).toBeNull();
    expect(document.querySelector("select")).toBeNull();
  });

  it("opens Create builder as an accessible dialog with solid modal semantics", async () => {
    vi.spyOn(builderStudioAdapter, "list").mockResolvedValue({ builders: [] });

    renderAt("/workspace/builder-studio");

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "No custom builders yet." })).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByRole("button", { name: "Create builder" })[0]);

    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-labelledby", "create-builder-wizard-title");
  });
});
