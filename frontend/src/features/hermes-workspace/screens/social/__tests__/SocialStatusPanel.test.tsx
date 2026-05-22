import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  GoHamSocialProfile,
  PollerStatus,
  SocialAutonomyTickResult,
  TelegramCapabilitiesPanel,
} from "@/features/hermes-workspace/adapters/socialAdapter";

const adapterMock = vi.hoisted(() => ({
  getAutonomyProfile: vi.fn(),
  getLearningHints: vi.fn(),
  launchAutonomy: vi.fn(),
  pauseAutonomy: vi.fn(),
  stopAutonomy: vi.fn(),
  updateAutonomyLimits: vi.fn(),
  getAutonomyWriteStatus: vi.fn(),
  previewAutonomyProfile: vi.fn(),
  previewAutonomyTick: vi.fn(),
  getPollerStatus: vi.fn(),
  getTelegramCapabilitiesPanel: vi.fn(),
}));

vi.mock("@/features/hermes-workspace/adapters/socialAdapter", () => ({
  socialAdapter: adapterMock,
}));

import { WorkspaceSocialScreen } from "../WorkspaceSocialScreen";

type ProfileOverride = Omit<Partial<GoHamSocialProfile>, "status"> & {
  status?: string;
};

function profile(overrides: ProfileOverride = {}): GoHamSocialProfile {
  const base = {
    profile_id: "profile-1",
    workspace_id: null,
    project_id: null,
    status: "running",
    goal: "grow awareness",
    persona_id: "ham-canonical",
    channels: {
      x: { enabled: true, available: true },
      telegram: { enabled: false, available: true },
      discord: { enabled: false, available: false },
    },
    actions_allowed_per_channel: {
      x: ["reply", "broadcast"],
      telegram: ["message", "activity", "reply"],
      discord: [],
    },
    daily_caps: { x: 3, telegram: 5, discord: 0 },
    cadence: "daily",
    quiet_hours: null,
    forbidden_topics: [],
    safety_rules: ["no spam", "no mass tagging", "no financial promises", "no credential requests"],
    learning_enabled: true,
    emergency_stop: false,
    last_run_at: null,
    next_run_at: null,
    last_tick_summary: null,
    created_at: "2026-05-20T00:00:00Z",
    updated_at: "2026-05-20T00:00:00Z",
  } satisfies GoHamSocialProfile;
  return { ...base, ...overrides } as GoHamSocialProfile;
}

function tickResult(overrides: Partial<SocialAutonomyTickResult> = {}): SocialAutonomyTickResult {
  return {
    ran: true,
    dry_run: true,
    actions_considered: ["x:reply", "telegram:message"],
    actions_taken: ["x:reply"],
    blocked_reasons: [],
    next_run_summary: "Next due at 2026-05-21 12:00 UTC.",
    profile_status: "running",
    ...overrides,
  };
}

function defaultPollerStatus(): PollerStatus {
  return {
    last_run_at: null,
    last_offset: null,
    transcript_count_today: 0,
    last_error_code: null,
  };
}

function defaultTelegramCaps(): TelegramCapabilitiesPanel {
  return {
    telegram_readiness: null,
    hermes_gateway_readiness: null,
    social_critic: null,
  };
}

function mockLoad(nextProfile: GoHamSocialProfile | null = profile()) {
  adapterMock.getAutonomyProfile.mockResolvedValue({
    profile: nextProfile,
    bridge: { status: "ready" },
  });
  adapterMock.getLearningHints.mockResolvedValue({
    hints: {
      hints: "HAM learned to keep social updates concise.",
      generated_at: "2026-05-20T00:00:00Z",
    },
    bridge: { status: "ready" },
  });
  adapterMock.getAutonomyWriteStatus.mockResolvedValue({
    status: {
      kind: "ham_social_autonomy_write_status",
      writes_enabled: true,
    },
    bridge: { status: "ready" },
  });
  adapterMock.launchAutonomy.mockResolvedValue({
    profile: profile({ status: "running" }),
    bridge: { status: "ready" },
  });
  adapterMock.pauseAutonomy.mockResolvedValue({
    profile: profile({ status: "paused" }),
    bridge: { status: "ready" },
  });
  adapterMock.stopAutonomy.mockResolvedValue({
    profile: profile({ status: "stopped" }),
    bridge: { status: "ready" },
  });
  adapterMock.updateAutonomyLimits.mockResolvedValue({
    profile: nextProfile,
    bridge: { status: "ready" },
  });
  adapterMock.previewAutonomyTick.mockResolvedValue({
    tick: tickResult(),
    bridge: { status: "ready" },
  });
  adapterMock.getPollerStatus.mockResolvedValue({
    pollerStatus: defaultPollerStatus(),
    bridge: { status: "ready" },
  });
  adapterMock.getTelegramCapabilitiesPanel.mockResolvedValue({
    caps: defaultTelegramCaps(),
    bridge: { status: "ready" },
  });
}

function renderSocial() {
  return render(
    <MemoryRouter initialEntries={["/workspace/social"]}>
      <WorkspaceSocialScreen />
    </MemoryRouter>,
  );
}

async function statusPanel() {
  return screen.findByRole("region", { name: /autonomy status/i });
}

async function previewButton() {
  return within(await statusPanel()).findByRole("button", { name: /preview tick/i });
}

describe("SocialStatusPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLoad();
  });

  it.each([
    ["running", "Running"],
    ["paused", "Paused"],
    ["stopped", "Stopped"],
  ] as const)("renders %s badge when profile status is %s", async (status, label) => {
    mockLoad(profile({ status }));

    renderSocial();

    const panel = await statusPanel();
    expect(within(panel).getByRole("status", { name: label })).toHaveTextContent(label);
  });

  it("renders neutral state when profile is missing", async () => {
    mockLoad(null);

    renderSocial();

    const panel = await statusPanel();
    expect(within(panel).getByRole("status", { name: /unknown/i })).toBeInTheDocument();
    expect(within(panel).queryByRole("status", { name: "Running" })).not.toBeInTheDocument();
    expect(await previewButton()).toBeDisabled();
  });

  it("renders neutral state when status is unknown", async () => {
    mockLoad(profile({ status: "armed" }));

    renderSocial();

    const panel = await statusPanel();
    expect(within(panel).getByRole("status", { name: /unknown/i })).toBeInTheDocument();
    expect(within(panel).queryByRole("status", { name: "Running" })).not.toBeInTheDocument();
  });

  it("renders last tick timestamp and action count when present", async () => {
    mockLoad(
      profile({
        last_tick_summary: {
          ran: true,
          dry_run: true,
          actions_considered: ["x:reply", "telegram:message"],
          actions_taken: ["x:reply"],
          blocked_reasons: [],
          profile_status: "running",
          recorded_at: "2026-05-20T12:30:00Z",
          next_run_summary: "Next due tomorrow.",
        },
      }),
    );

    renderSocial();

    const panel = await statusPanel();
    expect(panel).toHaveTextContent("2026-05-20 12:30:00 UTC");
    expect(panel).toHaveTextContent(/2 considered/i);
    expect(panel).toHaveTextContent(/1 taken/i);
  });

  it("renders next run timestamp when present", async () => {
    mockLoad(profile({ next_run_at: "2026-05-21T08:15:00Z" }));

    renderSocial();

    expect(await statusPanel()).toHaveTextContent("2026-05-21 08:15:00 UTC");
  });

  it("renders dash placeholders when last tick and next run are null", async () => {
    mockLoad(profile({ last_tick_summary: null, next_run_at: null }));

    renderSocial();

    const panel = await statusPanel();
    expect(within(panel).getByTestId("social-status-last-tick")).toHaveTextContent("—");
    expect(within(panel).getByTestId("social-status-next-run")).toHaveTextContent("—");
    expect(panel).not.toHaveTextContent(/null|undefined/i);
  });

  it("coexists with Mission 12 cards and renders inline", async () => {
    renderSocial();

    expect(await statusPanel()).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /launch state/i })).toBeInTheDocument();
    for (const name of [/goal/i, /channels/i, /limits/i, /safety boundaries/i]) {
      expect(screen.getByRole("region", { name })).toBeInTheDocument();
    }
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it.each([
    ["running", true],
    ["paused", false],
    ["stopped", false],
    ["draft", false],
  ] as const)("sets Preview Tick enabled=%s for status %s", async (status, enabled) => {
    mockLoad(profile({ status }));

    renderSocial();

    const button = await previewButton();
    if (enabled) expect(button).toBeEnabled();
    else expect(button).toBeDisabled();
  });

  it("keeps Preview Tick enabled without the legacy write token", async () => {
    mockLoad(profile({ status: "running" }));

    renderSocial();

    expect(await previewButton()).toBeEnabled();
  });

  it("clicking Preview Tick calls adapter with dry_run true and renders summary", async () => {
    adapterMock.previewAutonomyTick.mockResolvedValue({
      tick: tickResult({
        actions_considered: ["x:reply", "x:broadcast", "telegram:message"],
        actions_taken: [],
        blocked_reasons: ["autonomy_cadence_not_due"],
        profile_status: "running",
      }),
      bridge: { status: "ready" },
    });
    renderSocial();

    fireEvent.click(await previewButton());

    await waitFor(() =>
      expect(adapterMock.previewAutonomyTick).toHaveBeenCalledWith({ dry_run: true }),
    );
    const panel = await statusPanel();
    expect(panel).toHaveTextContent(/3 considered/i);
    expect(panel).toHaveTextContent(/0 taken/i);
    expect(panel).toHaveTextContent("autonomy_cadence_not_due");
    expect(panel).toHaveTextContent(/profile status:\s*running/i);
  });

  it("shows loading state and blocks concurrent preview requests", async () => {
    let resolvePreview!: (value: {
      tick: SocialAutonomyTickResult;
      bridge: { status: "ready" };
    }) => void;
    adapterMock.previewAutonomyTick.mockReturnValue(
      new Promise((resolve) => {
        resolvePreview = resolve;
      }),
    );
    renderSocial();

    const button = await previewButton();
    fireEvent.click(button);
    fireEvent.click(button);

    expect(
      await within(await statusPanel()).findByRole("button", { name: /previewing/i }),
    ).toBeDisabled();
    expect(adapterMock.previewAutonomyTick).toHaveBeenCalledTimes(1);

    resolvePreview({ tick: tickResult(), bridge: { status: "ready" } });
    await waitFor(() => expect(adapterMock.previewAutonomyTick).toHaveBeenCalledTimes(1));
  });

  it("renders neutral preview error without raw payload leaks", async () => {
    adapterMock.previewAutonomyTick.mockResolvedValue({
      tick: null,
      bridge: { status: "pending", detail: "HTTP 500" },
      error: `HTTP 500 workspace_id draft_id record_id ${["HAM", "SOCIAL", "LIVE", "APPLY", "TOKEN"].join("_")}`,
    });
    renderSocial();

    fireEvent.click(await previewButton());

    const panel = await statusPanel();
    await waitFor(() => expect(panel).toHaveTextContent("Preview tick failed."));
    expect(panel).not.toHaveTextContent("workspace_id");
    expect(panel).not.toHaveTextContent("draft_id");
    expect(panel).not.toHaveTextContent("record_id");
    expect(panel).not.toHaveTextContent(["HAM", "SOCIAL", "LIVE", "APPLY", "TOKEN"].join("_"));
  });

  it("does not render retired live controls or sensitive inputs in the status panel", async () => {
    const retiredLabels = [
      ["Send", "live"].join(" "),
      ["Run", "live"].join(" "),
      ["Run", "once", "live"].join(" "),
      ["Send", "one", "live"].join(" "),
    ];

    renderSocial();

    const panel = await statusPanel();
    for (const label of retiredLabels) {
      expect(
        within(panel).queryByRole("button", { name: new RegExp(`^${label}$`, "i") }),
      ).toBeNull();
    }
    expect(within(panel).queryByRole("button", { name: /^apply\b/i })).toBeNull();
    expect(within(panel).queryByLabelText(/token/i)).toBeNull();
    expect(within(panel).queryByPlaceholderText(/token/i)).toBeNull();
    expect(
      screen.queryByLabelText(new RegExp(["confirmation", "phrase"].join("\\s+"), "i")),
    ).toBeNull();
    expect(screen.queryByText(new RegExp(["live", "token"].join("\\s*"), "i"))).toBeNull();
  });

  it("updates the status panel when profile state changes through Mission 12 controls", async () => {
    mockLoad(profile({ status: "draft" }));
    renderSocial();

    const writeTokenInput = await screen.findByLabelText(
      "HAM_SOCIAL_AUTONOMY_WRITE_TOKEN (session only)",
    );
    fireEvent.change(writeTokenInput, { target: { value: "session-write-token" } });
    fireEvent.click(screen.getByRole("button", { name: /^Launch$/i }));

    await waitFor(() =>
      expect(
        within(screen.getByRole("region", { name: /autonomy status/i })).getByRole("status", {
          name: "Running",
        }),
      ).toBeInTheDocument(),
    );
  });

  // ── M4 VAL-M15-M4-UI-001: Storage backend row ──────────────────────────────

  it("VAL-M15-M4-UI-001: renders storage backend row when profile returns firestore", async () => {
    mockLoad(profile({ storage: { backend: "firestore" } } as Partial<GoHamSocialProfile>));
    renderSocial();
    const panel = await statusPanel();
    expect(within(panel).getByTestId("social-status-storage-backend")).toHaveTextContent(
      "firestore",
    );
  });

  it("VAL-M15-M4-UI-001: renders storage backend row as file", async () => {
    mockLoad(profile({ storage: { backend: "file" } } as Partial<GoHamSocialProfile>));
    renderSocial();
    const panel = await statusPanel();
    expect(within(panel).getByTestId("social-status-storage-backend")).toHaveTextContent("file");
  });

  it("VAL-M15-M4-UI-001: hides storage backend row when field is absent", async () => {
    mockLoad(profile());
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() =>
      expect(within(panel).queryByTestId("social-status-storage-backend")).toBeNull(),
    );
  });

  // ── M4 VAL-M15-M4-UI-002: Telegram readiness row (split from Hermes) ───────

  it("VAL-M15-M4-UI-002: renders Telegram readiness row as ready regardless of Hermes state", async () => {
    adapterMock.getTelegramCapabilitiesPanel.mockResolvedValue({
      caps: {
        telegram_readiness: "ready",
        hermes_gateway_readiness: "unknown",
        social_critic: null,
      },
      bridge: { status: "ready" },
    });
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() =>
      expect(within(panel).getByTestId("social-status-telegram-readiness")).toHaveTextContent(
        "ready",
      ),
    );
  });

  it("VAL-M15-M4-UI-002: renders Telegram readiness as setup_required", async () => {
    adapterMock.getTelegramCapabilitiesPanel.mockResolvedValue({
      caps: { telegram_readiness: "setup_required", hermes_gateway_readiness: null, social_critic: null },
      bridge: { status: "ready" },
    });
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() =>
      expect(within(panel).getByTestId("social-status-telegram-readiness")).toHaveTextContent(
        "setup_required",
      ),
    );
  });

  it("VAL-M15-M4-UI-002: hides Telegram readiness row when absent", async () => {
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() =>
      expect(within(panel).queryByTestId("social-status-telegram-readiness")).toBeNull(),
    );
  });

  // ── M4 VAL-M15-M4-UI-003: Hermes critique status row ───────────────────────

  it("VAL-M15-M4-UI-003: renders Hermes critique row as not configured", async () => {
    adapterMock.getTelegramCapabilitiesPanel.mockResolvedValue({
      caps: {
        telegram_readiness: null,
        hermes_gateway_readiness: null,
        social_critic: { status: "not configured" },
      },
      bridge: { status: "ready" },
    });
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() =>
      expect(within(panel).getByTestId("social-status-hermes-critique")).toHaveTextContent(
        "not configured",
      ),
    );
  });

  it("VAL-M15-M4-UI-003: renders Hermes critique row as available", async () => {
    adapterMock.getTelegramCapabilitiesPanel.mockResolvedValue({
      caps: {
        telegram_readiness: null,
        hermes_gateway_readiness: null,
        social_critic: { status: "available" },
      },
      bridge: { status: "ready" },
    });
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() =>
      expect(within(panel).getByTestId("social-status-hermes-critique")).toHaveTextContent(
        "available",
      ),
    );
  });

  it("VAL-M15-M4-UI-003: hides Hermes critique row when social_critic is absent", async () => {
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() =>
      expect(within(panel).queryByTestId("social-status-hermes-critique")).toBeNull(),
    );
  });

  // ── M4 VAL-M15-M4-UI-004: Poller status row ────────────────────────────────

  it("VAL-M15-M4-UI-004: renders poller status rows when pollerStatus data is present", async () => {
    adapterMock.getPollerStatus.mockResolvedValue({
      pollerStatus: {
        last_run_at: "2026-05-22T00:00:00Z",
        last_offset: 42,
        transcript_count_today: 3,
        last_error_code: null,
      },
      bridge: { status: "ready" },
    });
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() => {
      expect(within(panel).getByTestId("social-status-poller-last-run")).toHaveTextContent(
        "2026-05-22 00:00:00 UTC",
      );
      expect(within(panel).getByTestId("social-status-poller-offset")).toHaveTextContent("42");
      expect(within(panel).getByTestId("social-status-poller-transcript-count")).toHaveTextContent(
        "3",
      );
    });
  });

  it("VAL-M15-M4-UI-004: hides poller rows and shows no raw error when adapter rejects", async () => {
    adapterMock.getPollerStatus.mockRejectedValue(new Error("HTTP 500 workspace_id draft_id"));
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() =>
      expect(within(panel).queryByTestId("social-status-poller")).toBeNull(),
    );
    expect(panel).not.toHaveTextContent("workspace_id");
    expect(panel).not.toHaveTextContent("draft_id");
  });

  // ── M4 VAL-M15-M4-UI-005: Scheduler-route state row ───────────────────────

  it("VAL-M15-M4-UI-005: renders scheduler route row as disabled", async () => {
    mockLoad(
      profile({ scheduler_route: { state: "disabled" } } as Partial<GoHamSocialProfile>),
    );
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() =>
      expect(within(panel).getByTestId("social-status-scheduler-route")).toHaveTextContent(
        "disabled",
      ),
    );
  });

  it("VAL-M15-M4-UI-005: renders scheduler route row as dry-run-only", async () => {
    mockLoad(
      profile({ scheduler_route: { state: "dry-run-only" } } as Partial<GoHamSocialProfile>),
    );
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() =>
      expect(within(panel).getByTestId("social-status-scheduler-route")).toHaveTextContent(
        "dry-run-only",
      ),
    );
  });

  it("VAL-M15-M4-UI-005: hides scheduler route row when absent", async () => {
    mockLoad(profile());
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() =>
      expect(within(panel).queryByTestId("social-status-scheduler-route")).toBeNull(),
    );
  });

  // ── M4 VAL-M15-M4-UI-006: Cap usage today row ──────────────────────────────

  it("VAL-M15-M4-UI-006: renders cap usage today row per channel", async () => {
    mockLoad(
      profile({
        usage_today: { telegram: { messages: 0, replies: 0 } },
      } as Partial<GoHamSocialProfile>),
    );
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() => {
      const capRow = within(panel).getByTestId("social-status-cap-usage");
      expect(capRow).toHaveTextContent("telegram");
      expect(capRow).toHaveTextContent("0");
    });
  });

  it("VAL-M15-M4-UI-006: hides cap usage row when absent", async () => {
    mockLoad(profile());
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() =>
      expect(within(panel).queryByTestId("social-status-cap-usage")).toBeNull(),
    );
  });

  // ── M4 VAL-M15-M4-UI-007: Last tick summary (existing row preserved) ───────

  it("VAL-M15-M4-UI-007: last-tick row still renders with timestamp and counts", async () => {
    mockLoad(
      profile({
        last_tick_summary: {
          ran: true,
          dry_run: true,
          actions_considered: ["x:reply", "telegram:message"],
          actions_taken: ["x:reply"],
          blocked_reasons: [],
          profile_status: "running",
          recorded_at: "2026-05-22T00:00:00Z",
          next_run_summary: null,
        },
      }),
    );
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() => {
      expect(within(panel).getByTestId("social-status-last-tick")).toHaveTextContent(
        "2026-05-22 00:00:00 UTC",
      );
      expect(within(panel).getByTestId("social-status-last-tick")).toHaveTextContent(
        "2 considered",
      );
      expect(within(panel).getByTestId("social-status-last-tick")).toHaveTextContent("1 taken");
    });
  });

  // ── M4 VAL-M15-M4-UI-008: Last blocked reason row ──────────────────────────

  it("VAL-M15-M4-UI-008: renders last blocked reason when present", async () => {
    mockLoad(
      profile({
        last_tick_summary: {
          ran: false,
          dry_run: true,
          actions_considered: [],
          actions_taken: [],
          blocked_reasons: ["AUTONOMY_QUIET_HOURS_ACTIVE"],
          profile_status: "running",
          recorded_at: "2026-05-22T00:00:00Z",
          next_run_summary: null,
        },
      }),
    );
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() =>
      expect(within(panel).getByTestId("social-status-last-blocked")).toHaveTextContent(
        "AUTONOMY_QUIET_HOURS_ACTIVE",
      ),
    );
  });

  it("VAL-M15-M4-UI-008: hides last blocked reason row when list is empty", async () => {
    mockLoad(
      profile({
        last_tick_summary: {
          ran: true,
          dry_run: true,
          actions_considered: ["x:reply"],
          actions_taken: ["x:reply"],
          blocked_reasons: [],
          profile_status: "running",
          recorded_at: "2026-05-22T00:00:00Z",
          next_run_summary: null,
        },
      }),
    );
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() =>
      expect(within(panel).queryByTestId("social-status-last-blocked")).toBeNull(),
    );
  });

  it("VAL-M15-M4-UI-008: hides last blocked reason row when last_tick_summary is null", async () => {
    mockLoad(profile({ last_tick_summary: null }));
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() =>
      expect(within(panel).queryByTestId("social-status-last-blocked")).toBeNull(),
    );
  });

  // ── M4 VAL-M15-M4-UI-009: Emergency stop indicator ─────────────────────────

  it("VAL-M15-M4-UI-009: renders emergency stop indicator as active when true", async () => {
    mockLoad(profile({ emergency_stop: true }));
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() =>
      expect(within(panel).getByTestId("social-status-emergency-stop")).toHaveTextContent(
        "active",
      ),
    );
  });

  it("VAL-M15-M4-UI-009: renders emergency stop indicator as inactive when false", async () => {
    mockLoad(profile({ emergency_stop: false }));
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() =>
      expect(within(panel).getByTestId("social-status-emergency-stop")).toHaveTextContent(
        "inactive",
      ),
    );
  });

  // ── M4 VAL-M15-M4-UI-010: Learning summary row ──────────────────────────────

  it("VAL-M15-M4-UI-010: renders learning summary row when hints are present", async () => {
    adapterMock.getLearningHints.mockResolvedValue({
      hints: {
        hints: "Keep messages short and on-topic.",
        generated_at: "2026-05-22T00:00:00Z",
      },
      bridge: { status: "ready" },
    });
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() =>
      expect(within(panel).getByTestId("social-status-learning")).toBeInTheDocument(),
    );
  });

  it("VAL-M15-M4-UI-010: hides learning summary row when hints call rejects", async () => {
    adapterMock.getLearningHints.mockRejectedValue(new Error("network error"));
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() =>
      expect(within(panel).queryByTestId("social-status-learning")).toBeNull(),
    );
  });

  // ── M4 VAL-M15-M4-UI-NEGATIVE: Negative pins (extended / re-confirmed) ──────

  it("VAL-M15-M4-UI-NEGATIVE-001: no Approve canary button anywhere on the page", async () => {
    renderSocial();
    await statusPanel();
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /approve.*canary/i })).toBeNull();
      expect(screen.queryByRole("button", { name: /canary.*approve/i })).toBeNull();
    });
  });

  it("VAL-M15-M4-UI-NEGATIVE-002: no Send live / Run live / Run once live / Send one live button", async () => {
    renderSocial();
    await statusPanel();
    await waitFor(() => {
      for (const pattern of [
        /send live/i,
        /run live/i,
        /run once live/i,
        /send one live/i,
        /apply.*live/i,
      ]) {
        expect(screen.queryByRole("button", { name: pattern })).toBeNull();
      }
    });
  });

  it("VAL-M15-M4-UI-NEGATIVE-003: no bot-token field and no confirmation-phrase field", async () => {
    renderSocial();
    await statusPanel();
    await waitFor(() => {
      expect(screen.queryByLabelText(/bot token/i)).toBeNull();
      expect(screen.queryByLabelText(/telegram.*token/i)).toBeNull();
      expect(screen.queryByPlaceholderText(/confirmation phrase/i)).toBeNull();
    });
  });

  it("VAL-M15-M4-UI-NEGATIVE-004: no mode picker, no cockpit, no policy editor", async () => {
    renderSocial();
    await statusPanel();
    await waitFor(() => {
      expect(screen.queryByText(/mode.*picker/i)).toBeNull();
      expect(screen.queryByText(/cockpit/i)).toBeNull();
      expect(screen.queryByText(/policy editor/i)).toBeNull();
    });
  });

  it("VAL-M15-M4-UI-NEGATIVE-006: raw error payloads do not leak into DOM from new rows", async () => {
    const sensitiveToken = "HAM_SOCIAL_LIVE_APPLY_TOKEN=synthetic-XYZ";
    const sensitiveId = "123456789012345678";
    const sensitiveError = new Error(`${sensitiveToken} ${sensitiveId}`);
    adapterMock.getPollerStatus.mockRejectedValue(sensitiveError);
    adapterMock.getTelegramCapabilitiesPanel.mockRejectedValue(sensitiveError);
    renderSocial();
    const panel = await statusPanel();
    await waitFor(() => {
      expect(panel).not.toHaveTextContent("synthetic-XYZ");
      expect(panel).not.toHaveTextContent(sensitiveId);
    });
  });
});
