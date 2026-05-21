import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { clearClerkSessionTokenCacheMock, getRegisteredClerkSessionTokenMock } = vi.hoisted(() => ({
  clearClerkSessionTokenCacheMock: vi.fn(),
  getRegisteredClerkSessionTokenMock: vi.fn(),
}));

vi.mock("@/lib/ham/clerkSession", () => ({
  clearClerkSessionTokenCache: () => clearClerkSessionTokenCacheMock(),
  getRegisteredClerkSessionToken: (opts?: { forceRefresh?: boolean }) =>
    getRegisteredClerkSessionTokenMock(opts),
}));

import {
  socialAdapter,
  type GoHamSocialProfile,
  type SocialAutonomyTickResult,
} from "../socialAdapter";

type Recorded = {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: string | null;
};

function jsonResponse(status: number, payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function recordingFetch(impl: (input: Recorded) => Response): { recorded: Recorded[] } {
  const recorded: Recorded[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const rec: Recorded = {
        url: typeof input === "string" ? input : input.toString(),
        method: (init?.method ?? "GET").toUpperCase(),
        headers: {},
        body: typeof init?.body === "string" ? init.body : null,
      };
      new Headers(init?.headers as HeadersInit | undefined).forEach((value, key) => {
        rec.headers[key.toLowerCase()] = value;
      });
      recorded.push(rec);
      return impl(rec);
    }),
  );
  return { recorded };
}

const PROFILE: GoHamSocialProfile = {
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
  safety_rules: ["no spam"],
  learning_enabled: true,
  emergency_stop: false,
  created_at: "2026-05-20T00:00:00Z",
  updated_at: "2026-05-20T00:00:00Z",
};

beforeEach(() => {
  vi.unstubAllGlobals();
  vi.stubEnv("VITE_HAM_API_BASE", "");
  vi.stubEnv("VITE_CLERK_PUBLISHABLE_KEY", "");
  clearClerkSessionTokenCacheMock.mockClear();
  getRegisteredClerkSessionTokenMock.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe("socialAdapter autonomy methods", () => {
  it("getAutonomyProfile issues GET /api/social/autonomy", async () => {
    const { recorded } = recordingFetch(() => jsonResponse(200, PROFILE));
    const result = await socialAdapter.getAutonomyProfile();
    expect(result.profile).toEqual(PROFILE);
    expect(result.bridge.status).toBe("ready");
    expect(recorded[0]?.method).toBe("GET");
    expect(recorded[0]?.url).toMatch(/\/api\/social\/autonomy$/);
  });

  it("getAutonomyProfile maps errors", async () => {
    recordingFetch(() => jsonResponse(503, { detail: { error: { message: "offline" } } }));
    const result = await socialAdapter.getAutonomyProfile();
    expect(result.profile).toBeNull();
    expect(result.bridge.status).not.toBe("ready");
    expect(result.error).toBe("offline");
  });

  it("getAutonomyWriteStatus issues GET /api/social/autonomy/write-status", async () => {
    const { recorded } = recordingFetch(() =>
      jsonResponse(200, {
        kind: "ham_social_autonomy_write_status",
        writes_enabled: true,
      }),
    );
    const result = await socialAdapter.getAutonomyWriteStatus();
    expect(result.status).toEqual({
      kind: "ham_social_autonomy_write_status",
      writes_enabled: true,
    });
    expect(result.bridge.status).toBe("ready");
    expect(recorded[0]?.method).toBe("GET");
    expect(recorded[0]?.url).toMatch(/\/api\/social\/autonomy\/write-status$/);
  });

  it("previewAutonomyProfile posts the full profile", async () => {
    const { recorded } = recordingFetch(() =>
      jsonResponse(200, { ...PROFILE, goal: "announce updates" }),
    );
    const result = await socialAdapter.previewAutonomyProfile(PROFILE);
    expect(result.profile?.goal).toBe("announce updates");
    expect(result.bridge.status).toBe("ready");
    expect(recorded[0]?.method).toBe("POST");
    expect(recorded[0]?.url).toMatch(/\/api\/social\/autonomy\/preview$/);
    expect(JSON.parse(recorded[0]?.body ?? "{}")).toEqual(PROFILE);
  });

  it("previewAutonomyProfile maps errors", async () => {
    recordingFetch(() => jsonResponse(422, { detail: { error: { message: "invalid" } } }));
    const result = await socialAdapter.previewAutonomyProfile(PROFILE);
    expect(result.profile).toBeNull();
    expect(result.bridge.status).not.toBe("ready");
    expect(result.error).toBe("invalid");
  });

  it("launchAutonomy posts to launch", async () => {
    const { recorded } = recordingFetch(() => jsonResponse(200, { ...PROFILE, status: "running" }));
    const result = await socialAdapter.launchAutonomy();
    expect(result.profile?.status).toBe("running");
    expect(result.bridge.status).toBe("ready");
    expect(recorded[0]?.method).toBe("POST");
    expect(recorded[0]?.url).toMatch(/\/api\/social\/autonomy\/launch$/);
  });

  it("launchAutonomy maps errors", async () => {
    recordingFetch(() => jsonResponse(403, { detail: { error: { message: "write disabled" } } }));
    const result = await socialAdapter.launchAutonomy();
    expect(result.profile).toBeNull();
    expect(result.bridge.status).not.toBe("ready");
    expect(result.error).toBe("write disabled");
  });

  it("pauseAutonomy posts to pause", async () => {
    const { recorded } = recordingFetch(() => jsonResponse(200, { ...PROFILE, status: "paused" }));
    const result = await socialAdapter.pauseAutonomy();
    expect(result.profile?.status).toBe("paused");
    expect(result.bridge.status).toBe("ready");
    expect(recorded[0]?.method).toBe("POST");
    expect(recorded[0]?.url).toMatch(/\/api\/social\/autonomy\/pause$/);
  });

  it("pauseAutonomy maps errors", async () => {
    recordingFetch(() => jsonResponse(409, { detail: { error: { message: "bad transition" } } }));
    const result = await socialAdapter.pauseAutonomy();
    expect(result.profile).toBeNull();
    expect(result.bridge.status).not.toBe("ready");
    expect(result.error).toBe("bad transition");
  });

  it("stopAutonomy posts optional emergency-stop body", async () => {
    const { recorded } = recordingFetch(() =>
      jsonResponse(200, { ...PROFILE, status: "stopped", emergency_stop: true }),
    );
    const result = await socialAdapter.stopAutonomy({ emergency_stop: true });
    expect(result.profile?.status).toBe("stopped");
    expect(result.profile?.emergency_stop).toBe(true);
    expect(result.bridge.status).toBe("ready");
    expect(recorded[0]?.method).toBe("POST");
    expect(recorded[0]?.url).toMatch(/\/api\/social\/autonomy\/stop$/);
    expect(JSON.parse(recorded[0]?.body ?? "{}")).toEqual({ emergency_stop: true });
  });

  it("stopAutonomy maps errors", async () => {
    recordingFetch(() => jsonResponse(401, { detail: { error: { message: "auth required" } } }));
    const result = await socialAdapter.stopAutonomy();
    expect(result.profile).toBeNull();
    expect(result.bridge.status).not.toBe("ready");
    expect(result.error).toBe("auth required");
  });

  it("updateAutonomyLimits patches settings with limits payload", async () => {
    const payload = { daily_caps: { x: 4, telegram: 7, discord: 0 } };
    const { recorded } = recordingFetch(() =>
      jsonResponse(200, { ...PROFILE, daily_caps: payload.daily_caps }),
    );
    const result = await socialAdapter.updateAutonomyLimits(payload);
    expect(result.profile?.daily_caps).toEqual(payload.daily_caps);
    expect(result.bridge.status).toBe("ready");
    expect(recorded[0]?.method).toBe("PATCH");
    expect(recorded[0]?.url).toMatch(/\/api\/social\/autonomy\/settings$/);
    expect(JSON.parse(recorded[0]?.body ?? "{}")).toEqual(payload);
  });

  it("updateAutonomyLimits maps errors", async () => {
    recordingFetch(() => jsonResponse(422, { detail: { error: { message: "bad caps" } } }));
    const result = await socialAdapter.updateAutonomyLimits({ daily_caps: { x: -1 } });
    expect(result.profile).toBeNull();
    expect(result.bridge.status).not.toBe("ready");
    expect(result.error).toBe("bad caps");
  });

  it.each([
    ["launchAutonomy", () => socialAdapter.launchAutonomy("operator-token")],
    ["pauseAutonomy", () => socialAdapter.pauseAutonomy("operator-token")],
    ["stopAutonomy", () => socialAdapter.stopAutonomy({}, "operator-token")],
    [
      "updateAutonomyLimits",
      () => socialAdapter.updateAutonomyLimits({ daily_caps: { x: 2 } }, "operator-token"),
    ],
  ] as const)("%s sends HAM token on Authorization when Clerk is absent", async (_name, invoke) => {
    const { recorded } = recordingFetch(() => jsonResponse(200, PROFILE));

    await invoke();

    expect(recorded[0]?.headers.authorization).toBe("Bearer operator-token");
    expect(recorded[0]?.headers["x-ham-operator-authorization"]).toBeUndefined();
  });

  it.each([
    ["launchAutonomy", () => socialAdapter.launchAutonomy("operator-token")],
    ["pauseAutonomy", () => socialAdapter.pauseAutonomy("operator-token")],
    ["stopAutonomy", () => socialAdapter.stopAutonomy({}, "operator-token")],
    [
      "updateAutonomyLimits",
      () => socialAdapter.updateAutonomyLimits({ daily_caps: { x: 2 } }, "operator-token"),
    ],
  ] as const)(
    "%s sends HAM token on X-Ham-Operator-Authorization when Clerk Authorization exists",
    async (_name, invoke) => {
      vi.stubEnv("VITE_CLERK_PUBLISHABLE_KEY", "pk_test_mock");
      getRegisteredClerkSessionTokenMock.mockResolvedValue("clerk-jwt");
      const { recorded } = recordingFetch(() => jsonResponse(200, PROFILE));

      await invoke();

      expect(recorded[0]?.headers.authorization).toBe("Bearer clerk-jwt");
      expect(recorded[0]?.headers["x-ham-operator-authorization"]).toBe("Bearer operator-token");
    },
  );

  it("previewAutonomyTick method exists with dry_run signature", async () => {
    const input = { dry_run: true } satisfies Parameters<typeof socialAdapter.previewAutonomyTick>[0];
    const tick: SocialAutonomyTickResult = {
      ran: false,
      dry_run: true,
      actions_considered: [],
      actions_taken: [],
      blocked_reasons: ["autonomy_cadence_not_due"],
      next_run_summary: "Next due later.",
      profile_status: "running",
    };
    const { recorded } = recordingFetch(() => jsonResponse(200, tick));

    const result = await socialAdapter.previewAutonomyTick(input);

    expect(result.tick).toEqual(tick);
    expect(result.bridge.status).toBe("ready");
    expect(recorded[0]?.method).toBe("POST");
    expect(recorded[0]?.url).toMatch(/\/api\/social\/autonomy\/tick$/);
    expect(JSON.parse(recorded[0]?.body ?? "{}")).toEqual({ dry_run: true });
  });

  it("previewAutonomyTick maps non-2xx errors", async () => {
    recordingFetch(() => jsonResponse(500, { detail: { error: { message: "tick failed" } } }));
    const result = await socialAdapter.previewAutonomyTick({ dry_run: true });
    expect(result.tick).toBeNull();
    expect(result.bridge.status).not.toBe("ready");
    expect(result.error).toBe("tick failed");
  });

  it("previewAutonomyTick maps network failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("network down");
      }),
    );

    const result = await socialAdapter.previewAutonomyTick({ dry_run: true });

    expect(result.tick).toBeNull();
    expect(result.bridge.status).not.toBe("ready");
    expect(result.error).toBe("network down");
  });

  it("does not expose removed cockpit-only methods", () => {
    expect((socialAdapter as any).sendOneLiveReply).toBeUndefined();
    expect((socialAdapter as any).sendLiveReactiveBatch).toBeUndefined();
    expect((socialAdapter as any).sendOneLivePost).toBeUndefined();
    expect((socialAdapter as any).sendOneTelegramReactiveReply).toBeUndefined();
    expect((socialAdapter as any).sendOneTelegramActivity).toBeUndefined();
    expect((socialAdapter as any).sendOneTelegramMessage).toBeUndefined();
  });
});
