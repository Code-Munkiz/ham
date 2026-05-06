/**
 * HAM /api/social/policy adapter — D.3.
 *
 * Backend source of truth: src/api/social_policy.py (D.1).
 *
 * Hard rules:
 *   - Strip `project_root` from every server response so screens cannot
 *     accidentally render a server filesystem path.
 *   - Apply requests NEVER include `live_autonomy_phrase`. The editor cannot
 *     flip `live_autonomy_armed`, so the second phrase is unnecessary and
 *     intentionally not exposed.
 *   - The operator write token is only ever attached as the
 *     `X-Ham-Operator-Authorization` (or fallback `Authorization`) header via
 *     the existing `applyHamOperatorSecretHeaders` helper. It is never
 *     stored, never logged, never returned in error envelopes.
 */
import { apiUrl, applyHamOperatorSecretHeaders, hamApiFetch } from "@/lib/ham/api";

import { POLICY_PATHS } from "../screens/social/policy/lib/policyConstants";
import type {
  SocialPolicyApplyResponse,
  SocialPolicyAuditResponse,
  SocialPolicyChanges,
  SocialPolicyEndpointResponse,
  SocialPolicyHistoryResponse,
  SocialPolicyPreviewResponse,
  SocialPolicyServerError,
} from "../screens/social/policy/lib/policyTypes";

/**
 * Strip `project_root` from a parsed JSON object, if present, before any
 * downstream code can see it.
 */
function stripProjectRoot<T extends Record<string, unknown>>(
  obj: T | null | undefined,
): Omit<T, "project_root"> | null {
  if (!obj) return null;
  if (Object.prototype.hasOwnProperty.call(obj, "project_root")) {
    const { project_root: _ignored, ...rest } = obj as T & { project_root?: unknown };
    void _ignored;
    return rest as Omit<T, "project_root">;
  }
  return obj as Omit<T, "project_root">;
}

/** Server error envelope reader. Falls back to UNKNOWN if shape unexpected. */
async function readError(res: Response): Promise<SocialPolicyServerError> {
  let raw: unknown = null;
  try {
    raw = await res.json();
  } catch {
    return {
      status: res.status,
      code: "UNKNOWN",
      message: `HTTP ${res.status} ${res.statusText || ""}`.trim(),
    };
  }
  const detail =
    raw && typeof raw === "object" && "detail" in raw ? (raw as { detail: unknown }).detail : raw;
  if (detail && typeof detail === "object" && "error" in (detail as Record<string, unknown>)) {
    const errObj = (detail as { error?: unknown }).error;
    if (errObj && typeof errObj === "object") {
      const code = (errObj as { code?: unknown }).code;
      const message = (errObj as { message?: unknown }).message;
      if (typeof code === "string" && typeof message === "string") {
        return {
          status: res.status,
          code: code as SocialPolicyServerError["code"],
          message,
        };
      }
    }
  }
  return {
    status: res.status,
    code: "UNKNOWN",
    message:
      typeof detail === "string" ? detail : `HTTP ${res.status} ${res.statusText || ""}`.trim(),
  };
}

export class SocialPolicyApiError extends Error {
  status: number;
  code: SocialPolicyServerError["code"];
  constructor(envelope: SocialPolicyServerError) {
    super(envelope.message);
    this.name = "SocialPolicyApiError";
    this.status = envelope.status;
    this.code = envelope.code;
  }
}

/** GET /api/social/policy. */
export async function loadPolicy(): Promise<SocialPolicyEndpointResponse> {
  const res = await hamApiFetch(POLICY_PATHS.policy, { method: "GET" });
  if (!res.ok) {
    throw new SocialPolicyApiError(await readError(res));
  }
  const raw = (await res.json()) as Record<string, unknown>;
  return stripProjectRoot(raw) as unknown as SocialPolicyEndpointResponse;
}

/** POST /api/social/policy/preview. */
export async function previewPolicy(input: {
  changes: SocialPolicyChanges;
  clientProposalId?: string;
}): Promise<SocialPolicyPreviewResponse> {
  const body = JSON.stringify({
    changes: input.changes,
    ...(input.clientProposalId ? { client_proposal_id: input.clientProposalId } : {}),
  });
  const res = await hamApiFetch(POLICY_PATHS.preview, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  });
  if (!res.ok) {
    throw new SocialPolicyApiError(await readError(res));
  }
  const raw = (await res.json()) as Record<string, unknown>;
  return stripProjectRoot(raw) as unknown as SocialPolicyPreviewResponse;
}

/**
 * POST /api/social/policy/apply.
 *
 * `writeToken` is the operator-supplied bearer token. It is only attached
 * as the `X-Ham-Operator-Authorization` (or fallback `Authorization`)
 * header. The body NEVER includes `live_autonomy_phrase`.
 */
export async function applyPolicy(input: {
  changes: SocialPolicyChanges;
  baseRevision: string;
  confirmationPhrase: string;
  writeToken: string;
  clientProposalId?: string;
}): Promise<SocialPolicyApplyResponse> {
  const body = JSON.stringify({
    changes: input.changes,
    base_revision: input.baseRevision,
    confirmation_phrase: input.confirmationPhrase,
    ...(input.clientProposalId ? { client_proposal_id: input.clientProposalId } : {}),
    // INTENTIONALLY OMITTED: live_autonomy_phrase
  });

  const headers = new Headers({ "Content-Type": "application/json" });
  await applyHamOperatorSecretHeaders(headers, input.writeToken);

  const res = await fetch(apiUrl(POLICY_PATHS.apply), {
    method: "POST",
    headers,
    body,
  });
  if (!res.ok) {
    throw new SocialPolicyApiError(await readError(res));
  }
  const raw = (await res.json()) as Record<string, unknown>;
  return stripProjectRoot(raw) as unknown as SocialPolicyApplyResponse;
}

/** GET /api/social/policy/history. */
export async function loadHistory(): Promise<SocialPolicyHistoryResponse> {
  const res = await hamApiFetch(POLICY_PATHS.history, { method: "GET" });
  if (!res.ok) {
    throw new SocialPolicyApiError(await readError(res));
  }
  const raw = (await res.json()) as Record<string, unknown>;
  return stripProjectRoot(raw) as unknown as SocialPolicyHistoryResponse;
}

/** GET /api/social/policy/audit. */
export async function loadAudit(): Promise<SocialPolicyAuditResponse> {
  const res = await hamApiFetch(POLICY_PATHS.audit, { method: "GET" });
  if (!res.ok) {
    throw new SocialPolicyApiError(await readError(res));
  }
  const raw = (await res.json()) as Record<string, unknown>;
  return stripProjectRoot(raw) as unknown as SocialPolicyAuditResponse;
}

/**
 * Generate a stable client proposal id. Uses crypto.randomUUID where
 * available, falls back to a Math.random shim otherwise.
 */
export function newClientProposalId(): string {
  const g = globalThis as unknown as {
    crypto?: { randomUUID?: () => string };
  };
  if (g.crypto?.randomUUID) {
    return g.crypto.randomUUID();
  }
  // Fallback (RFC4122-ish, dev-only).
  const chars = "0123456789abcdef";
  let s = "";
  for (let i = 0; i < 32; i += 1) {
    s += chars[Math.floor(Math.random() * 16)];
  }
  return `${s.slice(0, 8)}-${s.slice(8, 12)}-${s.slice(12, 16)}-${s.slice(16, 20)}-${s.slice(20)}`;
}
