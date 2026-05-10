import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

  it("embedded settings lists integrations with connect UI", async () => {
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
    expect(screen.queryByTestId("hww-workbench-tab-terminal")).toBeNull();

    fireEvent.click(screen.getByTestId("hww-workbench-tab-storage"));
    const storagePanel = screen.getByTestId("hww-workbench-panel-storage");
    expect(within(storagePanel).getByTestId("hww-add-project-source")).toBeInTheDocument();
    expect(screen.getByText(/No cloud project blob store yet/i)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("hww-workbench-tab-settings"));
    const settingsPanel = screen.getByTestId("hww-workbench-panel-settings");
    expect(settingsPanel).toBeInTheDocument();
    expect(screen.getByTestId("hww-workbench-settings-nav-models")).toBeInTheDocument();
    expect(screen.getByText(/No project pinned/i)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("hww-workbench-settings-nav-integrations"));
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Connected tools" })).toBeInTheDocument();
    });
  });

  it("Workbench settings Usage links to full-screen Usage & Billing with optional project_id", () => {
    render(
      <MemoryRouter initialEntries={["/workspace/chat"]}>
        <WorkspaceWorkbench projectId="proj_abc" />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("hww-workbench-tab-settings"));
    fireEvent.click(screen.getByTestId("hww-workbench-settings-nav-usage"));
    const usageLink = screen.getByTestId("hww-workbench-usage-full-settings");
    expect(usageLink).toHaveAttribute(
      "href",
      "/workspace/settings?section=usage&project_id=proj_abc",
    );
  });

  it("does not expose a workbench Terminal tab", () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId("hww-workbench-tab-terminal")).toBeNull();
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
