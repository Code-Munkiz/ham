/**
 * Tests for socialPolicyAdapter — D.3.
 *
 * Covers:
 *   - GET /api/social/policy strips project_root.
 *   - POST /preview happy path + 422 envelope.
 *   - POST /apply happy path + auth header + body shape.
 *   - POST /apply NEVER includes live_autonomy_phrase.
 *   - POST /apply with empty token → no operator auth header set.
 *   - 401/403/409/422 error mapping.
 *   - history / audit happy paths.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  applyPolicy,
  loadAudit,
  loadHistory,
  loadPolicy,
  newClientProposalId,
  previewPolicy,
  SocialPolicyApiError,
} from "../socialPolicyAdapter";

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

function recordingFetch(impl: (input: Recorded) => Response): {
  spy: ReturnType<typeof vi.fn>;
  recorded: Recorded[];
} {
  const recorded: Recorded[] = [];
  const spy = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const method = (init?.method ?? "GET").toUpperCase();
    const headers: Record<string, string> = {};
    const initHeaders = new Headers(init?.headers as HeadersInit | undefined);
    initHeaders.forEach((v, k) => {
      headers[k.toLowerCase()] = v;
    });
    const body = typeof init?.body === "string" ? (init.body as string) : null;
    const rec: Recorded = { url, method, headers, body };
    recorded.push(rec);
    return impl(rec);
  });
  vi.stubGlobal("fetch", spy);
  return { spy, recorded };
}

beforeEach(() => {
  vi.unstubAllGlobals();
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const SAMPLE_DOC = {
  schema_version: 1 as const,
  persona: { persona_id: "ham-canonical", persona_version: 1 },
  content_style: {
    tone: "warm" as const,
    length_preference: "standard" as const,
    emoji_policy: "sparingly" as const,
    nature_tags: [],
  },
  safety_rules: {
    blocked_topics: [],
    block_links: true,
    min_relevance: 0.75,
    consecutive_failure_stop: 2,
    policy_rejection_stop: 10,
  },
  providers: {
    x: {
      provider_id: "x" as const,
      posting_mode: "off" as const,
      reply_mode: "off" as const,
      posting_caps: { max_per_day: 1, max_per_run: 1, min_spacing_minutes: 120 },
      reply_caps: {
        max_per_15m: 5,
        max_per_hour: 20,
        max_per_user_per_day: 3,
        max_per_thread_per_day: 5,
        min_seconds_between: 60,
        batch_max_per_run: 1,
      },
      posting_actions_allowed: [],
      targets: [],
    },
    telegram: {
      provider_id: "telegram" as const,
      posting_mode: "off" as const,
      reply_mode: "off" as const,
      posting_caps: { max_per_day: 1, max_per_run: 1, min_spacing_minutes: 120 },
      reply_caps: {
        max_per_15m: 5,
        max_per_hour: 20,
        max_per_user_per_day: 3,
        max_per_thread_per_day: 5,
        min_seconds_between: 60,
        batch_max_per_run: 1,
      },
      posting_actions_allowed: [],
      targets: [],
    },
    discord: {
      provider_id: "discord" as const,
      posting_mode: "off" as const,
      reply_mode: "off" as const,
      posting_caps: { max_per_day: 1, max_per_run: 1, min_spacing_minutes: 120 },
      reply_caps: {
        max_per_15m: 5,
        max_per_hour: 20,
        max_per_user_per_day: 3,
        max_per_thread_per_day: 5,
        min_seconds_between: 60,
        batch_max_per_run: 1,
      },
      posting_actions_allowed: [],
      targets: [],
    },
  },
  autopilot_mode: "off" as const,
  live_autonomy_armed: false,
};

describe("loadPolicy", () => {
  it("returns parsed body and strips project_root", async () => {
    recordingFetch(() =>
      jsonResponse(200, {
        project_root: "/server/secret/path",
        write_target: ".ham/social_policy.json",
        exists: true,
        policy: SAMPLE_DOC,
        revision: "rev-123",
        writes_enabled: true,
        live_apply_token_present: false,
        read_only: true,
      }),
    );
    const res = await loadPolicy();
    expect((res as unknown as Record<string, unknown>).project_root).toBeUndefined();
    expect(res.exists).toBe(true);
    expect(res.revision).toBe("rev-123");
    expect(res.policy?.providers.x.provider_id).toBe("x");
  });

  it("throws SocialPolicyApiError on 4xx with envelope", async () => {
    recordingFetch(() =>
      jsonResponse(403, {
        detail: { error: { code: "SOCIAL_POLICY_AUTH_INVALID", message: "nope" } },
      }),
    );
    await expect(loadPolicy()).rejects.toBeInstanceOf(SocialPolicyApiError);
  });
});

describe("previewPolicy", () => {
  it("posts JSON body with full policy + client_proposal_id and strips project_root", async () => {
    const { recorded } = recordingFetch(() =>
      jsonResponse(200, {
        project_root: "/server/path",
        effective_before: SAMPLE_DOC,
        effective_after: SAMPLE_DOC,
        diff: [],
        warnings: [],
        write_target: ".ham/social_policy.json",
        proposal_digest: "abc",
        base_revision: "rev-123",
        live_autonomy_change: false,
      }),
    );
    const result = await previewPolicy({
      changes: { policy: SAMPLE_DOC },
      clientProposalId: "uuid-1",
    });
    expect((result as unknown as Record<string, unknown>).project_root).toBeUndefined();
    const req = recorded[0];
    expect(req.method).toBe("POST");
    expect(req.url).toContain("/api/social/policy/preview");
    expect(req.headers["content-type"]).toBe("application/json");
    const body = JSON.parse(req.body!) as {
      changes: { policy: typeof SAMPLE_DOC };
      client_proposal_id?: string;
    };
    expect(body.changes.policy).toEqual(SAMPLE_DOC);
    expect(body.client_proposal_id).toBe("uuid-1");
  });

  it("maps 422 to typed error", async () => {
    recordingFetch(() =>
      jsonResponse(422, {
        detail: {
          error: { code: "SOCIAL_POLICY_PREVIEW_INVALID", message: "bad" },
        },
      }),
    );
    await expect(previewPolicy({ changes: { policy: SAMPLE_DOC } })).rejects.toMatchObject({
      code: "SOCIAL_POLICY_PREVIEW_INVALID",
      status: 422,
    });
  });
});

describe("applyPolicy", () => {
  it("sends correct body shape and never includes live_autonomy_phrase", async () => {
    const { recorded } = recordingFetch(() =>
      jsonResponse(200, {
        project_root: "/server/path",
        backup_id: "b-1",
        audit_id: "a-1",
        effective_after: SAMPLE_DOC,
        diff_applied: [],
        new_revision: "rev-2",
        live_autonomy_change: false,
      }),
    );
    await applyPolicy({
      changes: { policy: SAMPLE_DOC },
      baseRevision: "rev-1",
      confirmationPhrase: "SAVE SOCIAL POLICY",
      writeToken: "TOKEN_VALUE_1234",
      clientProposalId: "uuid-2",
    });
    const req = recorded[0];
    expect(req.method).toBe("POST");
    expect(req.url).toContain("/api/social/policy/apply");
    const parsed = JSON.parse(req.body!) as Record<string, unknown>;
    expect(parsed.changes).toEqual({ policy: SAMPLE_DOC });
    expect(parsed.base_revision).toBe("rev-1");
    expect(parsed.confirmation_phrase).toBe("SAVE SOCIAL POLICY");
    expect(parsed.client_proposal_id).toBe("uuid-2");
    // CRITICAL: live_autonomy_phrase must never be in the apply body.
    expect(Object.prototype.hasOwnProperty.call(parsed, "live_autonomy_phrase")).toBe(false);
  });

  it("attaches operator token via Authorization or X-Ham-Operator-Authorization", async () => {
    const { recorded } = recordingFetch(() =>
      jsonResponse(200, {
        backup_id: "b",
        audit_id: "a",
        effective_after: SAMPLE_DOC,
        diff_applied: [],
        new_revision: "r",
        live_autonomy_change: false,
      }),
    );
    await applyPolicy({
      changes: { policy: SAMPLE_DOC },
      baseRevision: "rev-1",
      confirmationPhrase: "SAVE SOCIAL POLICY",
      writeToken: "TOKEN_VALUE_5678",
    });
    const req = recorded[0];
    const authPair = req.headers["authorization"] ?? req.headers["x-ham-operator-authorization"];
    expect(authPair).toBe("Bearer TOKEN_VALUE_5678");
  });

  it("does NOT attach operator auth when token is empty string", async () => {
    const { recorded } = recordingFetch(() =>
      jsonResponse(200, {
        backup_id: "b",
        audit_id: "a",
        effective_after: SAMPLE_DOC,
        diff_applied: [],
        new_revision: "r",
        live_autonomy_change: false,
      }),
    );
    await applyPolicy({
      changes: { policy: SAMPLE_DOC },
      baseRevision: "rev-1",
      confirmationPhrase: "SAVE SOCIAL POLICY",
      writeToken: "",
    });
    const req = recorded[0];
    expect(req.headers["x-ham-operator-authorization"]).toBeUndefined();
    // Authorization may be attached only if Clerk is wired; in tests with no
    // VITE_CLERK_PUBLISHABLE_KEY, mergeClerkAuthBearerIfNeeded is a no-op.
    expect(req.headers["authorization"]).toBeUndefined();
  });

  it("maps 401 SOCIAL_POLICY_AUTH_REQUIRED", async () => {
    recordingFetch(() =>
      jsonResponse(401, {
        detail: {
          error: { code: "SOCIAL_POLICY_AUTH_REQUIRED", message: "no" },
        },
      }),
    );
    await expect(
      applyPolicy({
        changes: { policy: SAMPLE_DOC },
        baseRevision: "rev-1",
        confirmationPhrase: "SAVE SOCIAL POLICY",
        writeToken: "x",
      }),
    ).rejects.toMatchObject({
      code: "SOCIAL_POLICY_AUTH_REQUIRED",
      status: 401,
    });
  });

  it("maps 409 SOCIAL_POLICY_REVISION_CONFLICT", async () => {
    recordingFetch(() =>
      jsonResponse(409, {
        detail: {
          error: { code: "SOCIAL_POLICY_REVISION_CONFLICT", message: "drift" },
        },
      }),
    );
    await expect(
      applyPolicy({
        changes: { policy: SAMPLE_DOC },
        baseRevision: "rev-1",
        confirmationPhrase: "SAVE SOCIAL POLICY",
        writeToken: "x",
      }),
    ).rejects.toMatchObject({
      code: "SOCIAL_POLICY_REVISION_CONFLICT",
      status: 409,
    });
  });

  it("maps 422 SOCIAL_POLICY_APPLY_INVALID", async () => {
    recordingFetch(() =>
      jsonResponse(422, {
        detail: {
          error: { code: "SOCIAL_POLICY_APPLY_INVALID", message: "bad" },
        },
      }),
    );
    await expect(
      applyPolicy({
        changes: { policy: SAMPLE_DOC },
        baseRevision: "rev-1",
        confirmationPhrase: "SAVE SOCIAL POLICY",
        writeToken: "x",
      }),
    ).rejects.toMatchObject({
      code: "SOCIAL_POLICY_APPLY_INVALID",
      status: 422,
    });
  });

  it("falls back to UNKNOWN on non-JSON error body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("oops", { status: 500 })),
    );
    await expect(
      applyPolicy({
        changes: { policy: SAMPLE_DOC },
        baseRevision: "rev-1",
        confirmationPhrase: "SAVE SOCIAL POLICY",
        writeToken: "x",
      }),
    ).rejects.toMatchObject({ code: "UNKNOWN", status: 500 });
  });
});

describe("loadHistory / loadAudit", () => {
  it("strips project_root from history", async () => {
    recordingFetch(() =>
      jsonResponse(200, {
        project_root: "/secret",
        backups: [{ backup_id: "b1", timestamp_iso: "t", size_bytes: 10 }],
        read_only: true,
      }),
    );
    const res = await loadHistory();
    expect((res as unknown as Record<string, unknown>).project_root).toBeUndefined();
    expect(res.backups).toHaveLength(1);
  });

  it("strips project_root from audit", async () => {
    recordingFetch(() =>
      jsonResponse(200, {
        project_root: "/secret",
        audits: [],
        read_only: true,
      }),
    );
    const res = await loadAudit();
    expect((res as unknown as Record<string, unknown>).project_root).toBeUndefined();
    expect(res.audits).toEqual([]);
  });
});

describe("newClientProposalId", () => {
  it("returns a non-empty string", () => {
    const id = newClientProposalId();
    expect(typeof id).toBe("string");
    expect(id.length).toBeGreaterThan(8);
  });
  it("returns distinct ids on consecutive calls", () => {
    const a = newClientProposalId();
    const b = newClientProposalId();
    expect(a).not.toBe(b);
  });
});
