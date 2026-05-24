import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("../workspaceLibraryFlyoutContext", () => ({
  useWorkspaceLibraryFlyout: () => ({
    openLibrary: vi.fn(),
    toggleLibrary: vi.fn(),
    libraryOpen: false,
  }),
}));

import { WorkspaceMobileTabBar } from "../WorkspaceMobileTabBar";

describe("WorkspaceMobileTabBar", () => {
  it("omits Chat from mobile primary links and exposes library", () => {
    render(
      <MemoryRouter initialEntries={["/workspace/projects"]}>
        <WorkspaceMobileTabBar />
      </MemoryRouter>,
    );

    expect(screen.queryByRole("link", { name: "Chat" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Social" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /HAMgomoon/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open library" })).toBeInTheDocument();
  });
});
