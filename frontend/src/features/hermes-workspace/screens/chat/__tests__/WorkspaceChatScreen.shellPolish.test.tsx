/**
 * /workspace/chat shell polish: header copy, inspector tab chrome, quick prompts scrollbar, toolbar icons.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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

  it("styles Inspector like a workbench tab and opens the inspector surface (no workbench slot)", async () => {
    renderChat("/workspace/chat?session=sid_shell");
    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    const tab = screen.getByTestId("hww-chat-inspector-tab");
    expect(tab.getAttribute("data-active")).toBe("false");
    expect(tab.className).toMatch(/rounded-md/);
    expect(tab.className).toMatch(/text-white\/45/);

    fireEvent.click(tab);
    await waitFor(() => expect(screen.getByTestId("hww-inspector-panel")).toBeInTheDocument());
    expect(tab.getAttribute("data-active")).toBe("true");
    expect(tab.className).toMatch(/bg-emerald-500\/15/);
    expect(screen.queryByTestId("hww-workbench")).not.toBeInTheDocument();
  });

  it("anchors quick prompts with hidden scrollbar class and exposes compact scroll-next control", async () => {
    const { container } = renderChat("/workspace/chat?session=sid_tips");
    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    const scroll = container.querySelector("[data-hww-composer-quick-tips-scroll]");
    expect(scroll?.classList.contains("hww-composer-quick-tips-scroll")).toBe(true);
    expect(await screen.findByRole("toolbar", { name: "Starter prompts" })).toBeTruthy();

    const nextBtn = screen.getByRole("button", { name: "Show more starter prompts" });
    expect(nextBtn).toBeTruthy();
    expect(nextBtn.className).toMatch(/h-7/);
    expect(nextBtn.className).toMatch(/w-7/);
  });

  it("sizes composer toolbar icon actions consistently (attach, mic, send)", async () => {
    const { container } = renderChat("/workspace/chat?session=sid_actions");
    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    const panel = container.querySelector('[data-testid="hww-command-panel"]');
    expect(panel?.querySelector('[data-hww-composer-toolbar-icon="add"]')).toBeTruthy();
    expect(panel?.querySelector('[data-hww-composer-toolbar-icon="mic"]')).toBeTruthy();
    expect(panel?.querySelector('[data-hww-composer-toolbar-icon="send"]')).toBeTruthy();

    expect(panel?.querySelector('[data-hww-composer-toolbar-icon="add"]')?.className).toMatch(
      /size-9/,
    );
    const send = panel?.querySelector("[data-hww-command-send]");
    expect(send?.className).toMatch(/size-9/);
    expect(send?.className).toMatch(/rounded-md/);
  });

  it("workbench tab strip remains unchanged without GitHub", async () => {
    renderChat("/workspace/chat?session=sid_wb");
    await waitFor(() => expect(screen.getByTestId("hww-workbench-tab-terminal")).toBeInTheDocument());
    expect(screen.queryByTestId("hww-workbench-tab-github")).not.toBeInTheDocument();
    expect(screen.getByTestId("hww-workbench-tab-preview")).toBeInTheDocument();
  });
});
