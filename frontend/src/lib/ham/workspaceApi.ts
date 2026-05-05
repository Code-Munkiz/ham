/**
 * Phase 1c: typed client for the multi-user workspace primitive
 * (`/api/me`, `/api/workspaces`). Backend contract = PR #150 + #152.
 *
 * Reuses the existing `apiUrl` + `hamApiFetch` plumbing in `api.ts` so the
 * Clerk JWT (when present) and `VITE_HAM_API_BASE` overrides are honored
 * uniformly. No new auth surface introduced here.
 */
import { apiUrl, hamApiFetch, hamApiErrorDetailMessage } from "./api";

// ---------------------------------------------------------------------------
// Wire types — match backend response shapes exactly.
// ---------------------------------------------------------------------------

export type HamWorkspaceRole = "owner" | "admin" | "member" | "viewer";
export type HamWorkspaceStatus = "active" | "archived";
export type HamAuthMode = "clerk" | "local_dev_bypass";

export interface HamWorkspaceSummary {
  workspace_id: string;
  org_id: string | null;
  name: string;
  slug: string;
  description: string;
  status: HamWorkspaceStatus;
  role: HamWorkspaceRole;
  perms: string[];
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface HamMeUser {
  user_id: string;
  email: string | null;
  display_name: string | null;
  photo_url: string | null;
  primary_org_id: string | null;
}

export interface HamMeOrg {
  org_id: string;
  name: string;
  clerk_slug: string;
  org_role: string;
}

export interface HamMeResponse {
  user: HamMeUser;
  orgs: HamMeOrg[];
  workspaces: HamWorkspaceSummary[];
  default_workspace_id: string | null;
  auth_mode: HamAuthMode;
}

export interface HamWorkspaceContext {
  role: HamWorkspaceRole;
  perms: string[];
  org_role: string | null;
}

export interface HamListWorkspacesResponse {
  workspaces: HamWorkspaceSummary[];
  default_workspace_id: string | null;
}

export interface HamWorkspaceResponse {
  workspace: HamWorkspaceSummary;
  context: HamWorkspaceContext;
  audit_id?: string;
}

export interface HamCreateWorkspaceBody {
  name: string;
  slug?: string;
  description?: string;
  org_id?: string | null;
}

export interface HamPatchWorkspaceBody {
  name?: string;
  description?: string;
}

// ---------------------------------------------------------------------------
// Error shape
// ---------------------------------------------------------------------------

/** Stable error class for callers — always carries an HTTP status + the
 * structured backend error code when one is present.
 */
export class HamWorkspaceApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly httpDetail: unknown;

  constructor(status: number, code: string | null, message: string, detail?: unknown) {
    super(message);
    this.name = "HamWorkspaceApiError";
    this.status = status;
    this.code = code;
    this.httpDetail = detail;
  }
}

async function readError(res: Response, fallback: string): Promise<HamWorkspaceApiError> {
  let detail: unknown = undefined;
  let code: string | null = null;
  let message: string | null = null;
  try {
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      const body = (await res.clone().json()) as {
        detail?: { error?: { code?: string; message?: string } };
      };
      detail = body?.detail;
      code = body?.detail?.error?.code ?? null;
      message = body?.detail?.error?.message ?? null;
    }
  } catch {
    /* swallow */
  }
  if (!message) {
    message = (await hamApiErrorDetailMessage(res)) || fallback;
  }
  return new HamWorkspaceApiError(res.status, code, message, detail);
}

// ---------------------------------------------------------------------------
// Methods
// ---------------------------------------------------------------------------

/** `GET /api/me` — caller identity + accessible workspace summaries. */
export async function getMe(): Promise<HamMeResponse> {
  const res = await hamApiFetch("/api/me");
  if (!res.ok) {
    throw await readError(res, `GET /api/me failed (${res.status})`);
  }
  return (await res.json()) as HamMeResponse;
}

/** `GET /api/workspaces` — list workspaces visible to caller. */
export async function listWorkspaces(opts?: {
  org_id?: string | null;
  include_archived?: boolean;
}): Promise<HamListWorkspacesResponse> {
  const params = new URLSearchParams();
  if (opts?.org_id) params.set("org_id", opts.org_id);
  if (opts?.include_archived) params.set("include_archived", "true");
  const qs = params.toString();
  const res = await hamApiFetch(`/api/workspaces${qs ? `?${qs}` : ""}`);
  if (!res.ok) {
    throw await readError(res, `GET /api/workspaces failed (${res.status})`);
  }
  return (await res.json()) as HamListWorkspacesResponse;
}

/** `POST /api/workspaces` — create a workspace (personal or org-scoped). */
export async function createWorkspace(body: HamCreateWorkspaceBody): Promise<HamWorkspaceResponse> {
  const res = await hamApiFetch("/api/workspaces", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw await readError(res, `POST /api/workspaces failed (${res.status})`);
  }
  return (await res.json()) as HamWorkspaceResponse;
}

/** `GET /api/workspaces/{workspace_id}`. */
export async function getWorkspace(workspaceId: string): Promise<HamWorkspaceResponse> {
  const res = await hamApiFetch(`/api/workspaces/${encodeURIComponent(workspaceId)}`);
  if (!res.ok) {
    throw await readError(res, `GET workspace failed (${res.status})`);
  }
  return (await res.json()) as HamWorkspaceResponse;
}

/** `PATCH /api/workspaces/{workspace_id}` — update name and/or description. */
export async function patchWorkspace(
  workspaceId: string,
  patch: HamPatchWorkspaceBody,
): Promise<HamWorkspaceResponse> {
  const res = await hamApiFetch(`/api/workspaces/${encodeURIComponent(workspaceId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) {
    throw await readError(res, `PATCH workspace failed (${res.status})`);
  }
  return (await res.json()) as HamWorkspaceResponse;
}

// Re-export the API origin helper so callers (tests, debug pages) don't need
// to deep-import `api.ts` themselves.
export { apiUrl };
