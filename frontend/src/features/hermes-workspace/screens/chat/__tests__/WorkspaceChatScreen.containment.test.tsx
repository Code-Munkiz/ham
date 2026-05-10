/**
 * /workspace/chat: command vs workbench split — composer and feed must stay in the command column.
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

describe("WorkspaceChatScreen split containment", () => {
  beforeEach(() => {
    globalThis.ResizeObserver = class {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    } as unknown as typeof ResizeObserver;
    mockMatchMedia(true);
  });

  it("anchors composer, starter strip, empty state inside command panel DOM; workbench is sibling-only", async () => {
    const { container } = renderChat();

    await waitFor(() => {
      expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByTestId("hww-workbench")).toBeInTheDocument();
    });

    const panels = container.querySelectorAll('[data-testid="hww-command-panel"]');
    expect(panels.length).toBe(1);

    const commandPanel = container.querySelector('[data-testid="hww-command-panel"]');
    const workbenchAside = container.querySelector('[data-testid="hww-workbench"]');
    const wbSlot = container.querySelector('[data-testid="hww-workbench-panel-slot"]');

    expect(commandPanel).toBeTruthy();
    expect(workbenchAside).toBeTruthy();
    expect(wbSlot?.contains(workbenchAside!)).toBe(true);
    expect(commandPanel?.contains(workbenchAside!)).toBe(false);

    expect(commandPanel?.querySelector(".hww-chat-composer-outer")).toBeTruthy();
    expect(commandPanel?.querySelector("[data-hww-command-deck]")).toBeTruthy();
    expect(commandPanel?.querySelector("[data-hww-composer-quick-tips]")).toBeTruthy();
    expect(commandPanel?.querySelector(".hww-chat-empty")).toBeTruthy();

    expect(
      screen
        .getByRole("heading", { name: "Begin a session" })
        .closest('[data-testid="hww-command-panel"]'),
    ).toBe(commandPanel);

    const composer = commandPanel!.querySelector(".hww-chat-composer-outer");
    expect(composer?.className).not.toMatch(/100vw/i);
    expect(composer?.className).not.toMatch(/fixed/i);
    const deckOuter = commandPanel!.querySelector("[data-hww-command-deck]");
    expect(deckOuter?.className).toMatch(/max-w-full/i);
    expect(deckOuter?.className).toMatch(/overflow-hidden/i);
    const deckInner = deckOuter?.querySelector(".hww-command-deck.box-border");
    expect(deckInner?.className).toMatch(/overflow-x-hidden/i);
    expect(
      screen
        .getByRole("toolbar", { name: "Starter prompts" })
        .closest('[data-testid="hww-command-panel"]'),
    ).toBe(commandPanel);
    expect(screen.getByTestId("hww-chat-split-row")).toBeInTheDocument();
  });

  it("workbench exposes Project source tab without a GitHub tab", async () => {
    renderChat();
    await waitFor(() => {
      expect(screen.getByTestId("hww-workbench-tab-storage")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("hww-workbench-tab-github")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId("hww-workbench-tab-storage"));
    expect(await screen.findByText(/ZIP ingestion is not supported/i)).toBeInTheDocument();
  });

  it("composer does not advertise viewport-relative width tokens on roots", async () => {
    const { container } = renderChat();
    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());
    const commandPanel = container.querySelector('[data-testid="hww-command-panel"]');
    expect(commandPanel?.className?.includes("100vw")).toBe(false);
    expect(commandPanel?.textContent ?? "").not.toContain("100vw");
  });
});
