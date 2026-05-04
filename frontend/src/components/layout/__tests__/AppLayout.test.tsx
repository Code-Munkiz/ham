import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/ham/desktopConfig", () => ({
  isHamDesktopShell: () => false,
}));

import { AppLayout } from "@/components/layout/AppLayout";

describe("AppLayout", () => {
  it("does not render the workspace pill on the bare landing route", () => {
    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppLayout>
          <main>Landing content</main>
        </AppLayout>
      </MemoryRouter>,
    );

    expect(screen.getByText("Landing content")).toBeInTheDocument();
    expect(screen.queryByTestId("ham-workspace-pill")).toBeNull();
  });
});
