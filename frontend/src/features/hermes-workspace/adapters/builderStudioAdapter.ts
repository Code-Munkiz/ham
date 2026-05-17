/**
 * Builder Studio — frontend adapter.
 *
 * Wraps the workspace-scoped Custom Builder API surface (PR 2) behind a
 * small, normie-safe result shape. Never throws raw network errors at the
 * screen layer; never serializes `byok:<record-id>` into a URL parameter;
 * never returns raw HTTP status codes in user-facing copy.
 */

import { hamApiFetch } from "@/lib/ham/api";

const BASE = "/api/workspaces";

export type BuilderPublic = {
  builder_id: string;
  workspace_id: string;
  name: string;
  description: string;
  intent_tags: string[];
  task_kinds: string[];
  permission_preset: string;
  allowed_paths: string[];
  denied_paths: string[];
  denied_operations: string[];
  review_mode: string;
  deletion_policy: string;
  external_network_policy: string;
  model_source: string;
  model_ref: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  updated_by: string;
  technical_details?: {
    harness: string;
    compiled_permission_summary: string;
    model_ref: string | null;
  };
};

export type BuilderDraft = Omit<
  BuilderPublic,
  "created_at" | "updated_at" | "updated_by" | "technical_details"
>;

export type AdapterError =
  | { kind: "feature_disabled" }
  | { kind: "validation"; message: string }
  | { kind: "auth" }
  | { kind: "not_found" }
  | { kind: "duplicate" }
  | { kind: "unavailable" }
  | { kind: "unknown"; message: string };

const FEATURE_DISABLED_COPY = "Builder Studio is being prepared — check back soon.";
const VALIDATION_GENERIC_COPY = "That permission combination isn't allowed for safety reasons.";
const UNAVAILABLE_COPY = "Couldn't reach Builder Studio right now. Try again in a moment.";
const UNKNOWN_SAVE_COPY = "Couldn't save the builder. Try again in a moment.";
const UNKNOWN_LOAD_COPY = "Couldn't load Builder Studio. Try again in a moment.";

function workspacesPath(workspaceId: string, suffix: string): string {
  return `${BASE}/${encodeURIComponent(workspaceId)}/custom-builders${suffix}`;
}

function builderPath(workspaceId: string, builderId: string, suffix = ""): string {
  return `${BASE}/${encodeURIComponent(workspaceId)}/custom-builders/${encodeURIComponent(
    builderId,
  )}${suffix}`;
}

async function safeJson(res: Response): Promise<unknown> {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

function looksLikeFeatureDisabled(body: unknown): boolean {
  if (!body || typeof body !== "object") return false;
  const candidate =
    (body as Record<string, unknown>).detail ?? (body as Record<string, unknown>).code;
  if (typeof candidate !== "string") return false;
  return candidate.toUpperCase().includes("CUSTOM_BUILDER_FEATURE_DISABLED");
}

async function mapErrorResponse(res: Response, fallback: string): Promise<AdapterError> {
  if (res.status === 401 || res.status === 403) return { kind: "auth" };
  if (res.status === 404) return { kind: "not_found" };
  if (res.status === 409) return { kind: "duplicate" };
  if (res.status === 422) {
    return { kind: "validation", message: VALIDATION_GENERIC_COPY };
  }
  if (res.status === 503) {
    const body = await safeJson(res);
    if (looksLikeFeatureDisabled(body)) return { kind: "feature_disabled" };
    return { kind: "unavailable" };
  }
  return { kind: "unknown", message: fallback };
}

function networkError(fallback: string): AdapterError {
  return { kind: "unknown", message: fallback };
}

interface ListResponse {
  builders?: BuilderPublic[];
}

interface BuilderResponse {
  builder?: BuilderPublic;
}

interface PreviewResponse {
  summary?: string;
}

interface TestPlanResponse {
  candidates?: unknown[];
}

export const builderStudioAdapter = {
  description: "HAM /api/workspaces/{wid}/custom-builders — CRUD + preview + test-plan",

  async list(workspaceId: string): Promise<{ builders: BuilderPublic[]; error?: AdapterError }> {
    try {
      const res = await hamApiFetch(workspacesPath(workspaceId, ""), {
        credentials: "include",
      });
      if (!res.ok) {
        return { builders: [], error: await mapErrorResponse(res, UNKNOWN_LOAD_COPY) };
      }
      const body = (await safeJson(res)) as ListResponse | null;
      const builders = Array.isArray(body?.builders) ? (body?.builders as BuilderPublic[]) : [];
      return { builders };
    } catch {
      return { builders: [], error: networkError(UNAVAILABLE_COPY) };
    }
  },

  async get(
    workspaceId: string,
    builderId: string,
  ): Promise<{ builder: BuilderPublic | null; error?: AdapterError }> {
    try {
      const res = await hamApiFetch(builderPath(workspaceId, builderId), {
        credentials: "include",
      });
      if (!res.ok) {
        return { builder: null, error: await mapErrorResponse(res, UNKNOWN_LOAD_COPY) };
      }
      const body = (await safeJson(res)) as BuilderResponse | null;
      return { builder: body?.builder ?? null };
    } catch {
      return { builder: null, error: networkError(UNAVAILABLE_COPY) };
    }
  },

  async create(
    workspaceId: string,
    draft: BuilderDraft,
  ): Promise<{ builder: BuilderPublic | null; error?: AdapterError }> {
    try {
      const res = await hamApiFetch(workspacesPath(workspaceId, ""), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      if (!res.ok) {
        return { builder: null, error: await mapErrorResponse(res, UNKNOWN_SAVE_COPY) };
      }
      const body = (await safeJson(res)) as BuilderResponse | null;
      return { builder: body?.builder ?? null };
    } catch {
      return { builder: null, error: networkError(UNAVAILABLE_COPY) };
    }
  },

  async update(
    workspaceId: string,
    builderId: string,
    patch: Partial<BuilderDraft>,
  ): Promise<{ builder: BuilderPublic | null; error?: AdapterError }> {
    try {
      const res = await hamApiFetch(builderPath(workspaceId, builderId), {
        method: "PATCH",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
      });
      if (!res.ok) {
        return { builder: null, error: await mapErrorResponse(res, UNKNOWN_SAVE_COPY) };
      }
      const body = (await safeJson(res)) as BuilderResponse | null;
      return { builder: body?.builder ?? null };
    } catch {
      return { builder: null, error: networkError(UNAVAILABLE_COPY) };
    }
  },

  async softDelete(
    workspaceId: string,
    builderId: string,
  ): Promise<{ ok: boolean; error?: AdapterError }> {
    try {
      const res = await hamApiFetch(builderPath(workspaceId, builderId), {
        method: "DELETE",
        credentials: "include",
      });
      if (res.ok || res.status === 204) {
        return { ok: true };
      }
      return { ok: false, error: await mapErrorResponse(res, UNKNOWN_SAVE_COPY) };
    } catch {
      return { ok: false, error: networkError(UNAVAILABLE_COPY) };
    }
  },

  async preview(
    workspaceId: string,
    draft: BuilderDraft,
  ): Promise<{ summary: string | null; error?: AdapterError }> {
    try {
      const res = await hamApiFetch(workspacesPath(workspaceId, "/preview"), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(draft),
      });
      if (!res.ok) {
        return { summary: null, error: await mapErrorResponse(res, UNKNOWN_SAVE_COPY) };
      }
      const body = (await safeJson(res)) as PreviewResponse | null;
      const summary = typeof body?.summary === "string" ? body.summary : null;
      return { summary };
    } catch {
      return { summary: null, error: networkError(UNAVAILABLE_COPY) };
    }
  },

  async testPlan(
    workspaceId: string,
    builderId: string,
    prompt: string,
  ): Promise<{ candidates: unknown[]; error?: AdapterError }> {
    try {
      const res = await hamApiFetch(builderPath(workspaceId, builderId, "/test-plan"), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_prompt: prompt }),
      });
      if (!res.ok) {
        return { candidates: [], error: await mapErrorResponse(res, UNKNOWN_LOAD_COPY) };
      }
      const body = (await safeJson(res)) as TestPlanResponse | null;
      const candidates = Array.isArray(body?.candidates) ? (body?.candidates as unknown[]) : [];
      return { candidates };
    } catch {
      return { candidates: [], error: networkError(UNAVAILABLE_COPY) };
    }
  },
} as const;

export function adapterErrorMessage(error: AdapterError): string {
  switch (error.kind) {
    case "feature_disabled":
      return FEATURE_DISABLED_COPY;
    case "validation":
      return error.message;
    case "auth":
      return "Please sign in again to manage Builder Studio.";
    case "not_found":
      return "That builder isn't available anymore.";
    case "duplicate":
      return "A builder with that id already exists. Pick a different id.";
    case "unavailable":
      return UNAVAILABLE_COPY;
    default:
      return error.message;
  }
}
