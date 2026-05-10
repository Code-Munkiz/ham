import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const { fetchWorkspaceToolsMock, isLocalRuntimeConfiguredMock } = vi.hoisted(() => ({
  fetchWorkspaceToolsMock: vi.fn(),
  isLocalRuntimeConfiguredMock: vi.fn(() => false),
}));

vi.mock("@/lib/ham/api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/ham/api")>();
  return {
    ...mod,
    fetchWorkspaceTools: (...args: unknown[]) => fetchWorkspaceToolsMock(...args),
  };
});

vi.mock("../../adapters/localRuntime", () => ({
  isLocalRuntimeConfigured: () => isLocalRuntimeConfiguredMock(),
}));

vi.mock("../../screens/terminal/WorkspaceTerminalView", () => ({
  WorkspaceTerminalView: () => <div data-testid="hww-terminal-surface-mock" />,
}));

import { WorkspaceWorkbench } from "../WorkspaceWorkbench";

function toolsOk() {
  return new Response(
    JSON.stringify({
      tools: [{ id: "github", connection: "off" }],
      scan_available: true,
      scan_hint: null,
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
}

describe("WorkspaceWorkbench", () => {
  beforeEach(() => {
    fetchWorkspaceToolsMock.mockResolvedValue(toolsOk());
    isLocalRuntimeConfiguredMock.mockReturnValue(false);
  });

  it("select Preview by default and switches panel content", () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("hww-workbench-panel-preview")).toBeInTheDocument();
    expect(screen.getByTestId("hww-workbench-tab-preview").getAttribute("data-active")).toBe(
      "true",
    );

    fireEvent.click(screen.getByTestId("hww-workbench-tab-code"));
    expect(screen.getByTestId("hww-workbench-panel-code")).toBeInTheDocument();
    expect(screen.getByTestId("hww-workbench-tab-code").getAttribute("data-active")).toBe("true");
  });

  it("Share and Publish are disabled (not wired)", () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("hww-workbench-share")).toBeDisabled();
    expect(screen.getByTestId("hww-workbench-publish")).toBeDisabled();
  });

  it("placeholders avoid claiming live preview or database connections", () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench />
      </MemoryRouter>,
    );
    expect(screen.getByText(/No preview yet/i)).toBeInTheDocument();
    expect(screen.getByText(/not wired in this shell/i)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("hww-workbench-tab-database"));
    expect(screen.getByText(/not available in this placeholder/i)).toBeInTheDocument();

    expect(screen.queryByTestId("hww-workbench-tab-github")).toBeNull();

    fireEvent.click(screen.getByTestId("hww-workbench-tab-terminal"));
    expect(screen.getByText(/Terminal requires a connected runtime/i)).toBeInTheDocument();
    expect(screen.queryByTestId("hww-workbench-terminal-embed")).toBeNull();

    fireEvent.click(screen.getByTestId("hww-workbench-tab-settings"));
    const settingsPanel = screen.getByTestId("hww-workbench-panel-settings");
    expect(settingsPanel).toBeInTheDocument();
    expect(settingsPanel.textContent).toMatch(/Connected tools/);
    expect(
      screen.getByText(/Use Connected Tools for Git-related integration/i),
    ).toBeInTheDocument();
  });

  it("embeds the terminal surface when a local runtime is configured", () => {
    isLocalRuntimeConfiguredMock.mockReturnValue(true);
    render(
      <MemoryRouter>
        <WorkspaceWorkbench />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("hww-workbench-tab-terminal"));
    expect(screen.getByTestId("hww-workbench-terminal-embed")).toBeInTheDocument();
    expect(screen.getByTestId("hww-terminal-surface-mock")).toBeInTheDocument();
  });

  it("Add project source opens shared dialog from code and storage tabs", async () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench />
      </MemoryRouter>,
    );
    for (const tab of ["code", "storage"] as const) {
      fireEvent.click(screen.getByTestId(`hww-workbench-tab-${tab}`));
      const buttons = screen.getAllByTestId("hww-add-project-source");
      expect(buttons.length).toBe(1);
      fireEvent.click(buttons[0]!);
      expect(await screen.findByTestId("hww-project-source-dialog")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Close" }));
      await waitFor(() => {
        expect(screen.queryByTestId("hww-project-source-dialog")).not.toBeInTheDocument();
      });
    }
  });
});
