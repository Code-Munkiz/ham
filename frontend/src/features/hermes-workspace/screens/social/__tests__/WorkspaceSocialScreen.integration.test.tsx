import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { setupServer } from "msw/node";
import * as React from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { GoHamSocialProfile } from "@/features/hermes-workspace/adapters/socialAdapter";

import { WorkspaceRoutes } from "@/features/hermes-workspace/WorkspaceApp";

import { WorkspaceSocialScreen } from "../WorkspaceSocialScreen";

type RecordedRequest = {
  url: string;
  method: string;
  body: unknown;
  authorization: string | null;
  operatorAuthorization: string | null;
};

type BackendOptions = {
  profile?: GoHamSocialProfile | Record<string, unknown>;
  learningStatus?: number;
  learningHints?: string;
  writesEnabled?: boolean;
};

const API_ORIGIN = "http://localhost";
const WRITE_TOKEN = "session-write-token";
const TOKEN_NAME = ["HAM", "SOCIAL", "LIVE", "APPLY", "TOKEN"].join("_");
const POLICY_CODE = ["policy", "setup_required"].join("_");

const server = setupServer();

function baseProfile(overrides: Partial<GoHamSocialProfile> = {}): GoHamSocialProfile {
  const profile: GoHamSocialProfile = {
    profile_id: "profile-1",
    workspace_id: null,
    project_id: null,
    status: "draft",
    goal: "grow awareness",
    persona_id: "ham-canonical",
    channels: {
      x: { enabled: true, available: true },
      telegram: { enabled: true, available: true },
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
    safety_rules: [
      "no spam",
      "no mass tagging",
      "no financial promises",
      "no credential requests",
      "emergency stop available",
    ],
    learning_enabled: true,
    emergency_stop: false,
    created_at: "2026-05-20T00:00:00Z",
    updated_at: "2026-05-20T00:00:00Z",
  };
  return { ...profile, ...overrides };
}

function api(path: string): string {
  return `${API_ORIGIN}${path}`;
}

function pathOf(rawUrl: string): string {
  return new URL(rawUrl).pathname;
}

async function recordRequest(request: Request): Promise<RecordedRequest> {
  let body: unknown = null;
  if (request.method !== "GET" && request.method !== "HEAD") {
    body = await request
      .clone()
      .json()
      .catch(() => null);
  }
  return {
    url: request.url,
    method: request.method.toUpperCase(),
    body,
    authorization: request.headers.get("authorization"),
    operatorAuthorization: request.headers.get("x-ham-operator-authorization"),
  };
}

function installMswBackend(options: BackendOptions = {}) {
  let profile: GoHamSocialProfile | Record<string, unknown> = options.profile ?? baseProfile();
  const calls: RecordedRequest[] = [];

  server.use(
    http.get(api("/api/social/autonomy/write-status"), async ({ request }) => {
      calls.push(await recordRequest(request));
      return HttpResponse.json({
        kind: "ham_social_autonomy_write_status",
        writes_enabled: options.writesEnabled ?? true,
      });
    }),
    http.get(api("/api/social/autonomy"), async ({ request }) => {
      calls.push(await recordRequest(request));
      return HttpResponse.json(profile);
    }),
    http.post(api("/api/social/autonomy/launch"), async ({ request }) => {
      calls.push(await recordRequest(request));
      profile = { ...baseProfile(), ...profile, status: "running", emergency_stop: false };
      return HttpResponse.json(profile);
    }),
    http.post(api("/api/social/autonomy/pause"), async ({ request }) => {
      calls.push(await recordRequest(request));
      profile = { ...baseProfile(), ...profile, status: "paused" };
      return HttpResponse.json(profile);
    }),
    http.post(api("/api/social/autonomy/stop"), async ({ request }) => {
      const call = await recordRequest(request);
      calls.push(call);
      const emergency = Boolean((call.body as { emergency_stop?: boolean } | null)?.emergency_stop);
      profile = { ...baseProfile(), ...profile, status: "stopped", emergency_stop: emergency };
      return HttpResponse.json(profile);
    }),
    http.patch(api("/api/social/autonomy/settings"), async ({ request }) => {
      const call = await recordRequest(request);
      calls.push(call);
      const body = call.body as {
        daily_caps?: GoHamSocialProfile["daily_caps"];
        quiet_hours?: GoHamSocialProfile["quiet_hours"];
      } | null;
      profile = {
        ...baseProfile(),
        ...profile,
        daily_caps: {
          ...(profile as GoHamSocialProfile).daily_caps,
          ...(body?.daily_caps ?? {}),
        },
        quiet_hours: body?.quiet_hours ?? (profile as GoHamSocialProfile).quiet_hours,
      };
      return HttpResponse.json(profile);
    }),
    http.get(api("/api/social/learning/hints"), async ({ request }) => {
      calls.push(await recordRequest(request));
      if (options.learningStatus && options.learningStatus >= 500) {
        return HttpResponse.json(
          {
            workspace_id: "ws-1",
            draft_id: "draft-1",
            record_id: "rec-1",
          },
          { status: options.learningStatus },
        );
      }
      return HttpResponse.json({
        hints: options.learningHints ?? "HAM learned to keep replies short and useful.",
        generated_at: "2026-05-20T00:00:00Z",
      });
    }),
    http.all(
      new RegExp(`${API_ORIGIN}/api/social/providers/(?:x|telegram)/.*/apply$`),
      async ({ request }) => {
        calls.push(await recordRequest(request));
        return HttpResponse.json(
          { detail: "apply endpoints are forbidden in this page test" },
          { status: 500 },
        );
      },
    ),
  );

  return {
    calls,
    getProfile: () => profile,
    callsTo: (path: string, method?: string) =>
      calls.filter((call) => pathOf(call.url) === path && (!method || call.method === method)),
    applyCalls: () =>
      calls.filter((call) =>
        /\/api\/social\/providers\/(?:x|telegram)\/.*\/apply$/.test(pathOf(call.url)),
      ),
  };
}

function renderSocial(initialPath = "/workspace/social") {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <WorkspaceSocialScreen />
    </MemoryRouter>,
  );
}

async function enterWriteToken(token = WRITE_TOKEN) {
  const input = await screen.findByLabelText("HAM_SOCIAL_AUTONOMY_WRITE_TOKEN (session only)");
  fireEvent.change(input, { target: { value: token } });
  return input;
}

async function waitForLaunchState() {
  return screen.findByRole("region", { name: /launch state/i });
}

beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
});

beforeEach(() => {
  vi.stubEnv("VITE_HAM_API_BASE", API_ORIGIN);
  vi.stubEnv("VITE_CLERK_PUBLISHABLE_KEY", "");
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

afterAll(() => {
  server.close();
});

describe("WorkspaceSocialScreen API integration flows", () => {
  it("round-trips launch, pause, resume, and stop through the autonomy API surface", async () => {
    const backend = installMswBackend({ profile: baseProfile({ status: "draft" }) });
    renderSocial();
    await enterWriteToken();

    fireEvent.click(await screen.findByRole("button", { name: /^Launch$/i }));
    await waitFor(() =>
      expect((backend.getProfile() as GoHamSocialProfile).status).toBe("running"),
    );
    expect(backend.callsTo("/api/social/autonomy/launch", "POST")).toHaveLength(1);
    expect(backend.callsTo("/api/social/autonomy/launch", "POST")[0]?.authorization).toBe(
      `Bearer ${WRITE_TOKEN}`,
    );
    expect(backend.callsTo("/api/social/autonomy", "GET").at(-1)).toBeTruthy();
    const runningState = await waitForLaunchState();
    expect(within(runningState).getByRole("button", { name: /^Pause$/i })).toBeInTheDocument();
    expect(within(runningState).getByRole("button", { name: /^Stop$/i })).toBeInTheDocument();
    expect(
      within(runningState).queryByRole("button", { name: /^Launch$/i }),
    ).not.toBeInTheDocument();

    fireEvent.click(within(runningState).getByRole("button", { name: /^Pause$/i }));
    await waitFor(() => expect((backend.getProfile() as GoHamSocialProfile).status).toBe("paused"));
    expect(backend.callsTo("/api/social/autonomy/pause", "POST")).toHaveLength(1);
    expect(await screen.findByRole("button", { name: /^Resume$/i })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^Resume$/i }));
    await waitFor(() =>
      expect((backend.getProfile() as GoHamSocialProfile).status).toBe("running"),
    );
    expect(backend.callsTo("/api/social/autonomy/launch", "POST")).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: /^Stop$/i }));
    await waitFor(() =>
      expect((backend.getProfile() as GoHamSocialProfile).status).toBe("stopped"),
    );
    expect(backend.callsTo("/api/social/autonomy/stop", "POST")).toHaveLength(1);
    expect(await screen.findByRole("button", { name: /^Launch$/i })).toBeEnabled();
  });

  it("round-trips stop from paused and emergency-stop persistence", async () => {
    const backend = installMswBackend({ profile: baseProfile({ status: "paused" }) });
    renderSocial();
    await enterWriteToken();

    fireEvent.click(await screen.findByRole("button", { name: /^Stop$/i }));
    await waitFor(() =>
      expect((backend.getProfile() as GoHamSocialProfile).status).toBe("stopped"),
    );
    expect(await screen.findByRole("button", { name: /^Launch$/i })).toBeEnabled();

    cleanup();
    server.resetHandlers();
    const emergencyBackend = installMswBackend({ profile: baseProfile({ status: "running" }) });
    renderSocial();
    await enterWriteToken();
    fireEvent.click(await screen.findByRole("button", { name: /emergency.*stop/i }));
    await waitFor(() => {
      const current = emergencyBackend.getProfile() as GoHamSocialProfile;
      expect(current.status).toBe("stopped");
      expect(current.emergency_stop).toBe(true);
    });
    expect(emergencyBackend.callsTo("/api/social/autonomy/stop", "POST")[0]?.body).toEqual({
      emergency_stop: true,
    });
    expect(await screen.findByText(/emergency stop is active/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Launch$/i })).toBeDisabled();
  });

  it("patches limits without changing status and reflects backend states on first mount", async () => {
    const backend = installMswBackend({ profile: baseProfile({ status: "running" }) });
    renderSocial();
    await enterWriteToken();

    const limits = await screen.findByRole("region", { name: /limits/i });
    fireEvent.change(within(limits).getByLabelText(/posts.*per.*day/i), {
      target: { value: "8" },
    });
    fireEvent.change(within(limits).getByLabelText(/replies.*per.*day/i), {
      target: { value: "6" },
    });
    expect(within(limits).getByText("Total daily actions: 14")).toBeInTheDocument();
    fireEvent.click(within(limits).getByRole("button", { name: /save limits/i }));

    await waitFor(() =>
      expect((backend.getProfile() as GoHamSocialProfile).daily_caps).toEqual({
        x: 8,
        telegram: 6,
        discord: 0,
      }),
    );
    expect((backend.getProfile() as GoHamSocialProfile).status).toBe("running");
    expect(backend.callsTo("/api/social/autonomy/settings", "PATCH")).toHaveLength(1);

    cleanup();
    server.resetHandlers();
    installMswBackend({ profile: baseProfile({ status: "paused" }) });
    renderSocial();
    await enterWriteToken();
    expect(await screen.findByRole("button", { name: /^Resume$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Pause$/i })).not.toBeInTheDocument();

    cleanup();
    server.resetHandlers();
    installMswBackend({ profile: baseProfile({ status: "stopped" }) });
    renderSocial();
    await enterWriteToken();
    expect(await screen.findByRole("button", { name: /^Launch$/i })).toBeEnabled();
    expect(screen.queryByRole("button", { name: /^Pause$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Resume$/i })).not.toBeInTheDocument();
  });

  it("renders learning hints safely on happy path and 5xx fallback", async () => {
    installMswBackend({ learningHints: "HAM learned to ask one clear question." });
    renderSocial();
    const learned = await screen.findByRole("region", { name: /what.*HAM.*learned/i });
    expect(learned.textContent?.trim()).toBe(
      "What HAM learnedHAM learned to ask one clear question.",
    );

    cleanup();
    server.resetHandlers();
    installMswBackend({ learningStatus: 503 });
    renderSocial();
    const fallback = await screen.findByRole("region", { name: /what.*HAM.*learned/i });
    for (const marker of ['{"', '":[', '"workspace_id"', '"draft_id"', '"record_id"']) {
      expect(fallback.textContent ?? "").not.toContain(marker);
    }
  });

  it("does not call provider apply endpoints while exercising user controls", async () => {
    const backend = installMswBackend({ profile: baseProfile({ status: "draft" }) });
    renderSocial();
    await enterWriteToken();

    fireEvent.click(await screen.findByRole("button", { name: /^Launch$/i }));
    await screen.findByRole("button", { name: /^Pause$/i });
    fireEvent.click(screen.getByRole("button", { name: /^Pause$/i }));
    await screen.findByRole("button", { name: /^Resume$/i });
    fireEvent.click(screen.getByRole("button", { name: /^Resume$/i }));
    await screen.findByRole("button", { name: /^Stop$/i });
    fireEvent.click(screen.getByRole("button", { name: /^Stop$/i }));
    await screen.findByRole("button", { name: /^Launch$/i });
    const limits = screen.getByRole("region", { name: /limits/i });
    fireEvent.click(within(limits).getByRole("button", { name: /save limits/i }));
    await waitFor(() =>
      expect(backend.callsTo("/api/social/autonomy/settings", "PATCH")).toHaveLength(1),
    );
    fireEvent.click(screen.getByRole("button", { name: /emergency.*stop/i }));

    await waitFor(() =>
      expect(backend.callsTo("/api/social/autonomy/stop", "POST")).toHaveLength(2),
    );
    expect(backend.applyCalls()).toEqual([]);
  });

  it("handles invalid and sensitive backend payloads without a React crash or verbatim leaks", async () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { container } = renderSocialWithBackend({
      profile: { ...baseProfile(), status: "armed", reasons: [POLICY_CODE] },
      learningHints: `${TOKEN_NAME} ${POLICY_CODE}`,
    });

    expect(await screen.findByText(/could not be loaded safely/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Launch$/i })).toBeDisabled();
    expect(container.innerHTML).not.toContain(TOKEN_NAME);
    expect(container.innerHTML).not.toMatch(new RegExp(`\\b${POLICY_CODE}\\b`));
    expect(consoleSpy).not.toHaveBeenCalled();
  });
});

function renderSocialWithBackend(options: BackendOptions) {
  installMswBackend(options);
  return renderSocial();
}

function LocationProbe({ onPath }: { onPath: (path: string) => void }) {
  const location = useLocation();
  onPath(location.pathname);
  return null;
}

function renderRedirect(initialPath: string) {
  let observedPath = "";
  render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route
          path="/workspace/*"
          element={
            <>
              <LocationProbe onPath={(path) => (observedPath = path)} />
              <WorkspaceRoutes />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
  return () => observedPath;
}

describe("legacy Social redirects", () => {
  it("redirects legacy HAMgomoon and policy routes to the Social page using production routes", async () => {
    installMswBackend();
    const hamgomoonPath = renderRedirect("/workspace/hamgomoon");
    await screen.findByRole("heading", { name: /^Social$/ });
    expect(hamgomoonPath()).toBe("/workspace/social");
    expect(screen.queryByText(/drafts to review/i)).not.toBeInTheDocument();

    cleanup();
    server.resetHandlers();
    installMswBackend();
    const policyPath = renderRedirect("/workspace/social/policy");
    await screen.findByRole("heading", { name: /^Social$/ });
    expect(policyPath()).toBe("/workspace/social");
    expect(screen.queryByText(/preview \/ diff \/ apply/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(new RegExp(["type", "confirmation", "phrase"].join(" "), "i")),
    ).not.toBeInTheDocument();
  });
});
