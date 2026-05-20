import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { GoHamSocialProfile } from "@/features/hermes-workspace/adapters/socialAdapter";

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
import { WorkspaceRoutes } from "../../../WorkspaceApp";

function profile(overrides: Partial<GoHamSocialProfile> = {}): GoHamSocialProfile {
  const base: GoHamSocialProfile = {
    profile_id: "profile-1",
    workspace_id: null,
    project_id: null,
    status: "draft",
    goal: "grow awareness",
    persona_id: "ham-canonical",
    channels: {
      x: { enabled: true, available: true },
      telegram: { enabled: false, available: true },
      discord: { enabled: false, available: false },
    },
    actions_allowed_per_channel: {
      x: ["reply", "broadcast"],
      telegram: ["message", "activity"],
      discord: [],
    },
    daily_caps: { x: 3, telegram: 5, discord: 0 },
    cadence: "daily",
    quiet_hours: null,
    forbidden_topics: [],
    safety_rules: ["no spam", "no mass tagging", "no financial promises", "no credential requests"],
    learning_enabled: true,
    emergency_stop: false,
    created_at: "2026-05-20T00:00:00Z",
    updated_at: "2026-05-20T00:00:00Z",
  };
  return { ...base, ...overrides };
}

function mockLoad(
  nextProfile: GoHamSocialProfile = profile(),
  hints = "HAM learned to prefer concise replies.",
  writesEnabled = true,
) {
  adapterMock.getAutonomyProfile.mockResolvedValue({
    profile: nextProfile,
    bridge: { status: "ready" },
  });
  adapterMock.getLearningHints.mockResolvedValue({
    hints: { hints, generated_at: "2026-05-20T00:00:00Z" },
    bridge: { status: "ready" },
  });
  adapterMock.getAutonomyWriteStatus.mockResolvedValue({
    status: {
      kind: "ham_social_autonomy_write_status",
      writes_enabled: writesEnabled,
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
}

function renderScreen(initialPath = "/workspace/social") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <WorkspaceSocialScreen />
    </MemoryRouter>,
  );
}

async function fillSessionWriteToken(value = "session-write-token") {
  const input = await screen.findByLabelText("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN (session only)");
  fireEvent.change(input, { target: { value } });
  return input;
}

describe("WorkspaceSocialScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLoad();
  });

  it("renders the Social page header and product-direction subtitle", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { container } = renderScreen();
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: /^Social$/ })).toBeInTheDocument(),
    );
    expect(container.textContent ?? "").toContain(
      "Set goals, choose channels, set limits, and let HAM run your social presence.",
    );
    expect(consoleSpy).not.toHaveBeenCalled();
    consoleSpy.mockRestore();
  });

  it.each([
    ["draft", "Not launched", ["Launch"], ["Pause", "Stop", "Resume"]],
    ["running", "Running", ["Pause", "Stop"], ["Launch", "Resume"]],
    ["paused", "Paused", ["Resume", "Stop"], ["Launch", "Pause"]],
    ["stopped", "Stopped", ["Launch"], ["Pause", "Stop", "Resume"]],
  ] as const)(
    "maps status %s to the expected launch controls",
    async (status, label, visible, hidden) => {
      mockLoad(profile({ status }));
      renderScreen();
      const launchState = await screen.findByRole("region", { name: /launch state/i });
      await fillSessionWriteToken();
      expect(within(launchState).getByText(label)).toBeInTheDocument();
      for (const button of visible) {
        expect(within(launchState).getByRole("button", { name: button })).toBeEnabled();
      }
      for (const button of hidden) {
        expect(within(launchState).queryByRole("button", { name: button })).not.toBeInTheDocument();
      }
    },
  );

  it("keeps Launch disabled when emergency stop is active", async () => {
    mockLoad(profile({ status: "stopped", emergency_stop: true }));
    renderScreen();
    const launchState = await screen.findByRole("region", { name: /launch state/i });
    expect(within(launchState).getByText(/Emergency stopped/i)).toBeInTheDocument();
    expect(within(launchState).getByRole("button", { name: "Launch" })).toBeDisabled();
  });

  it("renders goal examples, channel badges, limits, and safety boundaries", async () => {
    renderScreen();
    const goal = await screen.findByRole("region", { name: /goal/i });
    for (const example of [
      "grow awareness",
      "announce updates",
      "engage community",
      "educate users",
      "launch campaign",
    ]) {
      expect(within(goal).getAllByText(new RegExp(example, "i")).length).toBeGreaterThan(0);
    }

    const channels = screen.getByRole("region", { name: /channels/i });
    expect(within(channels).getByText(/^X$/)).toBeInTheDocument();
    expect(within(channels).getByText("Telegram")).toBeInTheDocument();
    expect(within(channels).getByText("Discord")).toBeInTheDocument();
    expect(within(channels).getByText("Not available")).toBeInTheDocument();

    const limits = screen.getByRole("region", { name: /limits/i });
    expect(within(limits).getByLabelText(/posts.*per.*day/i)).toBeInTheDocument();
    expect(within(limits).getByLabelText(/replies.*per.*day/i)).toBeInTheDocument();
    expect(within(limits).queryByLabelText(/max.*actions.*per.*day/i)).not.toBeInTheDocument();
    expect(within(limits).getByText("Total daily actions: 8")).toBeInTheDocument();

    const safety = screen.getByRole("region", { name: /safety/i });
    for (const phrase of [
      "no spam",
      "no mass tagging",
      "no financial promises",
      "no credential requests",
      "emergency stop available",
    ]) {
      expect(safety.textContent ?? "").toMatch(new RegExp(phrase, "i"));
    }
  });

  it("renders safe learning hints and a safe recent activity summary", async () => {
    mockLoad(
      profile({ status: "running" }),
      'HAM learned to prefer concise replies.\n{"workspace_id":"ws-1","record_id":"rec-1","draft_id":"draft-1"}',
    );
    renderScreen();
    const learned = await screen.findByRole("region", { name: /what.*HAM.*learned/i });
    expect(adapterMock.getLearningHints).toHaveBeenCalledTimes(1);
    expect(learned.textContent ?? "").toContain("HAM learned to prefer concise replies.");
    for (const marker of ['{"', '":[', '"workspace_id"', '"draft_id"', '"record_id"']) {
      expect(learned.textContent ?? "").not.toContain(marker);
    }

    const activity = screen.getByRole("region", { name: /recent activity/i });
    expect(activity.textContent ?? "").toMatch(/operating inside the configured limits/i);
    for (const marker of ['{"', '":[', '"record_id"']) {
      expect(activity.textContent ?? "").not.toContain(marker);
    }
  });

  it("does not render legacy cockpit copy or operation controls", async () => {
    const { container } = renderScreen();
    await screen.findByRole("region", { name: /launch state/i });
    const banned = [
      "HAM_SOCIAL" + "_LIVE_APPLY_TOKEN",
      "Type confirmation" + " phrase",
      "Send one" + " live",
      "autonomous social" + " reach",
      "HAM " + "Social",
      "review " + "queue",
      "Advanced technical" + " proof",
      "HAM_X" + "_",
      "TELEGRAM_BOT" + "_TOKEN",
      "XAI_API" + "_KEY",
    ];
    for (const phrase of banned) {
      expect(container.innerHTML).not.toContain(phrase);
      expect(container.textContent ?? "").not.toContain(phrase);
    }
    expect(container.querySelectorAll(`input[placeholder="${banned[0]}"]`)).toHaveLength(0);
    for (const control of [/^approve$/i, /^reject$/i, /^retry$/i, /send now/i]) {
      expect(screen.queryByRole("button", { name: control })).not.toBeInTheDocument();
    }
    expect(screen.queryByRole("tab", { name: /technical proof/i })).not.toBeInTheDocument();
    expect(
      screen.queryByText(new RegExp(["advanced", "technical", "proof"].join(" "), "i")),
    ).not.toBeInTheDocument();
  });

  it("keeps mutating controls disabled until a session-only write token is entered", async () => {
    mockLoad(profile({ status: "running" }));
    renderScreen();
    const input = await screen.findByLabelText("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN (session only)");
    expect(input).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: /^Pause$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^Stop$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /emergency.*stop/i })).toBeDisabled();

    fireEvent.change(input, { target: { value: "session-write-token" } });

    expect(screen.getByRole("button", { name: /^Pause$/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /^Stop$/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /emergency.*stop/i })).toBeEnabled();
  });

  it("shows writes-disabled badge and disables buttons when server writes are off", async () => {
    mockLoad(profile({ status: "running" }), "HAM learned to prefer concise replies.", false);
    renderScreen();
    await fillSessionWriteToken();

    expect(await screen.findByText(/writes disabled/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Pause$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /^Stop$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /emergency.*stop/i })).toBeDisabled();
  });

  it("never logs the session-only write token", async () => {
    const spies = [
      vi.spyOn(console, "error").mockImplementation(() => undefined),
      vi.spyOn(console, "warn").mockImplementation(() => undefined),
      vi.spyOn(console, "log").mockImplementation(() => undefined),
    ];
    mockLoad(profile({ status: "draft" }));
    renderScreen();
    await fillSessionWriteToken("never-log-this-token");
    fireEvent.click(screen.getByRole("button", { name: /^Launch$/i }));
    await waitFor(() =>
      expect(adapterMock.launchAutonomy).toHaveBeenCalledWith("never-log-this-token"),
    );

    for (const spy of spies) {
      expect(JSON.stringify(spy.mock.calls)).not.toContain("never-log-this-token");
      spy.mockRestore();
    }
  });
});

function LocationProbe({ onPath }: { onPath: (path: string) => void }) {
  const location = useLocation();
  onPath(location.pathname);
  return null;
}

function renderRoute(initialPath: string) {
  let observed = "";
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route
          path="/workspace/*"
          element={
            <>
              <LocationProbe onPath={(path) => (observed = path)} />
              <WorkspaceRoutes />
            </>
          }
        />
        <Route path="*" element={<div data-testid="workspace-fallback" />} />
      </Routes>
    </MemoryRouter>,
  );
  return () => observed;
}

describe("Social route behavior", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLoad();
  });

  it("renders the simple Social page at /workspace/social", async () => {
    const getPath = renderRoute("/workspace/social");
    expect(await screen.findByRole("heading", { name: /^Social$/ })).toBeInTheDocument();
    expect(getPath()).toBe("/workspace/social");
    expect(screen.getByRole("region", { name: /launch state/i })).toBeInTheDocument();
    expect(screen.queryByText(/preview & send/i)).not.toBeInTheDocument();
  });

  it("redirects legacy social routes to /workspace/social", async () => {
    const hamgomoonPath = renderRoute("/workspace/hamgomoon");
    expect(await screen.findByRole("heading", { name: /^Social$/ })).toBeInTheDocument();
    expect(hamgomoonPath()).toBe("/workspace/social");

    cleanup();
    vi.clearAllMocks();
    mockLoad();
    const policyPath = renderRoute("/workspace/social/policy");
    expect(await screen.findByRole("heading", { name: /^Social$/ })).toBeInTheDocument();
    expect(policyPath()).toBe("/workspace/social");
  });

  it("does not mount operator or advanced social surfaces", () => {
    renderRoute("/workspace/social/operator");
    expect(
      screen.queryByText(new RegExp(["send", "one", "live"].join(" "), "i")),
    ).not.toBeInTheDocument();

    renderRoute("/workspace/social/advanced");
    expect(
      screen.queryByText(new RegExp(["advanced", "technical", "proof"].join(" "), "i")),
    ).not.toBeInTheDocument();
  });
});
