/**
 * Session URL + workspace switching: stale ?session= must not load under the wrong workspace.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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

function chatRouteTree() {
  return (
    <WorkspaceHamProjectProvider>
      <MemoryRouter initialEntries={["/workspace/chat?session=sid_for_a"]}>
        <Routes>
          <Route path="/workspace/chat" element={<WorkspaceChatScreen />} />
        </Routes>
      </MemoryRouter>
    </WorkspaceHamProjectProvider>
  );
}

describe("WorkspaceChatScreen session URL + workspace switch", () => {
  beforeEach(() => {
    globalThis.ResizeObserver = class {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    } as unknown as typeof ResizeObserver;
    Object.defineProperty(window, "matchMedia", {
      writable: true,
      configurable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
    fetchChatSessionMock.mockImplementation(async (sessionId: string) => ({
      session_id: sessionId,
      messages: [],
    }));
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("does not fetch a prior workspace session id immediately after switching workspace (stale ?session=)", async () => {
    mockUseHamWorkspace.mockReturnValue(readyCtx("ws_a"));
    const view = render(chatRouteTree());

    await waitFor(() => expect(fetchChatSessionMock).toHaveBeenCalledWith("sid_for_a", "ws_a"));

    mockUseHamWorkspace.mockReturnValue(readyCtx("ws_b"));
    view.rerender(chatRouteTree());

    await waitFor(() => {
      const header = view.container.querySelector('[data-testid="hww-chat-header-compact"]');
      expect(header?.querySelector(".sr-only")?.textContent).toMatch(/New session/i);
    });

    expect(fetchChatSessionMock).not.toHaveBeenCalledWith("sid_for_a", "ws_b");
  });

  it("still surfaces Session unavailable for an invalid session deep link in the current workspace", async () => {
    fetchChatSessionMock.mockRejectedValue(new Error("session not found"));
    mockUseHamWorkspace.mockReturnValue(readyCtx("ws_b"));
    render(
      <WorkspaceHamProjectProvider>
        <MemoryRouter initialEntries={["/workspace/chat?session=sid_dead"]}>
          <Routes>
            <Route path="/workspace/chat" element={<WorkspaceChatScreen />} />
          </Routes>
        </MemoryRouter>
      </WorkspaceHamProjectProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("Session unavailable")).toBeInTheDocument();
    });
  });
});
