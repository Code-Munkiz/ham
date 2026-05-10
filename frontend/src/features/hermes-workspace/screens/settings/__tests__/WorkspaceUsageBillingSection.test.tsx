import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { WorkspaceSettingsScreen } from "../WorkspaceSettingsScreen";

describe("Workspace Usage & Billing settings", () => {
  it("/workspace/settings?section=usage renders title, tabs, plan stub, honest history, and disabled billing actions", () => {
    render(
      <MemoryRouter initialEntries={["/workspace/settings?section=usage"]}>
        <Routes>
          <Route path="/workspace/settings" element={<WorkspaceSettingsScreen />} />
        </Routes>
      </MemoryRouter>,
    );

    const root = screen.getByTestId("hww-usage-billing-root");
    expect(within(root).getByRole("heading", { name: /Usage & Billing/i })).toBeInTheDocument();
    expect(
      within(root).getByText(/Track workspace usage, credits, and upcoming metering surfaces\./),
    ).toBeInTheDocument();

    expect(within(root).getByRole("tab", { name: /^Tasks$/ })).toHaveAttribute("aria-selected", "true");

    expect(within(root).getByText(/^HAM Preview$/)).toBeInTheDocument();
    expect(within(root).getByText(/^Preview$/)).toBeInTheDocument();

    const manage = within(root).getByRole("button", { name: /^Manage/ });
    expect(manage).toBeDisabled();
    const upgrade = within(root).getByRole("button", { name: /^Upgrade/ });
    expect(upgrade).toBeDisabled();

    expect(within(root).getByTestId("hww-usage-history-empty")).toBeInTheDocument();
    expect(within(root).getByText(/No usage events yet\./)).toBeInTheDocument();
    expect(
      within(root).getByText(/Once metering connects, agent tasks/i),
    ).toBeInTheDocument();
    expect(
      within(root).queryByText(/stripe.*connected.*payment confirmed/i),
    ).not.toBeInTheDocument();
  });

  it("switches category tab content for Apps and Computers", () => {
    render(
      <MemoryRouter initialEntries={["/workspace/settings?section=usage"]}>
        <Routes>
          <Route path="/workspace/settings" element={<WorkspaceSettingsScreen />} />
        </Routes>
      </MemoryRouter>,
    );

    const root = screen.getByTestId("hww-usage-billing-root");
    expect(screen.getByTestId("hww-usage-tab-panel-tasks")).toBeInTheDocument();

    fireEvent.click(within(root).getByRole("tab", { name: /^Apps$/ }));
    expect(within(root).getByRole("tab", { name: /^Apps$/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("hww-usage-tab-panel-apps")).toBeInTheDocument();
    expect(screen.queryByTestId("hww-usage-tab-panel-tasks")).not.toBeInTheDocument();

    fireEvent.click(within(root).getByRole("tab", { name: /^Computers$/ }));
    expect(screen.getByTestId("hww-usage-tab-panel-computers")).toBeInTheDocument();
    expect(screen.queryByTestId("hww-usage-tab-panel-apps")).not.toBeInTheDocument();
  });
});
