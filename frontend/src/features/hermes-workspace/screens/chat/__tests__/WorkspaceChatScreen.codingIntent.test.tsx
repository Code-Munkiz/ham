/**
 * Conversational coding conductor — auto-preview from normal chat send.
 *
 * Locks the product contract:
 * - Coding-intent text fired through the main composer triggers
 *   previewCodingConductor automatically (no "Plan with coding agents"
 *   click required).
 * - Conceptual / conversational text does NOT trigger the preview.
 * - The CodingPlanCard renders inline below the message list.
 * - Launch CTAs stay non-actionable (no Cursor / Droid / Claude launch).
 * - No forbidden internal tokens leak into the surfaced UI text.
 *
 * Smallest safe path: frontend-only heuristic + side-effect preview call.
 * Backend chat route is unchanged.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { FORBIDDEN_CARD_TOKENS } from "../coding-plan/codingPlanCardCopy";
import { WorkspaceChatScreen } from "../WorkspaceChatScreen";
import { WorkspaceHamProjectProvider } from "../../../WorkspaceHamProjectContext";
import type { HamWorkspaceContextValue } from "@/lib/ham/HamWorkspaceContext";
import type { HamWorkspaceSummary } from "@/lib/ham/workspaceApi";

const {
  mockUseHamWorkspace,
  fetchChatSessionMock,
  previewCodingConductorMock,
  chatStreamMock,
  getStreamAuthMock,
  listHamProjectsMock,
} = vi.hoisted(() => ({
  mockUseHamWorkspace: vi.fn(),
  fetchChatSessionMock: vi.fn(),
  previewCodingConductorMock: vi.fn(),
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
    previewCodingConductor: (...args: Parameters<typeof mod.previewCodingConductor>) =>
      previewCodingConductorMock(...args),
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

const CHAT_W1_PROJECT_ID = "project.chat-test-w1-scoped";

const samplePreviewPayload = {
  kind: "coding_conductor_preview" as const,
  preview_id: "p-2",
  task_kind: "feature",
  task_confidence: 0.7,
  chosen: {
    provider: "factory_droid_build" as const,
    label: "Factory Droid build",
    available: true,
    reason: "Feature build; safe-edit-low isolated workspace.",
    blockers: [],
    confidence: 0.7,
    output_kind: "pull_request" as const,
    requires_operator: false,
    requires_confirmation: true,
    will_modify_code: true,
    will_open_pull_request: true,
  },
  candidates: [
    {
      provider: "factory_droid_build" as const,
      label: "Factory Droid build",
      available: true,
      reason: "Feature build; safe-edit-low isolated workspace.",
      blockers: [],
      confidence: 0.7,
      output_kind: "pull_request" as const,
      requires_operator: false,
      requires_confirmation: true,
      will_modify_code: true,
      will_open_pull_request: true,
    },
  ],
  blockers: [],
  recommendation_reason: "Feature build; safe-edit-low isolated workspace.",
  requires_approval: true,
  approval_kind: "operator_confirm" as const,
  project: {
    found: true,
    project_id: "p1",
    build_lane_enabled: false,
    has_github_repo: true,
  },
  is_operator: false,
};

function renderChat() {
  mockUseHamWorkspace.mockReturnValue(readyCtx("w1"));
  fetchChatSessionMock.mockImplementation(async (sessionId: string) => ({
    session_id: sessionId,
    messages: [],
  }));
  getStreamAuthMock.mockResolvedValue(undefined);
  // Chat stream: resolve to a minimal "ok" without actually streaming.
  // We only need send() to start so the side-effect preview fires.
  chatStreamMock.mockImplementation(async () => ({ ok: true }));
  return render(
    <WorkspaceHamProjectProvider>
      <MemoryRouter initialEntries={["/workspace/chat?session=sid_ci"]}>
        <Routes>
          <Route path="/workspace/chat" element={<WorkspaceChatScreen />} />
        </Routes>
      </MemoryRouter>
    </WorkspaceHamProjectProvider>,
  );
}

function forbiddenExtraTokens(): readonly string[] {
  return [
    "ham_droid_runner_url",
    "ham_droid_runner_token",
    "ham_droid_exec_token",
    "cursor_api_key",
    "factory_api_key",
    "safe_edit_low",
    "droid exec",
    "argv",
  ];
}

function assertNoForbiddenTokens(root: HTMLElement) {
  const hay = root.textContent?.toLowerCase() ?? "";
  for (const t of FORBIDDEN_CARD_TOKENS) {
    expect(hay.includes(String(t).toLowerCase())).toBe(false);
  }
  for (const t of forbiddenExtraTokens()) {
    expect(hay.includes(t)).toBe(false);
  }
}

async function typeAndSend(container: HTMLElement, text: string) {
  const ta = container.querySelector("#hww-chat-composer") as HTMLTextAreaElement;
  expect(ta).toBeTruthy();
  fireEvent.change(ta, { target: { value: text } });
  const command = screen.getByTestId("hww-command-panel");
  const send = within(command).getByRole("button", { name: "Send" });
  fireEvent.click(send);
}

describe("WorkspaceChatScreen conversational coding conductor", () => {
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
    // jsdom does not implement scrollIntoView; chat screen calls it in effects.
    if (!(Element.prototype as unknown as { scrollIntoView?: unknown }).scrollIntoView) {
      (Element.prototype as unknown as { scrollIntoView: () => void }).scrollIntoView = () => {};
    }
    mockMatchMedia(true);
    previewCodingConductorMock.mockReset();
    chatStreamMock.mockReset();
    getStreamAuthMock.mockReset();
    listHamProjectsMock.mockReset();
    listHamProjectsMock.mockImplementation(async () => ({
      projects: [
        {
          id: CHAT_W1_PROJECT_ID,
          version: "1.0.0",
          name: "Scoped Chat",
          root: "/repo",
          description: "",
          metadata: { workspace_id: "w1" },
        },
      ],
    }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("auto-fires conductor preview when normal-send text looks like a repo coding task", async () => {
    previewCodingConductorMock.mockResolvedValue(samplePreviewPayload);
    chatStreamMock.mockImplementation(async () => ({ ok: true }));
    getStreamAuthMock.mockResolvedValue(undefined);
    const { container } = renderChat();

    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    await typeAndSend(container, "Refactor the persistence layer in the HAM repo");

    await waitFor(() => {
      expect(previewCodingConductorMock).toHaveBeenCalledWith({
        user_prompt: "Refactor the persistence layer in the HAM repo",
        project_id: CHAT_W1_PROJECT_ID,
        workspace_id: "w1",
      });
    });
    // CodingPlanCard appears below the thread.
    await waitFor(() => {
      expect(container.querySelector("[data-hww-coding-plan-strip]")).not.toBeNull();
      expect(container.querySelector('[data-hww-coding-plan="card"]')).not.toBeNull();
    });
  });

  it("does NOT auto-fire conductor preview for chat-native builder prompts", async () => {
    previewCodingConductorMock.mockResolvedValue(samplePreviewPayload);
    chatStreamMock.mockImplementation(async () => ({ ok: true }));
    getStreamAuthMock.mockResolvedValue(undefined);
    const { container } = renderChat();

    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    await typeAndSend(container, "Build me a game like Tetris");
    await new Promise((r) => setTimeout(r, 50));
    expect(previewCodingConductorMock).not.toHaveBeenCalled();
    expect(container.querySelector('[data-hww-coding-plan="card"]')).toBeNull();
  });

  it("does NOT auto-fire conductor preview for conceptual / explain prompts", async () => {
    previewCodingConductorMock.mockResolvedValue(samplePreviewPayload);
    chatStreamMock.mockImplementation(async () => ({ ok: true }));
    getStreamAuthMock.mockResolvedValue(undefined);
    const { container } = renderChat();

    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    await typeAndSend(container, "Explain what validators are");
    // Give the side-effect a chance to run, then assert it did NOT.
    await new Promise((r) => setTimeout(r, 50));
    expect(previewCodingConductorMock).not.toHaveBeenCalled();
    expect(container.querySelector('[data-hww-coding-plan="card"]')).toBeNull();
  });

  it("does NOT auto-fire for short greetings", async () => {
    previewCodingConductorMock.mockResolvedValue(samplePreviewPayload);
    chatStreamMock.mockImplementation(async () => ({ ok: true }));
    getStreamAuthMock.mockResolvedValue(undefined);
    const { container } = renderChat();

    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    await typeAndSend(container, "Hi!");
    await new Promise((r) => setTimeout(r, 50));
    expect(previewCodingConductorMock).not.toHaveBeenCalled();
  });

  it("surfaces workspace project gate when nothing maps to the active workspace", async () => {
    listHamProjectsMock.mockReset();
    listHamProjectsMock.mockResolvedValue({
      projects: [
        {
          id: "p_other_ws_only",
          version: "1.0.0",
          name: "Other WS",
          root: "/r",
          description: "",
          metadata: { workspace_id: "other_ws" },
        },
      ],
    });
    previewCodingConductorMock.mockResolvedValue(samplePreviewPayload);
    chatStreamMock.mockImplementation(async () => ({ ok: true }));
    getStreamAuthMock.mockResolvedValue(undefined);
    const { container } = renderChat();

    await waitFor(() => expect(listHamProjectsMock).toHaveBeenCalled());
    // Wait until async project-scope resolution settles (avoid racing preview with stale projectId).
    await waitFor(() => {
      expect(screen.getByTestId("hww-preview-state-no-project")).toBeInTheDocument();
    });

    await typeAndSend(container, "Refactor the checkout persistence layer");

    await waitFor(() => {
      expect(
        screen.getByText(/Choose or create a project linked to this workspace first/i),
      ).toBeInTheDocument();
    });
    expect(previewCodingConductorMock).not.toHaveBeenCalled();
    assertNoForbiddenTokens(container);
  });

  it("never launches a provider build from auto-preview (launch CTA stays disabled)", async () => {
    previewCodingConductorMock.mockResolvedValue(samplePreviewPayload);
    chatStreamMock.mockImplementation(async () => ({ ok: true }));
    getStreamAuthMock.mockResolvedValue(undefined);
    const { container } = renderChat();

    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    await typeAndSend(container, "Refactor the persistence layer");

    await waitFor(() => expect(previewCodingConductorMock).toHaveBeenCalled());
    await waitFor(() =>
      expect(container.querySelector('[data-hww-coding-plan="card"]')).not.toBeNull(),
    );

    const launch = container.querySelector(
      '[data-hww-coding-plan="launch-cta-disabled"]',
    ) as HTMLButtonElement | null;
    expect(launch?.disabled).toBe(true);
    expect(launch?.getAttribute("data-launch-enabled")).toBe("0");
  });

  it("does not leak forbidden tokens after auto-preview renders", async () => {
    previewCodingConductorMock.mockResolvedValue(samplePreviewPayload);
    chatStreamMock.mockImplementation(async () => ({ ok: true }));
    getStreamAuthMock.mockResolvedValue(undefined);
    const { container } = renderChat();

    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    await typeAndSend(container, "Audit the persistence layer");

    await waitFor(() => expect(previewCodingConductorMock).toHaveBeenCalled());
    await waitFor(() =>
      expect(container.querySelector('[data-hww-coding-plan="card"]')).not.toBeNull(),
    );
    assertNoForbiddenTokens(container);
  });

  it("manual fallback button still works (demoted but functional)", async () => {
    previewCodingConductorMock.mockResolvedValue(samplePreviewPayload);
    const { container } = renderChat();
    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    const planBtn = container.querySelector(
      "[data-hww-coding-plan-action]",
    ) as HTMLButtonElement | null;
    expect(planBtn).toBeTruthy();
    expect(planBtn?.getAttribute("data-hww-coding-plan-priority")).toBe("manual-fallback");

    const ta = container.querySelector("#hww-chat-composer") as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: "Inspect the runner" } });
    fireEvent.click(planBtn!);

    await waitFor(() => {
      expect(previewCodingConductorMock).toHaveBeenCalledWith({
        user_prompt: "Inspect the runner",
        project_id: CHAT_W1_PROJECT_ID,
        workspace_id: "w1",
      });
    });
  });

  it("debounces: identical consecutive coding prompts only call preview once", async () => {
    previewCodingConductorMock.mockResolvedValue(samplePreviewPayload);
    chatStreamMock.mockImplementation(async () => ({ ok: true }));
    getStreamAuthMock.mockResolvedValue(undefined);
    const { container } = renderChat();

    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    await typeAndSend(container, "Fix the failing test in the runner");
    await waitFor(() => expect(previewCodingConductorMock).toHaveBeenCalledTimes(1));

    // Second identical send should be debounced by lastAutoCodingPromptRef.
    await typeAndSend(container, "Fix the failing test in the runner");
    await new Promise((r) => setTimeout(r, 50));
    expect(previewCodingConductorMock).toHaveBeenCalledTimes(1);
  });
});
