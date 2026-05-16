import type { ReactElement } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const { mockUseHamWorkspace } = vi.hoisted(() => ({
  mockUseHamWorkspace: vi.fn(),
}));

vi.mock("@/lib/ham/HamWorkspaceContext", () => ({
  useHamWorkspace: mockUseHamWorkspace,
}));

vi.mock("@/components/workspace/WorkspacePicker", () => ({
  WorkspacePicker: ({ open }: { open: boolean }) => (
    <div data-testid="workspace-picker-mock" data-open={String(open)} />
  ),
}));

vi.mock("@/components/workspace/WorkspaceCreateWorkspaceDialog", () => ({
  WorkspaceCreateWorkspaceDialog: ({
    open,
    onCreated,
  }: {
    open: boolean;
    onCreated?: (workspace: { workspace_id: string }) => void;
  }) =>
    open ? (
      <div data-testid="ham-workspace-create-dialog">
        <button
          type="button"
          data-testid="mock-create-success"
          onClick={() => onCreated?.({ workspace_id: "ws_new" })}
        >
          Finish create
        </button>
      </div>
    ) : null,
}));

import { HamWorkspaceTopbarPill } from "@/components/layout/HamWorkspaceTopbarPill";
import type { HamWorkspaceContextValue } from "@/lib/ham/HamWorkspaceContext";
import type { HamWorkspaceRole, HamWorkspaceSummary } from "@/lib/ham/workspaceApi";

function ws(id: string, name: string, role: HamWorkspaceRole = "owner"): HamWorkspaceSummary {
  return {
    workspace_id: id,
    org_id: null,
    name,
    slug: name.toLowerCase().replace(/\s+/g, "-"),
    description: "",
    status: "active",
    role,
    perms: [],
    is_default: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function baseCtx(overrides: Partial<HamWorkspaceContextValue> = {}): HamWorkspaceContextValue {
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
    archiveWorkspaceById: vi.fn(),
    hasPerm: vi.fn(() => false),
    ...overrides,
  };
}

function readyCtx(activeId: string, rows: HamWorkspaceSummary[]): HamWorkspaceContextValue {
  const active = rows.find((w) => w.workspace_id === activeId) ?? null;
  return baseCtx({
    state: {
      status: "ready",
      me: {
        user: {
          user_id: "u_alice",
          email: "alice@example.com",
          display_name: null,
          photo_url: null,
          primary_org_id: null,
        },
        orgs: [],
        workspaces: rows,
        default_workspace_id: activeId,
        auth_mode: "clerk",
      },
      activeWorkspaceId: activeId,
    },
    workspaces: rows,
    active,
    hostedAuth: { clerkConfigured: true, isLoaded: true, isSignedIn: true },
  });
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.clearAllMocks();
});

function renderWithRouter(ui: ReactElement, initialEntries: string[] = ["/"]) {
  return render(<MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>);
}

function PathProbe() {
  const loc = useLocation();
  return <span data-testid="pathname-probe">{loc.pathname}</span>;
}

function renderPillWithPath(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route
          path="*"
          element={
            <>
              <HamWorkspaceTopbarPill />
              <PathProbe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

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

    renderWithRouter(<HamWorkspaceTopbarPill />);

    const pill = screen.getByTestId("ham-workspace-pill");
    expect(pill).toHaveTextContent("Setup needed");
    expect(pill.className).toContain("text-amber-50");
  });

  it("opens setup-needed details with hosted-safe copy and no developer details by default", () => {
    mockUseHamWorkspace.mockReturnValue(baseCtx());

    renderWithRouter(<HamWorkspaceTopbarPill />);
    fireEvent.click(screen.getByRole("button", { name: /setup needed/i }));

    expect(screen.getByRole("dialog", { name: /workspace unavailable/i })).toBeInTheDocument();
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

    renderWithRouter(<HamWorkspaceTopbarPill />);
    fireEvent.click(screen.getByRole("button", { name: /setup needed/i }));
    fireEvent.click(screen.getByRole("button", { name: /refresh/i }));

    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("offers sign-in recovery from setup-needed details when Clerk is configured", () => {
    const openSignIn = vi.fn();
    mockUseHamWorkspace.mockReturnValue(
      baseCtx({
        hostedAuth: { clerkConfigured: true, isLoaded: true, isSignedIn: false },
        openSignIn,
      }),
    );

    renderWithRouter(<HamWorkspaceTopbarPill />);
    fireEvent.click(screen.getByRole("button", { name: /setup needed/i }));
    fireEvent.click(screen.getByRole("button", { name: /^sign in$/i }));

    expect(openSignIn).toHaveBeenCalledTimes(1);
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

    renderWithRouter(<HamWorkspaceTopbarPill />);
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    expect(screen.getByText("Sign in required")).toBeInTheDocument();
    expect(screen.getByText("Please sign in to load your HAM workspace.")).toBeInTheDocument();
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

    renderWithRouter(<HamWorkspaceTopbarPill />);
    fireEvent.click(screen.getByRole("button", { name: /auth not configured/i }));

    expect(screen.getByText("Authentication is not configured")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Workspace sign-in is temporarily unavailable. Refresh or contact your workspace admin.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^sign in$/i })).not.toBeInTheDocument();
    expectNoHostedUnsafeCopy();
  });

  it("keeps developer details hidden unless local-dev hints are explicitly enabled", () => {
    mockUseHamWorkspace.mockReturnValue(baseCtx());

    renderWithRouter(<HamWorkspaceTopbarPill />);
    fireEvent.click(screen.getByRole("button", { name: /setup needed/i }));

    expect(screen.queryByText("Developer details")).not.toBeInTheDocument();

    vi.stubEnv("VITE_HAM_SHOW_LOCAL_DEV_HINTS", "true");
    mockUseHamWorkspace.mockReturnValue(baseCtx());

    renderWithRouter(<HamWorkspaceTopbarPill />);
    const setupButtons = screen.getAllByRole("button", { name: /setup needed/i });
    fireEvent.click(setupButtons[setupButtons.length - 1]);

    expect(screen.getByText("Developer details")).toBeInTheDocument();
    expect(screen.getByText(/HAM_LOCAL_DEV_WORKSPACE_BYPASS=true/)).toBeInTheDocument();
  });
});

describe("HamWorkspaceTopbarPill ready workspace", () => {
  it("shows compact create control with a11y labels and no owner badge in the active pill", () => {
    mockUseHamWorkspace.mockReturnValue(readyCtx("ws_a", [ws("ws_a", "ham repo", "owner")]));

    renderWithRouter(<HamWorkspaceTopbarPill />);

    const createBtn = screen.getByTestId("ham-workspace-pill-create");
    expect(createBtn).toHaveAttribute("aria-label", "Create workspace");
    expect(createBtn).toHaveAttribute("title", "Create workspace");

    const group = screen.getByRole("group", { name: /active workspace/i });
    expect(within(group).getByTestId("ham-workspace-pill")).toHaveTextContent("ham repo");
    expect(within(group).queryByText(/^owner$/i)).not.toBeInTheDocument();
  });

  it("toggles workspace picker from the main pill segment only", () => {
    mockUseHamWorkspace.mockReturnValue(
      readyCtx("ws_a", [ws("ws_a", "Alpha"), ws("ws_b", "Beta")]),
    );

    renderWithRouter(<HamWorkspaceTopbarPill />);

    fireEvent.click(screen.getByTestId("ham-workspace-pill"));
    expect(screen.getByTestId("workspace-picker-mock")).toHaveAttribute("data-open", "true");

    fireEvent.click(screen.getByTestId("ham-workspace-pill"));
    expect(screen.getByTestId("workspace-picker-mock")).toHaveAttribute("data-open", "false");
  });

  it("opens create dialog from + and closes picker without opening picker via + alone", () => {
    mockUseHamWorkspace.mockReturnValue(
      readyCtx("ws_a", [ws("ws_a", "Alpha"), ws("ws_b", "Beta")]),
    );

    renderWithRouter(<HamWorkspaceTopbarPill />);

    fireEvent.click(screen.getByTestId("ham-workspace-pill"));
    expect(screen.getByTestId("workspace-picker-mock")).toHaveAttribute("data-open", "true");

    fireEvent.click(screen.getByTestId("ham-workspace-pill-create"));
    expect(screen.getByTestId("workspace-picker-mock")).toHaveAttribute("data-open", "false");
    expect(screen.getByTestId("ham-workspace-create-dialog")).toBeInTheDocument();
  });

  it("does not open picker when clicking + while picker is closed", () => {
    mockUseHamWorkspace.mockReturnValue(
      readyCtx("ws_a", [ws("ws_a", "Alpha"), ws("ws_b", "Beta")]),
    );

    renderWithRouter(<HamWorkspaceTopbarPill />);

    fireEvent.click(screen.getByTestId("ham-workspace-pill-create"));
    expect(screen.getByTestId("workspace-picker-mock")).toHaveAttribute("data-open", "false");
    expect(screen.getByTestId("ham-workspace-create-dialog")).toBeInTheDocument();
  });

  it("navigates to /workspace/chat after mocked successful create", () => {
    mockUseHamWorkspace.mockReturnValue(
      readyCtx("ws_a", [ws("ws_a", "Alpha"), ws("ws_b", "Beta")]),
    );

    renderPillWithPath("/workspace/settings");

    fireEvent.click(screen.getByTestId("ham-workspace-pill-create"));
    fireEvent.click(screen.getByTestId("mock-create-success"));

    expect(screen.getByTestId("pathname-probe")).toHaveTextContent("/workspace/chat");
  });
});
