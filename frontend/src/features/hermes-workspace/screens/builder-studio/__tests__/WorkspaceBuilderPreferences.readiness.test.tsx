import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/ham/api";
import * as codingAgentsAdapter from "@/features/hermes-workspace/adapters/codingAgentsAdapter";
import { WorkspaceBuilderPreferences } from "../WorkspaceBuilderPreferences";

let codingSnapSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.spyOn(codingAgentsAdapter, "fetchCursorReadiness").mockResolvedValue({
    readiness: "ready",
    status: null,
    error: null,
  });
  codingSnapSpy = vi.spyOn(codingAgentsAdapter, "fetchCodingReadinessSnapshot").mockResolvedValue({
    opencode: "needs_setup",
    claudeAgent: "ready",
  });
  vi.spyOn(codingAgentsAdapter, "fetchCodingAgentAccessSettings").mockResolvedValue({
    ok: true,
    settings: {
      ...codingAgentsAdapter.DEFAULT_CODING_AGENT_SETTINGS,
      workspace_id: "ws_1",
    },
  });
  vi.spyOn(codingAgentsAdapter, "patchCodingAgentAccessSettings").mockResolvedValue({
    ok: false,
    errorMessage: "unused in test",
  });
  vi.spyOn(api, "listHamProjects").mockResolvedValue({ projects: [] });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("WorkspaceBuilderPreferences readiness row", () => {
  it("shows Premium reasoning builder as ready when the snapshot reports claude_agent available", async () => {
    render(<WorkspaceBuilderPreferences workspaceId="ws_1" />);

    await waitFor(() => {
      expect(screen.getByText("Premium reasoning builder")).toBeInTheDocument();
    });

    const premiumHeading = screen.getByText("Premium reasoning builder");
    const row = premiumHeading.parentElement;
    expect(row).toBeTruthy();
    expect(within(row as HTMLElement).getByText("Ready")).toBeInTheDocument();
  });

  it("does not present legacy Claude Code as a user-facing readiness lane", async () => {
    codingSnapSpy.mockResolvedValue({
      opencode: "ready",
      claudeAgent: "needs_setup",
    });

    render(<WorkspaceBuilderPreferences workspaceId="ws_1" />);

    await waitFor(() => {
      expect(screen.getByText("OpenCode")).toBeInTheDocument();
    });

    expect(screen.queryByText(/Claude Code/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Local editor")).not.toBeInTheDocument();
  });
});
