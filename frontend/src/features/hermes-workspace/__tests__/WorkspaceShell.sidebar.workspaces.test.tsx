import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

const { mockUseHamWorkspace } = vi.hoisted(() => ({
  mockUseHamWorkspace: vi.fn(),
}));

vi.mock("@/lib/ham/HamWorkspaceContext", () => ({
  useHamWorkspace: mockUseHamWorkspace,
}));

vi.mock("../screens/terminal/WorkspaceTerminalView", () => ({
  WorkspaceTerminalView: () => null,
}));

vi.mock("@/components/workspace/WorkspaceCreateWorkspaceDialog", () => ({
  WorkspaceCreateWorkspaceDialog: ({
    open,
    onOpenChange,
    onCreated,
  }: {
    open: boolean;
    onOpenChange: (v: boolean) => void;
    onCreated?: (w: unknown) => void;
  }) =>
    open ? (
      <div data-testid="ham-workspace-create-dialog">
        <button type="button" onClick={() => onOpenChange(false)}>
          Cancel
        </button>
        <button
          type="button"
          data-testid="mock-shell-create-success"
          onClick={() => {
            onCreated?.({ workspace_id: "ws_new" });
            onOpenChange(false);
          }}
        >
          Finish create
        </button>
      </div>
    ) : null,
}));

import type { HamWorkspaceContextValue } from "@/lib/ham/HamWorkspaceContext";
import type { HamWorkspaceSummary } from "@/lib/ham/workspaceApi";

import { WorkspaceShell } from "../WorkspaceShell";

function ws(id: string, name: string): HamWorkspaceSummary {
  return {
    workspace_id: id,
    org_id: null,
    name,
    slug: name.toLowerCase().replace(/\s+/g, "-"),
    description: "",
    status: "active",
    role: "owner",
    perms: [],
    is_default: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

function baseCtx(overrides: Partial<HamWorkspaceContextValue> = {}): HamWorkspaceContextValue {
  return {
    state: { status: "auth_required" },
    workspaces: [],
    active: null,
    authMode: null,
    hostedAuth: { clerkConfigured: true, isLoaded: true, isSignedIn: false },
    refresh: vi.fn(async () => undefined),
    selectWorkspace: vi.fn(),
    createWorkspace: vi.fn(),
    patchActiveWorkspace: vi.fn(),
    hasPerm: vi.fn(() => false),
    ...overrides,
  };
}

function readyCtx(
  activeId: string,
  workspaceRows: HamWorkspaceSummary[],
): HamWorkspaceContextValue {
  const active = workspaceRows.find((w) => w.workspace_id === activeId) ?? null;
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
        workspaces: workspaceRows,
        default_workspace_id: activeId,
        auth_mode: "clerk",
      },
      activeWorkspaceId: activeId,
    },
    workspaces: workspaceRows,
    active,
    hostedAuth: { clerkConfigured: true, isLoaded: true, isSignedIn: true },
  });
}

function RouteProbe() {
  const loc = useLocation();
  return <span data-testid="shell-route-path">{loc.pathname}</span>;
}

function renderShell(initialPath = "/workspace/chat") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <>
        <RouteProbe />
        <WorkspaceShell>
          <div>workspace child</div>
        </WorkspaceShell>
      </>
    </MemoryRouter>,
  );
}

describe("WorkspaceShell workspace sidebar", () => {
  beforeEach(() => {
    localStorage.setItem("hww.sidebar.collapsed", "0");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("omits Chat from the primary rail", async () => {
    mockUseHamWorkspace.mockReturnValue(
      readyCtx("ws_a", [ws("ws_a", "Alpha"), ws("ws_b", "Beta")]),
    );
    renderShell();

    await waitFor(() => expect(screen.getByText("workspace child")).toBeInTheDocument());

    const primary = screen.getByRole("navigation", { name: "Workspace primary" });
    expect(primary.querySelector('a[href="/workspace/chat"]')).toBeNull();
    expect(screen.queryByRole("link", { name: "Chat" })).not.toBeInTheDocument();
  });

  it("shows workspace search, list, and pill create control when expanded (no full-width New workspace)", async () => {
    mockUseHamWorkspace.mockReturnValue(
      readyCtx("ws_a", [ws("ws_a", "Alpha"), ws("ws_b", "Beta")]),
    );
    renderShell();

    await waitFor(() => expect(screen.getByText("workspace child")).toBeInTheDocument());

    const search = await screen.findByTestId("hww-workspace-search");
    expect(search).toHaveAttribute("placeholder", "Search workspaces…");

    expect(screen.queryByTestId("hww-new-workspace")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New workspace" })).not.toBeInTheDocument();
    expect(screen.getByTestId("ham-workspace-pill-create")).toBeInTheDocument();
    expect(screen.getByText("Workspaces")).toBeInTheDocument();
  });

  it("opens create modal from the pill + control", async () => {
    mockUseHamWorkspace.mockReturnValue(
      readyCtx("ws_a", [ws("ws_a", "Alpha"), ws("ws_b", "Beta")]),
    );
    renderShell();

    await waitFor(() => expect(screen.getByText("workspace child")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("ham-workspace-pill-create"));

    await waitFor(() =>
      expect(screen.getByTestId("ham-workspace-create-dialog")).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    await waitFor(() =>
      expect(screen.queryByTestId("ham-workspace-create-dialog")).not.toBeInTheDocument(),
    );
  });

  it("after successful create navigates to /workspace/chat (not settings)", async () => {
    mockUseHamWorkspace.mockReturnValue(
      readyCtx("ws_a", [ws("ws_a", "Alpha"), ws("ws_b", "Beta")]),
    );
    renderShell("/workspace/settings");

    await waitFor(() => expect(screen.getByText("workspace child")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("ham-workspace-pill-create"));
    await waitFor(() =>
      expect(screen.getByTestId("ham-workspace-create-dialog")).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByTestId("mock-shell-create-success"));

    await waitFor(() =>
      expect(screen.getByTestId("shell-route-path")).toHaveTextContent("/workspace/chat"),
    );
  });

  it("calls selectWorkspace when picking a workspace row", async () => {
    const selectWorkspace = vi.fn();
    mockUseHamWorkspace.mockReturnValue({
      ...readyCtx("ws_a", [ws("ws_a", "Alpha"), ws("ws_b", "Beta")]),
      selectWorkspace,
    });
    renderShell();

    await waitFor(() => expect(screen.getByText("workspace child")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("hww-workspace-row-ws_b"));

    expect(selectWorkspace).toHaveBeenCalledWith("ws_b");
  });

  it("collapsed primary rail has no workspace search controls", async () => {
    mockUseHamWorkspace.mockReturnValue(
      readyCtx("ws_a", [ws("ws_a", "Alpha"), ws("ws_b", "Beta")]),
    );
    renderShell();

    await waitFor(() => expect(screen.getByText("workspace child")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));

    expect(screen.queryByTestId("hww-workspace-search")).not.toBeInTheDocument();
    expect(screen.queryByTestId("hww-new-workspace")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ham-workspace-pill")).not.toBeInTheDocument();

    const primary = screen.getByRole("navigation", { name: "Workspace primary" });
    expect(primary.querySelector('a[href="/workspace/chat"]')).toBeNull();
  });

  it("does not show workspace chrome while signed out", async () => {
    mockUseHamWorkspace.mockReturnValue(baseCtx());
    renderShell();

    await waitFor(() => expect(screen.getByText("workspace child")).toBeInTheDocument());

    expect(screen.queryByTestId("hww-workspace-search")).not.toBeInTheDocument();
    expect(screen.queryByTestId("hww-new-workspace")).not.toBeInTheDocument();
  });

  it("still renders children on /workspace/chat", async () => {
    mockUseHamWorkspace.mockReturnValue(
      readyCtx("ws_a", [ws("ws_a", "Alpha"), ws("ws_b", "Beta")]),
    );
    renderShell("/workspace/chat");

    await waitFor(() => expect(screen.getByText("workspace child")).toBeInTheDocument());
  });
});
