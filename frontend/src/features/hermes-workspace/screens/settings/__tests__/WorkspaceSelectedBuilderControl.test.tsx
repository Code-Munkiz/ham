import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { fetchSettingsMock, patchSettingsMock, readinessMock } = vi.hoisted(() => ({
  fetchSettingsMock: vi.fn(),
  patchSettingsMock: vi.fn(),
  readinessMock: vi.fn(),
}));

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
  };
});

import { WorkspaceSelectedBuilderControl } from "../WorkspaceSelectedBuilderControl";
import { DEFAULT_CODING_AGENT_SETTINGS } from "@/features/hermes-workspace/adapters/codingAgentsAdapter";

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

beforeEach(() => {
  readinessMock.mockResolvedValue({ opencode: "ready", claudeAgent: "needs_setup" });
  fetchSettingsMock.mockResolvedValue({ ok: true, settings: settings() });
  patchSettingsMock.mockImplementation(async (_ws: string, patch: Record<string, unknown>) => ({
    ok: true,
    settings: settings(patch),
  }));
});

afterEach(() => {
  vi.restoreAllMocks();
  fetchSettingsMock.mockReset();
  patchSettingsMock.mockReset();
  readinessMock.mockReset();
});

describe("WorkspaceSelectedBuilderControl", () => {
  it("renders the Builder selector with the five product-facing options", async () => {
    render(<WorkspaceSelectedBuilderControl workspaceId="ws_1" />);
    await waitFor(() => expect(fetchSettingsMock).toHaveBeenCalled());
    expect(screen.getByRole("heading", { name: "Builder" })).toBeInTheDocument();
    expect(
      screen.getByText("Choose which builder HAM uses for normal builds."),
    ).toBeInTheDocument();
    for (const name of ["OpenCode", "Factory Droid", "Cursor", "Claude", "Hermes Agent"]) {
      expect(screen.getByRole("radio", { name })).toBeInTheDocument();
    }
  });

  it("loads the current selected_builder from the API", async () => {
    fetchSettingsMock.mockResolvedValue({
      ok: true,
      settings: settings({ selected_builder: "factory_droid" }),
    });
    render(<WorkspaceSelectedBuilderControl workspaceId="ws_1" />);
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "Factory Droid" })).toHaveAttribute(
        "aria-checked",
        "true",
      ),
    );
  });

  it("PATCHes selected_builder=opencode when OpenCode is chosen", async () => {
    render(<WorkspaceSelectedBuilderControl workspaceId="ws_1" />);
    await waitFor(() => expect(fetchSettingsMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("radio", { name: "OpenCode" }));
    await waitFor(() => expect(patchSettingsMock).toHaveBeenCalledTimes(1));
    expect(patchSettingsMock).toHaveBeenCalledWith("ws_1", { selected_builder: "opencode" });
  });

  it("PATCHes selected_builder=factory_droid when Factory Droid is chosen", async () => {
    render(<WorkspaceSelectedBuilderControl workspaceId="ws_1" />);
    await waitFor(() => expect(fetchSettingsMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("radio", { name: "Factory Droid" }));
    await waitFor(() => expect(patchSettingsMock).toHaveBeenCalledTimes(1));
    expect(patchSettingsMock).toHaveBeenCalledWith("ws_1", { selected_builder: "factory_droid" });
  });

  it("shows honest helper copy for Hermes Agent (coming soon)", async () => {
    fetchSettingsMock.mockResolvedValue({
      ok: true,
      settings: settings({ selected_builder: "hermes_agent" }),
    });
    render(<WorkspaceSelectedBuilderControl workspaceId="ws_1" />);
    await waitFor(() =>
      expect(screen.getByTestId("hww-selected-builder-helper")).toHaveTextContent(
        "Hermes Agent new-build support is coming soon.",
      ),
    );
  });

  it("shows separate-flow helper copy for Cursor", async () => {
    fetchSettingsMock.mockResolvedValue({
      ok: true,
      settings: settings({ selected_builder: "cursor" }),
    });
    render(<WorkspaceSelectedBuilderControl workspaceId="ws_1" />);
    await waitFor(() =>
      expect(screen.getByTestId("hww-selected-builder-helper")).toHaveTextContent(
        "Cursor runs through its own build flow for now.",
      ),
    );
  });

  it("does not render any build launch / approve / preview controls", async () => {
    render(<WorkspaceSelectedBuilderControl workspaceId="ws_1" />);
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
    const { container } = render(<WorkspaceSelectedBuilderControl workspaceId="ws_1" />);
    await waitFor(() => expect(fetchSettingsMock).toHaveBeenCalled());
    const blob = (container.textContent || "").toLowerCase();
    for (const token of FORBIDDEN) {
      expect(blob, `selector leaks ${token}`).not.toContain(token);
    }
  });
});
