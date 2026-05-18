/**
 * Locks VAL-FE-001 / VAL-FE-002: ordinary chat send must NOT default to builder/agent posture.
 *
 * Captures the body passed to `workspaceChatAdapter.stream` and asserts neither
 * `workbench_mode` nor `worker` are present when the user has not touched any workbench /
 * builder affordance.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { WorkspaceChatScreen } from "../WorkspaceChatScreen";
import { WorkspaceHamProjectProvider } from "../../../WorkspaceHamProjectContext";
import type { HamWorkspaceContextValue } from "@/lib/ham/HamWorkspaceContext";
import type { HamWorkspaceSummary } from "@/lib/ham/workspaceApi";

const {
  mockUseHamWorkspace,
  fetchChatSessionMock,
  chatStreamMock,
  getStreamAuthMock,
  listHamProjectsMock,
} = vi.hoisted(() => ({
  mockUseHamWorkspace: vi.fn(),
  fetchChatSessionMock: vi.fn(),
  chatStreamMock: vi.fn(),
  getStreamAuthMock: vi.fn(),
  listHamProjectsMock: vi.fn(),
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
    listHamProjects: (...args: Parameters<typeof mod.listHamProjects>) =>
      listHamProjectsMock(...args),
  };
});

vi.mock("../../../workspaceAdapters", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../../../workspaceAdapters")>();
  return {
    ...mod,
    workspaceChatAdapter: {
      ...mod.workspaceChatAdapter,
      getStreamAuth: getStreamAuthMock,
      stream: chatStreamMock,
    },
  };
});

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

function renderChat() {
  mockUseHamWorkspace.mockReturnValue(readyCtx("w1"));
  fetchChatSessionMock.mockImplementation(async (sessionId: string) => ({
    session_id: sessionId,
    messages: [],
  }));
  getStreamAuthMock.mockResolvedValue(undefined);
  chatStreamMock.mockImplementation(async () => ({
    session_id: "sid_posture",
    messages: [],
    actions: [],
    operator_result: null,
    execution_mode: null,
  }));
  listHamProjectsMock.mockImplementation(async () => ({
    projects: [
      {
        id: "project.posture-w1",
        version: "1.0.0",
        name: "Posture Scoped",
        root: "/repo",
        description: "",
        metadata: { workspace_id: "w1" },
      },
    ],
  }));
  return render(
    <WorkspaceHamProjectProvider>
      <MemoryRouter initialEntries={["/workspace/chat?session=sid_posture"]}>
        <Routes>
          <Route path="/workspace/chat" element={<WorkspaceChatScreen />} />
        </Routes>
      </MemoryRouter>
    </WorkspaceHamProjectProvider>,
  );
}

async function typeAndSend(container: HTMLElement, text: string) {
  const ta = container.querySelector("#hww-chat-composer") as HTMLTextAreaElement;
  expect(ta).toBeTruthy();
  fireEvent.change(ta, { target: { value: text } });
  const command = screen.getByTestId("hww-command-panel");
  const send = within(command).getByRole("button", { name: "Send" });
  fireEvent.click(send);
}

describe("WorkspaceChatScreen default-posture outbound payload", () => {
  beforeEach(() => {
    try {
      sessionStorage.clear();
    } catch {
      /* ignore */
    }
    globalThis.ResizeObserver = class {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    } as unknown as typeof ResizeObserver;
    if (!(Element.prototype as unknown as { scrollIntoView?: unknown }).scrollIntoView) {
      (Element.prototype as unknown as { scrollIntoView: () => void }).scrollIntoView = () => {};
    }
    mockMatchMedia(true);
    chatStreamMock.mockReset();
    getStreamAuthMock.mockReset();
    fetchChatSessionMock.mockReset();
    listHamProjectsMock.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("ordinary chat send omits workbench_mode and worker (VAL-FE-001 / VAL-FE-002)", async () => {
    const { container } = renderChat();
    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    await typeAndSend(container, "what is HAM?");

    await waitFor(() => expect(chatStreamMock).toHaveBeenCalledTimes(1));
    const body = chatStreamMock.mock.calls[0]?.[0] as Record<string, unknown> | undefined;
    expect(body).toBeTruthy();
    expect(body).not.toBeUndefined();
    expect((body ?? {}) as Record<string, unknown>).not.toHaveProperty("workbench_mode");
    expect((body ?? {}) as Record<string, unknown>).not.toHaveProperty("worker");
    // The neighboring posture-adjacent field stays unchanged so the rest of the contract is intact.
    expect((body ?? {}).max_mode).toBe(false);
  });
});
