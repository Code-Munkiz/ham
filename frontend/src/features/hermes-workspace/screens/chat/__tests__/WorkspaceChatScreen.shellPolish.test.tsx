/**
 * /workspace/chat shell polish: header copy, quick prompts strip, toolbar icons.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const { mockUseHamWorkspace, fetchChatSessionMock } = vi.hoisted(() => ({
  mockUseHamWorkspace: vi.fn(),
  fetchChatSessionMock: vi.fn(),
}));

vi.mock("@/lib/ham/HamWorkspaceContext", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/ham/HamWorkspaceContext")>();
  return {
    ...actual,
    useHamWorkspace: mockUseHamWorkspace,
  };
});

vi.mock("../../hooks/useManagedMissionFeedLiveStream", () => ({
  useManagedMissionFeedLiveStream: () => ({
    feed: null,
    refetch: vi.fn(),
    banner: { phase: "idle" },
    initialLoading: false,
    feedScrollAnchorRef: { current: null },
  }),
}));

vi.mock("../workspaceChatSessionStorage", () => ({
  readWorkspaceLastChatSessionId: vi.fn(() => null),
  writeWorkspaceLastChatSessionId: vi.fn(),
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
    archiveWorkspaceById: vi.fn(),
    hasPerm: vi.fn(() => true),
  };
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

function renderChat(path = "/workspace/chat") {
  mockUseHamWorkspace.mockReturnValue(readyCtx("w1"));
  fetchChatSessionMock.mockImplementation(async (sessionId: string) => ({
    session_id: sessionId,
    messages: [],
  }));
  return render(
    <WorkspaceHamProjectProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/workspace/chat" element={<WorkspaceChatScreen />} />
        </Routes>
      </MemoryRouter>
    </WorkspaceHamProjectProvider>,
  );
}

describe("WorkspaceChatScreen shell polish", () => {
  beforeEach(() => {
    globalThis.ResizeObserver = class {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    } as unknown as typeof ResizeObserver;
    mockMatchMedia(true);
  });

  it("uses compact header without visible New session title or subtitle paragraph", async () => {
    const { container } = renderChat("/workspace/chat");
    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    const header = container.querySelector(".hww-chat-header");
    expect(header).toBeTruthy();
    expect(header?.querySelector("h1")).toBeNull();
    expect(header?.querySelector("p")).toBeNull();
    expect(header?.querySelector(".sr-only")?.textContent).toMatch(/New session/i);
    expect(header?.querySelector(".sr-only")?.textContent).toMatch(/Messages you send are stored/i);
    expect(screen.getByTestId("hww-chat-header-compact")).toBeInTheDocument();
  });

  it("keeps the right column on the workbench (no inspector header control)", async () => {
    renderChat("/workspace/chat?session=sid_shell");
    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    expect(screen.queryByTestId("hww-chat-inspector-tab")).not.toBeInTheDocument();
    expect(screen.getByTestId("hww-workbench-panel-slot")).toBeInTheDocument();
    expect(screen.getByTestId("hww-workbench")).toBeInTheDocument();
  });

  it("anchors quick prompts with hidden scrollbar and does not render scroll-chevrons", async () => {
    const { container } = renderChat("/workspace/chat?session=sid_tips");
    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    const scroll = container.querySelector("[data-hww-composer-quick-tips-scroll]");
    expect(scroll?.classList.contains("hww-composer-quick-tips-scroll")).toBe(true);
    expect(await screen.findByRole("toolbar", { name: "Starter prompts" })).toBeTruthy();

    expect(screen.queryByRole("button", { name: "Show more starter prompts" })).toBeNull();
    expect(container.querySelector("[data-hww-composer-quick-tips-scroll-next]")).toBeNull();
  });

  it("sizes composer toolbar icon actions consistently (attach, mic, send)", async () => {
    const { container } = renderChat("/workspace/chat?session=sid_actions");
    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    const panel = container.querySelector('[data-testid="hww-command-panel"]');
    expect(panel?.querySelector('[data-hww-composer-toolbar-icon="add"]')).toBeTruthy();
    expect(panel?.querySelector('[data-hww-composer-toolbar-icon="mic"]')).toBeTruthy();
    expect(panel?.querySelector('[data-hww-composer-toolbar-icon="send"]')).toBeTruthy();

    expect(panel?.querySelector('[data-hww-composer-toolbar-icon="add"]')?.className).toMatch(
      /size-8/,
    );
    const send = panel?.querySelector("[data-hww-command-send]");
    expect(send?.className).toMatch(/size-8/);
    expect(send?.className).toMatch(/rounded-md/);
  });

  it("workbench tab strip has no Terminal tab and no GitHub tab", async () => {
    renderChat("/workspace/chat?session=sid_wb");
    await waitFor(() =>
      expect(screen.getByTestId("hww-workbench-tab-preview")).toBeInTheDocument(),
    );
    expect(screen.queryByTestId("hww-workbench-tab-terminal")).not.toBeInTheDocument();
    expect(screen.queryByTestId("hww-workbench-tab-github")).not.toBeInTheDocument();
  });
});
