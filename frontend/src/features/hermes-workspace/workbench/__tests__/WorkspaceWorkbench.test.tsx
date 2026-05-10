import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { WorkspaceWorkbench } from "../WorkspaceWorkbench";

describe("WorkspaceWorkbench", () => {
  it("select Preview by default and switches panel content", () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench />
      </MemoryRouter>,
    );
    expect(screen.getByTestId("hww-workbench-panel-preview")).toBeInTheDocument();
    expect(
      screen.getByTestId("hww-workbench-tab-preview").getAttribute("data-active"),
    ).toBe("true");

    fireEvent.click(screen.getByTestId("hww-workbench-tab-code"));
    expect(screen.getByTestId("hww-workbench-panel-code")).toBeInTheDocument();
    expect(
      screen.getByTestId("hww-workbench-tab-code").getAttribute("data-active"),
    ).toBe("true");
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

  it("placeholders avoid claiming live or connected behavior", () => {
    render(
      <MemoryRouter>
        <WorkspaceWorkbench />
      </MemoryRouter>,
    );
    expect(screen.getByText(/No preview yet/i)).toBeInTheDocument();
    expect(screen.getByText(/not wired in this shell/i)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("hww-workbench-tab-database"));
    expect(screen.getByText(/not available in this placeholder/i)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("hww-workbench-tab-github"));
    expect(screen.getByText(/placeholders only/i)).toBeInTheDocument();
  });
});
