/**
 * Desktop chat reserves one right column for the workbench (inspector removed from chrome).
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const { mockUseHamWorkspace, fetchChatSessionMock } = vi.hoisted(() => ({
  mockUseHamWorkspace: vi.fn(),
  fetchChatSessionMock: vi.fn(),
}));

vi.mock("@/lib/ham/HamWorkspaceContext", () => ({
  useHamWorkspace: mockUseHamWorkspace,
}));

vi.mock("../../hooks/useManagedMissionFeedLiveStream", () => ({
  useManagedMissionFeedLiveStream: () => ({
    feed: null,
    refetch: vi.fn(),
    banner: { phase: "idle" },
    initialLoading: false,
    feedScrollAnchorRef: { current: null },
  }),
}));

vi.mock("@/lib/ham/api", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/ham/api")>();
  return {
    ...mod,
    fetchChatSession: (...args: Parameters<typeof mod.fetchChatSession>) =>
      fetchChatSessionMock(...args),
    fetchChatComposerPreference: vi.fn(async () => ({
      kind: "ham_chat_composer_preference" as const,
      model_id: null,
    })),
    putChatComposerPreference: vi.fn(
      async (_workspaceId: string, body: { model_id: string | null }) => ({
        kind: "ham_chat_composer_preference" as const,
        model_id: body.model_id,
      }),
    ),
    listHamProjects: vi.fn(async () => ({ projects: [] })),
    fetchContextEngine: vi.fn(
      async () =>
        ({
          cwd: "/tmp/repo",
        }) as unknown as import("@/lib/ham/types").ContextEnginePayload,
    ),
    ensureProjectIdForWorkspaceRoot: vi.fn(async () => null),
  };
});

import { WorkspaceChatScreen } from "../WorkspaceChatScreen";
import { WorkspaceHamProjectProvider } from "../../../WorkspaceHamProjectContext";
import type { HamWorkspaceContextValue } from "@/lib/ham/HamWorkspaceContext";
import type { HamWorkspaceSummary } from "@/lib/ham/workspaceApi";

function wsSummary(id: string): HamWorkspaceSummary {
  return {
    workspace_id: id,
    org_id: null,
    name: "Workspace",
    slug: "ws",
    description: "",
    status: "active",
    role: "owner",
    perms: ["chat.read", "chat.write"],
    is_default: true,
    created_at: "2026-05-05T00:00:00Z",
    updated_at: "2026-05-05T00:00:00Z",
  };
}

function readyCtx(workspaceId: string | null): HamWorkspaceContextValue {
  const w = workspaceId ? wsSummary(workspaceId) : null;
  return {
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
        workspaces: w ? [w] : [],
        default_workspace_id: workspaceId,
        auth_mode: "clerk",
      },
      activeWorkspaceId: workspaceId,
    },
    workspaces: w ? [w] : [],
    active: w,
    authMode: "clerk",
    hostedAuth: { clerkConfigured: true, isLoaded: true, isSignedIn: true },
    refresh: vi.fn(async () => undefined),
    selectWorkspace: vi.fn(),
    createWorkspace: vi.fn(),
    patchActiveWorkspace: vi.fn(),
    hasPerm: vi.fn(() => true),
  };
}

function renderChat() {
  mockUseHamWorkspace.mockReturnValue(readyCtx("w1"));
  fetchChatSessionMock.mockImplementation(async (sessionId: string) => ({
    session_id: sessionId,
    messages: [],
  }));
  return render(
    <WorkspaceHamProjectProvider>
      <MemoryRouter initialEntries={["/workspace/chat?session=sid_wb"]}>
        <Routes>
          <Route path="/workspace/chat" element={<WorkspaceChatScreen />} />
        </Routes>
      </MemoryRouter>
    </WorkspaceHamProjectProvider>,
  );
}

function mockMatchMedia(matches: boolean) {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
}

describe("WorkspaceChatScreen workbench shell", () => {
  beforeEach(() => {
    globalThis.ResizeObserver = class {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    } as unknown as typeof ResizeObserver;
    mockMatchMedia(false);
  });

  it("renders workbench and composer in empty session", async () => {
    renderChat();
    await waitFor(() => {
      expect(screen.getByTestId("hww-workbench")).toBeInTheDocument();
    });
    const command = screen.getByTestId("hww-command-panel");
    expect(within(command).getByRole("textbox")).toBeInTheDocument();
  });

  it("shows a resize handle on desktop split layout", async () => {
    mockMatchMedia(true);
    renderChat();
    await waitFor(() => {
      expect(screen.getByTestId("hww-workbench")).toBeInTheDocument();
    });
    expect(screen.getByTestId("hww-chat-split-resizer")).toBeInTheDocument();
  });

  it("does not show resize handle when viewport is below desktop split breakpoint", async () => {
    mockMatchMedia(false);
    renderChat();
    await waitFor(() => {
      expect(screen.getByTestId("hww-workbench")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("hww-chat-split-resizer")).not.toBeInTheDocument();
  });

  it("keeps split row scrollable and workbench slot bounded on constrained viewports", async () => {
    mockMatchMedia(false);
    renderChat();
    await waitFor(() => {
      expect(screen.getByTestId("hww-workbench")).toBeInTheDocument();
    });
    const splitRow = screen.getByTestId("hww-chat-split-row");
    expect(splitRow.className).toContain("overflow-y-auto");

    const workbenchSlot = screen.getByTestId("hww-workbench-panel-slot");
    expect(workbenchSlot.className).toContain("min-h-[min(260px,48vh)]");
    expect(workbenchSlot.className).toContain("max-h-[48vh]");
    expect(workbenchSlot.className).toContain("shrink-0");
  });

  it("switches workbench tabs locally", async () => {
    renderChat();
    await waitFor(() => {
      expect(screen.getByTestId("hww-workbench")).toBeInTheDocument();
    });
    expect(screen.getByTestId("hww-preview-state-no-project")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("hww-workbench-tab-code"));
    expect(
      await screen.findByText("Select a workspace and project to browse generated source."),
    ).toBeInTheDocument();
  });

  it("does not surface a header inspector toggle (workbench stays mounted)", async () => {
    renderChat();
    await waitFor(() => {
      expect(screen.getByTestId("hww-workbench")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("hww-chat-inspector-tab")).not.toBeInTheDocument();
    expect(screen.queryByTestId("hww-inspector-panel")).not.toBeInTheDocument();
  });

  it("desktop split keeps workbench + resize handle without inspector swap", async () => {
    mockMatchMedia(true);
    renderChat();
    await waitFor(() => {
      expect(screen.getByTestId("hww-workbench")).toBeInTheDocument();
    });
    expect(screen.getByTestId("hww-chat-split-resizer")).toBeInTheDocument();
    expect(screen.queryByTestId("hww-chat-inspector-tab")).not.toBeInTheDocument();
  });
});
