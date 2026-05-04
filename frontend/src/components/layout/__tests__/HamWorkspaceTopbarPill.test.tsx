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
    hostedAuth: null,
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
      screen.getByRole("dialog", { name: /workspace unavailable/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Workspace unavailable")).toBeInTheDocument();
    expect(
      screen.getByText(
        "HAM could not load your workspace. Sign in again or contact your workspace admin.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("HAM_LOCAL_DEV_WORKSPACE_BYPASS=true")).not.toBeInTheDocument();
  });

  it("calls refresh from the setup-needed details", () => {
    const refresh = vi.fn(async () => undefined);
    mockUseHamWorkspace.mockReturnValue(baseCtx({ refresh }));

    render(<HamWorkspaceTopbarPill />);
    fireEvent.click(screen.getByRole("button", { name: /setup needed/i }));
    fireEvent.click(screen.getByRole("button", { name: /refresh/i }));

    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("points auth-required details toward sign-in", () => {
    const openSignIn = vi.fn();
    mockUseHamWorkspace.mockReturnValue(
      baseCtx({
        state: { status: "auth_required" },
        hostedAuth: { clerkConfigured: true, isLoaded: true, isSignedIn: false },
        openSignIn,
      }),
    );

    render(<HamWorkspaceTopbarPill />);
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(screen.getByText("Sign in required")).toBeInTheDocument();
    expect(
      screen.getByText("Please sign in to load your HAM workspace."),
    ).toBeInTheDocument();
    const signInButtons = screen.getAllByRole("button", { name: /^sign in$/i });
    fireEvent.click(signInButtons[signInButtons.length - 1]);
    expect(openSignIn).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: /refresh/i })).toBeInTheDocument();
  });

  it("shows auth-not-configured details without a sign-in button", () => {
    mockUseHamWorkspace.mockReturnValue(
      baseCtx({
        state: { status: "auth_not_configured" },
        hostedAuth: { clerkConfigured: false, isLoaded: true, isSignedIn: false },
      }),
    );

    render(<HamWorkspaceTopbarPill />);
    fireEvent.click(screen.getByRole("button", { name: /auth not configured/i }));

    expect(screen.getByText("Authentication is not configured")).toBeInTheDocument();
    expect(
      screen.getByText("Set VITE_CLERK_PUBLISHABLE_KEY and redeploy."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^sign in$/i })).not.toBeInTheDocument();
  });
});
