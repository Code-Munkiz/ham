import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { mockUseHamWorkspace } = vi.hoisted(() => ({
  mockUseHamWorkspace: vi.fn(),
}));

vi.mock("@/lib/ham/HamWorkspaceContext", () => ({
  useHamWorkspace: mockUseHamWorkspace,
}));

import { HamWorkspaceTopbarPill } from "@/components/layout/HamWorkspaceTopbarPill";
import type { HamWorkspaceContextValue } from "@/lib/ham/HamWorkspaceContext";

function baseCtx(
  overrides: Partial<HamWorkspaceContextValue> = {},
): HamWorkspaceContextValue {
  return {
    state: { status: "setup_needed" },
    workspaces: [],
    active: null,
    authMode: null,
    refresh: vi.fn(async () => undefined),
    selectWorkspace: vi.fn(),
    createWorkspace: vi.fn(),
    patchActiveWorkspace: vi.fn(),
    hasPerm: vi.fn(() => false),
    ...overrides,
  };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("HamWorkspaceTopbarPill", () => {
  it("renders high-contrast setup-needed copy", () => {
    mockUseHamWorkspace.mockReturnValue(baseCtx());

    render(<HamWorkspaceTopbarPill />);

    const pill = screen.getByTestId("ham-workspace-pill");
    expect(pill).toHaveTextContent("Setup needed");
    expect(pill.className).toContain("text-amber-50");
  });

  it("opens setup-needed details with local-dev instruction", () => {
    mockUseHamWorkspace.mockReturnValue(baseCtx());

    render(<HamWorkspaceTopbarPill />);
    fireEvent.click(screen.getByRole("button", { name: /setup needed/i }));

    expect(
      screen.getByRole("dialog", { name: /workspace setup needed/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Workspace setup needed")).toBeInTheDocument();
    expect(
      screen.getByText(
        "HAM could not load a workspace because local workspace bypass is not enabled.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("HAM_LOCAL_DEV_WORKSPACE_BYPASS=true"),
    ).toBeInTheDocument();
  });

  it("calls refresh from the setup-needed details", () => {
    const refresh = vi.fn(async () => undefined);
    mockUseHamWorkspace.mockReturnValue(baseCtx({ refresh }));

    render(<HamWorkspaceTopbarPill />);
    fireEvent.click(screen.getByRole("button", { name: /setup needed/i }));
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));

    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("points auth-required details toward sign-in", () => {
    mockUseHamWorkspace.mockReturnValue(baseCtx({ state: { status: "auth_required" } }));

    render(<HamWorkspaceTopbarPill />);
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(screen.getByText("Workspace sign-in needed")).toBeInTheDocument();
    expect(screen.getByText(/Sign in, then retry/i)).toBeInTheDocument();
  });
});
