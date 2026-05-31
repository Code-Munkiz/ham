import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const {
  mockUseHamWorkspace,
  fetchSettingsMock,
  patchSettingsMock,
  readinessMock,
  ensureDefaultProjectMock,
} = vi.hoisted(() => ({
  mockUseHamWorkspace: vi.fn(),
  fetchSettingsMock: vi.fn(),
  patchSettingsMock: vi.fn(),
  readinessMock: vi.fn(),
  ensureDefaultProjectMock: vi.fn(),
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
    listHamProjects: vi.fn(async () => ({ projects: [{ id: "project_1" }] })),
    ensureBuilderDefaultProject: ensureDefaultProjectMock,
  };
});

vi.mock("@/features/hermes-workspace/adapters/codingAgentsAdapter", async (importOriginal) => {
  const actual =
    await importOriginal<
      typeof import("@/features/hermes-workspace/adapters/codingAgentsAdapter")
    >();
  return {
    ...actual,
    fetchCodingAgentAccessSettings: fetchSettingsMock,
    patchCodingAgentAccessSettings: patchSettingsMock,
    fetchCodingReadinessSnapshot: readinessMock,
    fetchCursorReadiness: vi.fn(async () => ({
      readiness: "needs_setup" as const,
      status: null,
      error: null,
    })),
  };
});

import WorkspaceBuildersSection from "../WorkspaceBuildersSection";
import { DEFAULT_CODING_AGENT_SETTINGS } from "@/features/hermes-workspace/adapters/codingAgentsAdapter";
import { listHamProjects, ensureBuilderDefaultProject } from "@/lib/ham/api";

function settings(over: Partial<typeof DEFAULT_CODING_AGENT_SETTINGS> = {}) {
  return { ...DEFAULT_CODING_AGENT_SETTINGS, workspace_id: "ws_1", ...over };
}

// Internals that must never appear in the control's rendered copy.
const FORBIDDEN = [
  "opencode_cli",
  "factory_droid_build",
  "cursor_cloud",
  "claude_agent",
  "claude_code",
  "registry_v2",
  "proposal_digest",
  "base_revision",
  "ham_opencode_exec_token",
  "ham_droid_exec_token",
  "cursor_api_key",
  "anthropic_api_key",
  "workflow_id",
  "safe_edit_low",
  "recipe",
  "playbook",
];

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

function renderBuildersSection() {
  return render(
    <MemoryRouter>
      <WorkspaceBuildersSection />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockUseHamWorkspace.mockReturnValue(readyWs());
  readinessMock.mockResolvedValue({ opencode: "ready", claudeAgent: "needs_setup" });
  fetchSettingsMock.mockResolvedValue({ ok: true, settings: settings() });
  patchSettingsMock.mockImplementation(async (_ws: string, patch: Record<string, unknown>) => ({
    ok: true,
    settings: settings(patch),
  }));
  ensureDefaultProjectMock.mockResolvedValue({
    workspace_id: "ws_1",
    project_id: "project.builder-test",
    project: {
      id: "project.builder-test",
      name: "Builder",
      root: "/tmp/builder",
      workspace_id: "ws_1",
    },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  mockUseHamWorkspace.mockReset();
  fetchSettingsMock.mockReset();
  patchSettingsMock.mockReset();
  readinessMock.mockReset();
  ensureDefaultProjectMock.mockReset();
});

describe("Workspace Builders selected-builder rows", () => {
  it("renders one coherent Builders section with the four external builder options", async () => {
    renderBuildersSection();
    await waitFor(() => expect(fetchSettingsMock).toHaveBeenCalled());
    expect(screen.getByRole("heading", { name: "Builders" })).toBeInTheDocument();
    expect(
      screen.getAllByText(
        "Choose an external builder for HAM to use. If none is selected, HAM builds natively. Native HAM build support is being wired.",
      ).length,
    ).toBeGreaterThanOrEqual(1);
    for (const name of ["OpenCode", "Factory Droid", "Cursor", "Claude"]) {
      expect(screen.getByRole("switch", { name })).toBeInTheDocument();
    }
    expect(screen.queryByRole("switch", { name: "Hermes Agent" })).toBeNull();
    expect(screen.queryByText("Builder connections")).toBeNull();
  });

  it("loads the current selected_builder from the API", async () => {
    fetchSettingsMock.mockResolvedValue({
      ok: true,
      settings: settings({ selected_builder: "factory_droid" }),
    });
    renderBuildersSection();
    await waitFor(() =>
      expect(screen.getByRole("switch", { name: "Factory Droid" })).toHaveAttribute(
        "aria-checked",
        "true",
      ),
    );
  });

  it("PATCHes selected_builder=opencode when OpenCode is chosen", async () => {
    renderBuildersSection();
    await waitFor(() => expect(fetchSettingsMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("switch", { name: "OpenCode" }));
    await waitFor(() => expect(patchSettingsMock).toHaveBeenCalledTimes(1));
    expect(patchSettingsMock).toHaveBeenCalledWith("ws_1", { selected_builder: "opencode" });
  });

  it("PATCHes selected_builder=factory_droid when Factory Droid is chosen", async () => {
    renderBuildersSection();
    await waitFor(() => expect(fetchSettingsMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("switch", { name: "Factory Droid" }));
    await waitFor(() => expect(patchSettingsMock).toHaveBeenCalledTimes(1));
    expect(patchSettingsMock).toHaveBeenCalledWith("ws_1", { selected_builder: "factory_droid" });
  });

  it("turning Factory Droid on visually turns OpenCode off", async () => {
    fetchSettingsMock.mockResolvedValue({
      ok: true,
      settings: settings({ selected_builder: "opencode" }),
    });
    renderBuildersSection();
    await waitFor(() =>
      expect(screen.getByRole("switch", { name: "OpenCode" })).toHaveAttribute(
        "aria-checked",
        "true",
      ),
    );
    fireEvent.click(screen.getByRole("switch", { name: "Factory Droid" }));
    await waitFor(() =>
      expect(screen.getByRole("switch", { name: "Factory Droid" })).toHaveAttribute(
        "aria-checked",
        "true",
      ),
    );
    expect(screen.getByRole("switch", { name: "OpenCode" })).toHaveAttribute(
      "aria-checked",
      "false",
    );
    expect(patchSettingsMock).toHaveBeenCalledWith("ws_1", {
      selected_builder: "factory_droid",
    });
  });

  it("toggling the active builder off clears selected_builder", async () => {
    fetchSettingsMock.mockResolvedValue({
      ok: true,
      settings: settings({ selected_builder: "opencode" }),
    });
    patchSettingsMock.mockResolvedValueOnce({
      ok: true,
      settings: settings({ selected_builder: null }),
    });
    renderBuildersSection();
    await waitFor(() =>
      expect(screen.getByRole("switch", { name: "OpenCode" })).toHaveAttribute(
        "aria-checked",
        "true",
      ),
    );
    fireEvent.click(screen.getByRole("switch", { name: "OpenCode" }));
    await waitFor(() => expect(patchSettingsMock).toHaveBeenCalledTimes(1));
    expect(patchSettingsMock).toHaveBeenCalledWith("ws_1", { selected_builder: null });
    await waitFor(() =>
      expect(screen.getByRole("switch", { name: "OpenCode" })).toHaveAttribute(
        "aria-checked",
        "false",
      ),
    );
  });

  it("failed PATCH reverts and shows a clear error", async () => {
    fetchSettingsMock.mockResolvedValue({
      ok: true,
      settings: settings({ selected_builder: "cursor" }),
    });
    patchSettingsMock.mockResolvedValueOnce({ ok: false, errorMessage: "nope" });
    renderBuildersSection();
    await waitFor(() =>
      expect(screen.getByRole("switch", { name: "Cursor" })).toHaveAttribute(
        "aria-checked",
        "true",
      ),
    );
    fireEvent.click(screen.getByRole("switch", { name: "OpenCode" }));
    await waitFor(() =>
      expect(patchSettingsMock).toHaveBeenCalledWith("ws_1", { selected_builder: "opencode" }),
    );
    await waitFor(() =>
      expect(screen.getByRole("switch", { name: "Cursor" })).toHaveAttribute(
        "aria-checked",
        "true",
      ),
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Couldn't save your builder choice. Try again.",
    );
  });

  it("failed auth-like PATCH suggests refresh or sign-in", async () => {
    fetchSettingsMock.mockResolvedValue({
      ok: true,
      settings: settings({ selected_builder: "cursor" }),
    });
    patchSettingsMock.mockResolvedValueOnce({
      ok: false,
      errorMessage: "Couldn't save your builder choice. Refresh or sign in again.",
    });
    renderBuildersSection();
    await waitFor(() =>
      expect(screen.getByRole("switch", { name: "Cursor" })).toHaveAttribute(
        "aria-checked",
        "true",
      ),
    );
    fireEvent.click(screen.getByRole("switch", { name: "OpenCode" }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Couldn't save your builder choice. Refresh or sign in again.",
      ),
    );
  });

  it("treats stored hermes_agent as native HAM mode without showing a selector row", async () => {
    fetchSettingsMock.mockResolvedValue({
      ok: true,
      settings: settings({ selected_builder: "hermes_agent" }),
    });
    renderBuildersSection();
    await waitFor(() =>
      expect(screen.getByTestId("hww-selected-builder-helper")).toHaveTextContent(
        "No external builder selected — HAM builds natively. Native HAM build support is being wired.",
      ),
    );
    expect(screen.queryByRole("switch", { name: "Hermes Agent" })).toBeNull();
    expect(screen.queryByText(/Hermes Agent new-build support is coming soon/i)).toBeNull();
  });

  it("shows native HAM mode copy when no external builder is selected", async () => {
    fetchSettingsMock.mockResolvedValue({
      ok: true,
      settings: settings({ selected_builder: null }),
    });
    renderBuildersSection();
    await waitFor(() =>
      expect(screen.getByTestId("hww-selected-builder-helper")).toHaveTextContent(
        "No external builder selected — HAM builds natively. Native HAM build support is being wired.",
      ),
    );
  });

  it("shows separate-flow helper copy for Cursor", async () => {
    fetchSettingsMock.mockResolvedValue({
      ok: true,
      settings: settings({ selected_builder: "cursor" }),
    });
    renderBuildersSection();
    await waitFor(() =>
      expect(screen.getByTestId("hww-selected-builder-helper")).toHaveTextContent(
        "Cursor runs through its own build flow for now.",
      ),
    );
  });

  it("shows Finish setup for selected OpenCode when it is not build-ready", async () => {
    // listHamProjects (mocked) returns a project with no workspace_id, so the
    // build gate is not satisfied even though the provider is platform-ready.
    fetchSettingsMock.mockResolvedValue({
      ok: true,
      settings: settings({ selected_builder: "opencode" }),
    });
    renderBuildersSection();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Finish setup" })).toBeInTheDocument(),
    );
    expect(
      screen.getByText(
        "Finish setup before HAM can use OpenCode. HAM will prepare a workspace project for builds.",
      ),
    ).toBeInTheDocument();
    // The selected, blocked builder must not be advertised as build-ready.
    expect(screen.queryByText("Ready")).toBeNull();
    expect(screen.queryByText("Available")).toBeNull();
  });

  it("Finish setup creates the default builder project and refreshes readiness", async () => {
    fetchSettingsMock.mockResolvedValue({
      ok: true,
      settings: settings({ selected_builder: "opencode" }),
    });
    renderBuildersSection();
    fireEvent.click(await screen.findByRole("button", { name: "Finish setup" }));
    await waitFor(() => expect(ensureBuilderDefaultProject).toHaveBeenCalledWith("ws_1"));
    await waitFor(() => expect(fetchSettingsMock).toHaveBeenCalledTimes(2));
  });

  it("shows 'Ready' for OpenCode once a managed workspace project exists", async () => {
    vi.mocked(listHamProjects).mockResolvedValueOnce({
      projects: [{ id: "project_1", workspace_id: "ws_1" }],
    } as Awaited<ReturnType<typeof listHamProjects>>);
    fetchSettingsMock.mockResolvedValue({
      ok: true,
      settings: settings({ selected_builder: "opencode" }),
    });
    renderBuildersSection();
    await waitFor(() => expect(screen.getAllByText("Ready").length).toBeGreaterThanOrEqual(1));
    expect(
      screen.queryByText("Finish setup before HAM can use OpenCode.", { exact: false }),
    ).toBeNull();
    expect(screen.queryByRole("button", { name: "Finish setup" })).toBeNull();
  });

  it("shows Ready OpenCode details without stale setup or model-access copy", async () => {
    vi.mocked(listHamProjects).mockResolvedValueOnce({
      projects: [{ id: "project_1", workspace_id: "ws_1" }],
    } as Awaited<ReturnType<typeof listHamProjects>>);
    fetchSettingsMock.mockResolvedValue({
      ok: true,
      settings: settings({ selected_builder: "opencode" }),
    });
    renderBuildersSection();
    fireEvent.click(await screen.findByRole("button", { name: "Open details for OpenCode" }));
    const dialog = await screen.findByRole("dialog", { name: "OpenCode" });
    expect(dialog).toHaveTextContent("Ready");
    expect(dialog).toHaveTextContent("HAM will use OpenCode when you ask it to build.");
    expect(dialog).not.toHaveTextContent("Finish setup");
    expect(dialog).not.toHaveTextContent("Configure model access");
    expect(dialog).not.toHaveTextContent("Requires");
    expect(dialog).not.toHaveTextContent("Safe next step");
  });

  it("shows Finish setup in OpenCode details when selected OpenCode is not build-ready", async () => {
    fetchSettingsMock.mockResolvedValue({
      ok: true,
      settings: settings({ selected_builder: "opencode" }),
    });
    renderBuildersSection();
    fireEvent.click(await screen.findByRole("button", { name: "Open details for OpenCode" }));
    const dialog = await screen.findByRole("dialog", { name: "OpenCode" });
    expect(dialog).toHaveTextContent("Finish setup before HAM can use OpenCode for builds.");
    const buttons = screen.getAllByRole("button", { name: "Finish setup" });
    expect(buttons.length).toBeGreaterThanOrEqual(1);
  });

  it("details Finish setup calls the same OpenCode setup flow as the row", async () => {
    fetchSettingsMock.mockResolvedValue({
      ok: true,
      settings: settings({ selected_builder: "opencode" }),
    });
    renderBuildersSection();
    fireEvent.click(await screen.findByRole("button", { name: "Open details for OpenCode" }));
    const buttons = await screen.findAllByRole("button", { name: "Finish setup" });
    fireEvent.click(buttons[buttons.length - 1]);
    await waitFor(() => expect(ensureBuilderDefaultProject).toHaveBeenCalledWith("ws_1"));
  });

  it("does not show Hermes as a coming-soon builder", async () => {
    renderBuildersSection();
    await waitFor(() => expect(fetchSettingsMock).toHaveBeenCalled());
    expect(screen.queryByText("Hermes Agent")).toBeNull();
    expect(screen.queryByText(/coming soon/i)).toBeNull();
    expect(screen.queryByText(/Hermes Agent new-build support/i)).toBeNull();
  });

  it("does not render any build launch / approve / preview controls", async () => {
    renderBuildersSection();
    await waitFor(() => expect(fetchSettingsMock).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: /prepare build/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /approve build/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /launch/i })).toBeNull();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("does not expose build-kit internals, env names, or provider ids", async () => {
    fetchSettingsMock.mockResolvedValue({
      ok: true,
      settings: settings({ selected_builder: "opencode" }),
    });
    const { container } = renderBuildersSection();
    await waitFor(() => expect(fetchSettingsMock).toHaveBeenCalled());
    const blob = (container.textContent || "").toLowerCase();
    for (const token of FORBIDDEN) {
      expect(blob, `selector leaks ${token}`).not.toContain(token);
    }
  });

  it("details modal does not expose build-kit internals, env names, or provider ids", async () => {
    vi.mocked(listHamProjects).mockResolvedValueOnce({
      projects: [{ id: "project_1", workspace_id: "ws_1" }],
    } as Awaited<ReturnType<typeof listHamProjects>>);
    fetchSettingsMock.mockResolvedValue({
      ok: true,
      settings: settings({ selected_builder: "opencode" }),
    });
    const { container } = renderBuildersSection();
    fireEvent.click(await screen.findByRole("button", { name: "Open details for OpenCode" }));
    await screen.findByRole("dialog", { name: "OpenCode" });
    const blob = (container.textContent || "").toLowerCase();
    for (const token of FORBIDDEN) {
      expect(blob, `details leaks ${token}`).not.toContain(token);
    }
  });
});
