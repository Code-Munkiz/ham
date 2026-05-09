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
  it("omits Chat from mobile primary links", () => {
    render(
      <MemoryRouter initialEntries={["/workspace/social"]}>
        <WorkspaceMobileTabBar />
      </MemoryRouter>,
    );

    expect(screen.queryByRole("link", { name: "Chat" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Social" })).toHaveAttribute(
      "href",
      "/workspace/social",
    );
  });
});
