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
  vi.unstubAllEnvs();
  vi.clearAllMocks();
});

function expectNoHostedUnsafeCopy() {
  const html = document.body.innerHTML;
  expect(html).not.toMatch(/local API/i);
  expect(html).not.toMatch(/uvicorn/i);
  expect(html).not.toMatch(/127\.0\.0\.1/);
  expect(html).not.toMatch(/HAM_[A-Z0-9_]+/);
  expect(html).not.toMatch(/VITE_[A-Z0-9_]+/);
  expect(html).not.toMatch(/Cloud Run|Vercel config/i);
}

describe("HamWorkspaceTopbarPill", () => {
  it("renders high-contrast setup-needed copy", () => {
    mockUseHamWorkspace.mockReturnValue(baseCtx());

    render(<HamWorkspaceTopbarPill />);

    const pill = screen.getByTestId("ham-workspace-pill");
    expect(pill).toHaveTextContent("Setup needed");
    expect(pill.className).toContain("text-amber-50");
  });

  it("opens setup-needed details with hosted-safe copy and no developer details by default", () => {
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
    expect(screen.queryByText("Developer details")).not.toBeInTheDocument();
    expectNoHostedUnsafeCopy();
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

  it("shows auth-not-configured details with product-safe copy and no sign-in button", () => {
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
      screen.getByText("Workspace sign-in is temporarily unavailable. Refresh or contact your workspace admin."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^sign in$/i })).not.toBeInTheDocument();
    expectNoHostedUnsafeCopy();
  });

  it("keeps developer details hidden unless local-dev hints are explicitly enabled", () => {
    mockUseHamWorkspace.mockReturnValue(baseCtx());

    render(<HamWorkspaceTopbarPill />);
    fireEvent.click(screen.getByRole("button", { name: /setup needed/i }));

    expect(screen.queryByText("Developer details")).not.toBeInTheDocument();

    vi.stubEnv("VITE_HAM_SHOW_LOCAL_DEV_HINTS", "true");
    mockUseHamWorkspace.mockReturnValue(baseCtx());

    render(<HamWorkspaceTopbarPill />);
    const setupButtons = screen.getAllByRole("button", { name: /setup needed/i });
    fireEvent.click(setupButtons[setupButtons.length - 1]);

    expect(screen.getByText("Developer details")).toBeInTheDocument();
    expect(screen.getByText(/HAM_LOCAL_DEV_WORKSPACE_BYPASS=true/)).toBeInTheDocument();
  });
});
