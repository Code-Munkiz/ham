import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { mockUseHamWorkspace, fetchSettingsMock, patchSettingsMock } = vi.hoisted(() => ({
  mockUseHamWorkspace: vi.fn(),
  fetchSettingsMock: vi.fn(),
  patchSettingsMock: vi.fn(),
}));

vi.mock("@/lib/ham/HamWorkspaceContext", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/ham/HamWorkspaceContext")>();
  return {
    ...actual,
    useHamWorkspace: mockUseHamWorkspace,
  };
});

vi.mock("@/lib/ham/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/ham/api")>();
  return {
    ...actual,
    listHamProjects: vi.fn(async () => ({ projects: [] })),
  };
});

vi.mock("@/features/hermes-workspace/adapters/codingAgentsAdapter", async (importOriginal) => {
  const actual =
    await importOriginal<
      typeof import("@/features/hermes-workspace/adapters/codingAgentsAdapter")
    >();
  return {
    ...actual,
    fetchCursorReadiness: vi.fn(async () => ({
      readiness: "needs_setup" as const,
      status: null,
      error: null,
    })),
    fetchCodingReadinessSnapshot: vi.fn(async () => ({
      opencode: "needs_setup" as const,
      claudeAgent: "needs_setup" as const,
    })),
    fetchCodingAgentAccessSettings: fetchSettingsMock,
    patchCodingAgentAccessSettings: patchSettingsMock,
  };
});

import WorkspaceBuildersSection from "../WorkspaceBuildersSection";
import { DEFAULT_CODING_AGENT_SETTINGS } from "@/features/hermes-workspace/adapters/codingAgentsAdapter";

function readyWs() {
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
        workspaces: [],
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

beforeEach(() => {
  mockUseHamWorkspace.mockReturnValue(readyWs());
  fetchSettingsMock.mockResolvedValue({
    ok: true,
    settings: { ...DEFAULT_CODING_AGENT_SETTINGS, workspace_id: "ws_1" },
  });
  patchSettingsMock.mockResolvedValue({
    ok: true,
    settings: { ...DEFAULT_CODING_AGENT_SETTINGS, workspace_id: "ws_1" },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  fetchSettingsMock.mockReset();
  patchSettingsMock.mockReset();
});

describe("WorkspaceBuildersSection", () => {
  it("renders the Builders heading and demoted subtitle", async () => {
    render(
      <MemoryRouter>
        <WorkspaceBuildersSection />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Builders", level: 2 })).toBeInTheDocument();
    });
    expect(
      screen.getAllByText(
        "Choose which builder HAM uses for normal builds. Work still starts in chat.",
      ).length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("heading", { name: "Builder", level: 2 })).toBeInTheDocument();
  });

  it("does not render launch / create / approve / test-plan CTAs", async () => {
    render(
      <MemoryRouter>
        <WorkspaceBuildersSection />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Builders", level: 2 })).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: /create builder/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /new task/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /test plan/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /approve launch/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /prepare build/i })).toBeNull();
  });
});
