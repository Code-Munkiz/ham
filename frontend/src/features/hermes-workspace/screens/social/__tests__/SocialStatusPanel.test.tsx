import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type {
  GoHamSocialProfile,
  SocialAutonomyTickResult,
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
});
