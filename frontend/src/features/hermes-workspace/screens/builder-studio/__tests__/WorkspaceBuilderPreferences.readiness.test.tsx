import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "@/lib/ham/api";
import * as codingAgentsAdapter from "@/features/hermes-workspace/adapters/codingAgentsAdapter";
import { CODING_AGENT_LABELS } from "@/features/hermes-workspace/screens/coding-agents/codingAgentLabels";
import { MemoryRouter } from "react-router-dom";
import { WorkspaceBuilderPreferences } from "../WorkspaceBuilderPreferences";

let codingSnapSpy: ReturnType<typeof vi.spyOn>;

function renderConnections() {
  return render(
    <MemoryRouter>
      <WorkspaceBuilderPreferences workspaceId="ws_1" />
    </MemoryRouter>,
  );
}

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
  vi.spyOn(api, "listHamProjects").mockResolvedValue({ projects: [] });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("WorkspaceBuilderPreferences builder connections", () => {
  it("lists Claude, Cursor, Factory Droid, and OpenCode without router checkboxes or native select", async () => {
    renderConnections();

    await waitFor(() => {
      expect(screen.getByText(CODING_AGENT_LABELS.builderConnectionsTitle)).toBeInTheDocument();
    });

    expect(screen.getByRole("heading", { name: "Claude" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Cursor" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Factory Droid" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "OpenCode" })).toBeInTheDocument();

    expect(document.querySelector("input[type='checkbox']")).toBeNull();
    expect(document.querySelector("select")).toBeNull();
  });

  it("shows Claude as ready when the snapshot reports claude_agent available", async () => {
    renderConnections();

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Claude" })).toBeInTheDocument();
    });

    const claudeHeading = screen.getByRole("heading", { name: "Claude" });
    const row = claudeHeading.closest("li");
    expect(row).toBeTruthy();
    expect(within(row as HTMLElement).getByText("Ready")).toBeInTheDocument();
  });

  it("does not present legacy Claude Code as a user-facing lane", async () => {
    codingSnapSpy.mockResolvedValue({
      opencode: "ready",
      claudeAgent: "needs_setup",
    });

    renderConnections();

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "OpenCode" })).toBeInTheDocument();
    });

    expect(screen.queryByText(/Claude Code/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Local editor")).not.toBeInTheDocument();
  });

  it("opens a builder-specific detail panel with distinct primary CTAs for each row", async () => {
    renderConnections();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Open details for Claude/i })).toBeInTheDocument();
    });

    for (const { name, primary, goodForSnippet } of [
      {
        name: /Open details for Claude/i,
        primary: CODING_AGENT_LABELS.builderPanelPrimaryManageClaude,
        goodForSnippet: "Complex edits",
      },
      {
        name: /Open details for Cursor/i,
        primary: CODING_AGENT_LABELS.builderPanelPrimaryManageCursor,
        goodForSnippet: "Repo-connected",
      },
      {
        name: /Open details for Factory Droid/i,
        primary: CODING_AGENT_LABELS.builderPanelPrimarySetupRunner,
        goodForSnippet: "Deterministic",
      },
    ] as const) {
      fireEvent.click(screen.getByRole("button", { name }));
      const dialog = await screen.findByRole("dialog");
      expect(
        within(dialog).getByText(CODING_AGENT_LABELS.builderPanelGoodForHeading),
      ).toBeInTheDocument();
      expect(within(dialog).getByText(goodForSnippet, { exact: false })).toBeInTheDocument();
      expect(within(dialog).getByRole("link", { name: primary })).toBeInTheDocument();
      expect(
        within(dialog).getByRole("link", {
          name: CODING_AGENT_LABELS.builderPanelSecondaryConnectedTools,
        }),
      ).toBeInTheDocument();
      fireEvent.keyDown(document, { key: "Escape", code: "Escape" });
      await waitFor(() => {
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      });
    }

    fireEvent.click(screen.getByRole("button", { name: /Open details for OpenCode/i }));
    const opencodeDialog = await screen.findByRole("dialog");
    expect(within(opencodeDialog).getByText("Managed workspace builds")).toBeInTheDocument();
    expect(
      within(opencodeDialog).getByRole("link", {
        name: CODING_AGENT_LABELS.actionConfigureModelAccess,
      }),
    ).toBeInTheDocument();
    expect(
      within(opencodeDialog).getByRole("link", {
        name: CODING_AGENT_LABELS.builderPanelSecondaryOpenModelSettings,
      }),
    ).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape", code: "Escape" });
    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("lists Open model settings as a secondary link only for OpenCode", async () => {
    renderConnections();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Open details for OpenCode/i }),
      ).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Open details for OpenCode/i }));
    const dialog = await screen.findByRole("dialog");
    expect(
      within(dialog).getByRole("link", {
        name: CODING_AGENT_LABELS.builderPanelSecondaryOpenModelSettings,
      }),
    ).toBeInTheDocument();
    expect(
      within(dialog).queryByRole("link", {
        name: CODING_AGENT_LABELS.builderPanelSecondaryConnectedTools,
      }),
    ).not.toBeInTheDocument();
  });
});
