/**
 * Phase 2C: composer-driven coding conductor preview — no second prompt surface.
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
  listHamProjectsMock,
} = vi.hoisted(() => ({
  mockUseHamWorkspace: vi.fn(),
  fetchChatSessionMock: vi.fn(),
  previewCodingConductorMock: vi.fn(),
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

const CHAT_W1_PROJECT_ID = "project.chat-plan-w1-scoped";

const samplePreviewPayload = {
  kind: "coding_conductor_preview" as const,
  preview_id: "p-1",
  task_kind: "audit",
  task_confidence: 0.85,
  chosen: {
    provider: "factory_droid_audit" as const,
    label: "Read-only audit",
    available: true,
    reason: "Read-only audit; no risk to the repository.",
    blockers: [],
    confidence: 0.85,
    output_kind: "report" as const,
    requires_operator: false,
    requires_confirmation: true,
    will_modify_code: false,
    will_open_pull_request: false,
  },
  candidates: [
    {
      provider: "factory_droid_audit" as const,
      label: "Read-only audit",
      available: true,
      reason: "Read-only audit; no risk to the repository.",
      blockers: [],
      confidence: 0.85,
      output_kind: "report" as const,
      requires_operator: false,
      requires_confirmation: true,
      will_modify_code: false,
      will_open_pull_request: false,
    },
  ],
  blockers: [],
  recommendation_reason: "Read-only audit; no risk to the repository.",
  requires_approval: true,
  approval_kind: "confirm" as const,
  project: {
    found: true,
    project_id: "p1",
    build_lane_enabled: false,
    has_github_repo: false,
  },
  is_operator: false,
};

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

function forbiddenExtraUserTokens(): readonly string[] {
  return ["ham_droid_runner_url", "ham_droid_runner_token", "cursor_api_key"];
}

describe("WorkspaceChatScreen composer-driven coding plan", () => {
  beforeEach(() => {
    globalThis.ResizeObserver = class {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    } as unknown as typeof ResizeObserver;
    mockMatchMedia(true);
    previewCodingConductorMock.mockReset();
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

  function assertNoForbiddenTokens(root: HTMLElement) {
    const hay = root.textContent?.toLowerCase() ?? "";
    for (const t of FORBIDDEN_CARD_TOKENS) {
      expect(hay.includes(String(t).toLowerCase())).toBe(false);
    }
    for (const t of forbiddenExtraUserTokens()) {
      expect(hay.includes(t)).toBe(false);
    }
  }

  it("submits the trimmed composer draft via Plan with coding agents", async () => {
    previewCodingConductorMock.mockResolvedValue(samplePreviewPayload);
    const { container } = renderChat();

    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    const ta = container.querySelector("#hww-chat-composer") as HTMLTextAreaElement;
    expect(ta).toBeTruthy();
    fireEvent.change(ta, { target: { value: "  Audit the persistence layer.  " } });

    const planBtn = container.querySelector(
      "[data-hww-coding-plan-action]",
    ) as HTMLButtonElement | null;
    expect(planBtn).toBeTruthy();
    fireEvent.click(planBtn!);

    await waitFor(() => {
      expect(previewCodingConductorMock).toHaveBeenCalledWith({
        user_prompt: "Audit the persistence layer.",
        project_id: CHAT_W1_PROJECT_ID,
        workspace_id: "w1",
      });
    });

    await waitFor(() => {
      expect(container.querySelector("[data-hww-coding-plan-strip]")).not.toBeNull();
      expect(container.querySelector('[data-hww-coding-plan="card"]')).not.toBeNull();
    });
    assertNoForbiddenTokens(container);
  });

  it("does not call preview when composer draft is empty; shows validation", async () => {
    const { container } = renderChat();

    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    const planBtn = container.querySelector(
      "[data-hww-coding-plan-action]",
    ) as HTMLButtonElement | null;
    fireEvent.click(planBtn!);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Describe what you want HAM to build or inspect first.",
      );
    });
    expect(previewCodingConductorMock).not.toHaveBeenCalled();
  });

  it("blocks manual plan when no project is linked to this workspace", async () => {
    listHamProjectsMock.mockReset();
    listHamProjectsMock.mockResolvedValue({
      projects: [
        {
          id: "proj_elsewhere",
          version: "1.0.0",
          name: "Elsewhere",
          root: "/repo",
          description: "",
          metadata: { workspace_id: "other_ws" },
        },
      ],
    });
    const { container } = renderChat();

    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    const ta = container.querySelector("#hww-chat-composer") as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: "Improve auth." } });
    fireEvent.click(container.querySelector("[data-hww-coding-plan-action]") as HTMLElement);

    await waitFor(() =>
      expect(
        screen.getByText(/Choose or create a project linked to this workspace first/i),
      ).toBeInTheDocument(),
    );
    expect(previewCodingConductorMock).not.toHaveBeenCalled();
  });

  it("keeps launch CTA non-actionable", async () => {
    previewCodingConductorMock.mockResolvedValue(samplePreviewPayload);
    const { container } = renderChat();

    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    const ta = container.querySelector("#hww-chat-composer") as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: "Hello" } });
    fireEvent.click(container.querySelector("[data-hww-coding-plan-action]") as HTMLElement);

    await waitFor(() =>
      expect(container.querySelector('[data-hww-coding-plan="card"]')).not.toBeNull(),
    );

    const launch = container.querySelector(
      '[data-hww-coding-plan="launch-cta-disabled"]',
    ) as HTMLButtonElement | null;
    expect(launch?.disabled).toBe(true);
    expect(launch?.getAttribute("data-launch-enabled")).toBe("0");
  });

  it("focuses the main composer when empty-state Plan is clicked", async () => {
    previewCodingConductorMock.mockResolvedValue(samplePreviewPayload);
    const { container } = renderChat();

    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    const ta = container.querySelector("#hww-chat-composer") as HTMLTextAreaElement;
    const focusSpy = vi.spyOn(ta, "focus");

    fireEvent.change(ta, { target: { value: "Typed in composer" } });

    const emptyBtn = container.querySelector("[data-hww-coding-plan-open]") as HTMLElement;
    expect(emptyBtn).toBeTruthy();
    fireEvent.click(emptyBtn);

    expect(focusSpy).toHaveBeenCalled();
    await waitFor(() => expect(previewCodingConductorMock).toHaveBeenCalled());
  });

  it("send control remains available after a preview (composer still usable)", async () => {
    previewCodingConductorMock.mockResolvedValue(samplePreviewPayload);
    const { container } = renderChat();

    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    const ta = container.querySelector("#hww-chat-composer") as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: "Plan text" } });
    fireEvent.click(container.querySelector("[data-hww-coding-plan-action]") as HTMLElement);

    await waitFor(() =>
      expect(container.querySelector('[data-hww-coding-plan="card"]')).not.toBeNull(),
    );

    fireEvent.change(ta, { target: { value: "Plan text\nFollow-up for chat send" } });
    expect(ta.value).toContain("Follow-up for chat send");

    const command = screen.getByTestId("hww-command-panel");
    const send = within(command).getByRole("button", { name: "Send" });
    expect(send).toBeInTheDocument();
  });
});

describe("WorkspaceChatScreen OpenCode preferred-provider affordance", () => {
  beforeEach(() => {
    globalThis.ResizeObserver = class {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    } as unknown as typeof ResizeObserver;
    mockMatchMedia(true);
    previewCodingConductorMock.mockReset();
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

  const fdBuildChosen = {
    provider: "factory_droid_build" as const,
    label: "Low-risk pull request",
    available: true,
    reason: "Low-risk pull request with a minimal diff.",
    blockers: [],
    confidence: 0.8,
    output_kind: "pull_request" as const,
    requires_operator: false,
    requires_confirmation: true,
    will_modify_code: true,
    will_open_pull_request: true,
  };

  const opencodeAvailable = {
    provider: "opencode_cli" as const,
    label: "OpenCode managed workspace build",
    available: true,
    reason: "Build inside a managed workspace snapshot.",
    blockers: [],
    confidence: 0.7,
    output_kind: "pull_request" as const,
    requires_operator: false,
    requires_confirmation: true,
    will_modify_code: true,
    will_open_pull_request: false,
  };

  const previewWithOpencodeAlt = {
    ...samplePreviewPayload,
    chosen: fdBuildChosen,
    candidates: [fdBuildChosen, opencodeAvailable],
  };

  const previewWithOpencodeChosen = {
    ...samplePreviewPayload,
    chosen: opencodeAvailable,
    candidates: [opencodeAvailable, fdBuildChosen],
  };

  function assertNoForbiddenTokens(root: HTMLElement) {
    const hay = root.textContent?.toLowerCase() ?? "";
    for (const t of FORBIDDEN_CARD_TOKENS) {
      expect(hay.includes(String(t).toLowerCase())).toBe(false);
    }
    for (const t of forbiddenExtraUserTokens()) {
      expect(hay.includes(t)).toBe(false);
    }
  }

  it("clicking Try with OpenCode re-fires preview with preferred_provider=opencode_cli", async () => {
    previewCodingConductorMock
      .mockResolvedValueOnce(previewWithOpencodeAlt)
      .mockResolvedValueOnce(previewWithOpencodeChosen);
    const { container } = renderChat();

    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    const ta = container.querySelector("#hww-chat-composer") as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: "Refactor the auth module." } });
    fireEvent.click(container.querySelector("[data-hww-coding-plan-action]") as HTMLElement);

    await waitFor(() =>
      expect(
        container.querySelector('[data-hww-coding-plan="prefer-opencode-cta"]'),
      ).not.toBeNull(),
    );

    expect(previewCodingConductorMock).toHaveBeenCalledTimes(1);
    expect(previewCodingConductorMock).toHaveBeenNthCalledWith(1, {
      user_prompt: "Refactor the auth module.",
      project_id: CHAT_W1_PROJECT_ID,
      workspace_id: "w1",
    });

    const cta = container.querySelector(
      '[data-hww-coding-plan="prefer-opencode-cta"]',
    ) as HTMLButtonElement;
    fireEvent.click(cta);

    await waitFor(() => expect(previewCodingConductorMock).toHaveBeenCalledTimes(2));
    expect(previewCodingConductorMock).toHaveBeenNthCalledWith(2, {
      user_prompt: "Refactor the auth module.",
      project_id: CHAT_W1_PROJECT_ID,
      preferred_provider: "opencode_cli",
      workspace_id: "w1",
    });

    await waitFor(() =>
      expect(container.querySelector('[data-hww-coding-plan="prefer-opencode-cta"]')).toBeNull(),
    );
    assertNoForbiddenTokens(container);
  });

  it("renders the OpenCode managed approval panel after switching chosen to opencode_cli", async () => {
    const previewWithOpencodeChosenManaged = {
      ...samplePreviewPayload,
      chosen: opencodeAvailable,
      candidates: [opencodeAvailable, fdBuildChosen],
      project: {
        found: true,
        project_id: CHAT_W1_PROJECT_ID,
        build_lane_enabled: true,
        has_github_repo: false,
        output_target: "managed_workspace",
        has_workspace_id: true,
      },
    };
    previewCodingConductorMock
      .mockResolvedValueOnce(previewWithOpencodeAlt)
      .mockResolvedValueOnce(previewWithOpencodeChosenManaged);
    const { container } = renderChat();

    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    const ta = container.querySelector("#hww-chat-composer") as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: "Refactor the auth module." } });
    fireEvent.click(container.querySelector("[data-hww-coding-plan-action]") as HTMLElement);

    await waitFor(() =>
      expect(
        container.querySelector('[data-hww-coding-plan="prefer-opencode-cta"]'),
      ).not.toBeNull(),
    );

    const cta = container.querySelector(
      '[data-hww-coding-plan="prefer-opencode-cta"]',
    ) as HTMLButtonElement;
    fireEvent.click(cta);

    await waitFor(() =>
      expect(
        container.querySelector('[data-hww-coding-plan="opencode-build-approval"]'),
      ).not.toBeNull(),
    );
    expect(container.querySelector('[data-hww-coding-plan="launch-cta-disabled"]')).toBeNull();
    assertNoForbiddenTokens(container);
  });

  it("clears preferring state and keeps prior preview after re-preview failure", async () => {
    previewCodingConductorMock
      .mockResolvedValueOnce(previewWithOpencodeAlt)
      .mockRejectedValueOnce(new Error("HAM is offline right now."));
    const { container } = renderChat();

    await waitFor(() => expect(screen.getByTestId("hww-command-panel")).toBeInTheDocument());

    const ta = container.querySelector("#hww-chat-composer") as HTMLTextAreaElement;
    fireEvent.change(ta, { target: { value: "Refactor the auth module." } });
    fireEvent.click(container.querySelector("[data-hww-coding-plan-action]") as HTMLElement);

    await waitFor(() =>
      expect(
        container.querySelector('[data-hww-coding-plan="prefer-opencode-cta"]'),
      ).not.toBeNull(),
    );

    const cta = container.querySelector(
      '[data-hww-coding-plan="prefer-opencode-cta"]',
    ) as HTMLButtonElement;
    fireEvent.click(cta);

    await waitFor(() => expect(previewCodingConductorMock).toHaveBeenCalledTimes(2));

    // Card remains visible with prior preview; CTA returns to enabled state.
    await waitFor(() => {
      expect(container.querySelector('[data-hww-coding-plan="card"]')).not.toBeNull();
      const stillCta = container.querySelector(
        '[data-hww-coding-plan="prefer-opencode-cta"]',
      ) as HTMLButtonElement | null;
      expect(stillCta).not.toBeNull();
      expect(stillCta!.disabled).toBe(false);
    });
  });
});
