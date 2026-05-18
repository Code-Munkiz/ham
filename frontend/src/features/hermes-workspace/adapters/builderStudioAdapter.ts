/**
 * Builder Studio — frontend adapter.
 *
 * Wraps the workspace-scoped Custom Builder API surface (PR 2) behind a
 * small, normie-safe result shape. Never throws raw network errors at the
 * screen layer; never serializes `byok:<record-id>` into a URL parameter;
 * never returns raw HTTP status codes in user-facing copy.
 */

import { hamApiFetch } from "@/lib/ham/api";
import {
  MODEL_SOURCE_LABELS,
  PERMISSION_PRESET_LABELS,
  REVIEW_MODE_LABELS,
  type ModelSource,
  type PermissionPreset,
  type ReviewMode,
} from "@/features/hermes-workspace/screens/builder-studio/builderStudioLabels";

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

/** Step key for surfacing validation errors in Create Builder wizard (no `preview` — errors occur before that step). */
export type BuilderWizardValidationStep = "identity" | "skill" | "safety" | "model";

export type AdapterError =
  | { kind: "feature_disabled" }
  | {
      kind: "validation";
      message: string;
      /** When set, the wizard should highlight this step, not Step 4 (model). */
      wizardStep?: BuilderWizardValidationStep;
    }
  | { kind: "auth" }
  | { kind: "not_found" }
  /** List endpoint missing or workspace has no list resource — not a single-builder delete state. */
  | { kind: "builders_list_not_found" }
  | { kind: "duplicate" }
  | { kind: "unavailable" }
  | { kind: "unknown"; message: string };

const FEATURE_DISABLED_COPY = "Builder Studio is being prepared — check back soon.";
const VALIDATION_PERMISSION_COPY =
  "This builder's permissions are too broad for the selected safety mode. Choose a safer permission preset to continue.";
const VALIDATION_MODEL_COPY =
  "That model choice needs a small fix. Use a workspace model id or a BYOK reference like byok:your-record — not a raw secret or API key.";
const VALIDATION_CUSTOM_PRESET_COPY =
  "Advanced (custom) needs path or rule settings this quick wizard doesn't collect yet. Pick a standard safety preset to continue, or edit the builder later where advanced rules are supported.";
const VALIDATION_GENERIC_COPY =
  "We couldn't validate this builder. Use the button below to go back to the right step, adjust your choices, and try Preview again.";
const VALIDATION_REQUEST_SHAPE_COPY =
  "Something in this builder request didn't match the server. Go back one step, then try Preview again.";

const UNAVAILABLE_COPY = "Couldn't reach Builder Studio right now. Try again in a moment.";
const UNKNOWN_SAVE_COPY = "Couldn't save the builder. Try again in a moment.";
const UNKNOWN_LOAD_COPY = "Couldn't load custom builders. Try again in a moment.";
const LIST_NOT_FOUND_COPY =
  "We couldn't load your custom builders for this workspace. Try refreshing. If this keeps happening, Builder Studio may not be available here yet.";

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

/** POST body keys accepted by Custom Builder API models (no `workspace_id` — path-only). */
function draftToApiJson(draft: BuilderDraft): Record<string, unknown> {
  return {
    builder_id: draft.builder_id,
    name: draft.name,
    description: draft.description,
    intent_tags: draft.intent_tags,
    task_kinds: draft.task_kinds,
    model_source: draft.model_source,
    model_ref: draft.model_ref,
    permission_preset: draft.permission_preset,
    allowed_paths: draft.allowed_paths,
    denied_paths: draft.denied_paths,
    denied_operations: draft.denied_operations,
    review_mode: draft.review_mode,
    deletion_policy: draft.deletion_policy,
    external_network_policy: draft.external_network_policy,
    enabled: draft.enabled,
  };
}

function patchToApiJson(patch: Partial<BuilderDraft>): Record<string, unknown> {
  const entries = Object.entries(patch).filter(([, v]) => v !== undefined);
  return Object.fromEntries(entries.filter(([k]) => k !== "workspace_id"));
}

function extract422DetailText(body: unknown): string {
  if (!body || typeof body !== "object") return "";
  const rec = body as Record<string, unknown>;
  const detail = rec.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => {
        if (
          d &&
          typeof d === "object" &&
          "msg" in d &&
          typeof (d as { msg: unknown }).msg === "string"
        ) {
          return (d as { msg: string }).msg;
        }
        return "";
      })
      .filter(Boolean);
    return parts.join("; ");
  }
  if (detail && typeof detail === "object") {
    const err = (detail as Record<string, unknown>).error;
    if (
      err &&
      typeof err === "object" &&
      typeof (err as { message?: unknown }).message === "string"
    ) {
      return String((err as { message: string }).message);
    }
  }
  return "";
}

function classifyWizardValidationStep(raw: string): BuilderWizardValidationStep | undefined {
  const t = raw.toLowerCase();
  if (
    t.includes("model_ref") ||
    t.includes("model_source") ||
    t.includes("raw secret") ||
    (t.includes("byok") && t.includes("instead"))
  ) {
    return "model";
  }
  if (
    t.includes("builder_id") ||
    t.includes("intent_tag") ||
    t.includes("intent tags") ||
    t.includes("intent_tags")
  ) {
    return "identity";
  }
  if (t.includes("task_kind") || t.includes("task kinds") || t.includes("task_kinds")) {
    return "skill";
  }
  if (
    t.includes("permission") ||
    t.includes("preset") ||
    t.includes("allowed_paths") ||
    t.includes("denied_paths") ||
    t.includes("denied_operations") ||
    t.includes("review_mode") ||
    t.includes("deletion") ||
    t.includes("network") ||
    t.includes("harness") ||
    t.includes("custom preset")
  ) {
    return "safety";
  }
  return undefined;
}

function userFacingValidationFromRaw(
  raw: string,
  stepHint?: BuilderWizardValidationStep,
): { message: string; wizardStep?: BuilderWizardValidationStep } {
  const t = raw.toLowerCase();
  const resolvedStep = stepHint ?? classifyWizardValidationStep(raw);

  if (t.includes("extra inputs") || t.includes("extra_forbidden") || t.includes("workspace_id")) {
    return { message: VALIDATION_REQUEST_SHAPE_COPY, wizardStep: undefined };
  }
  if (
    t.includes("custom preset requires") ||
    (t.includes("allowed_paths") && t.includes("custom")) ||
    (t.includes("denied_paths") && t.includes("custom"))
  ) {
    return { message: VALIDATION_CUSTOM_PRESET_COPY, wizardStep: "safety" };
  }
  if (t.includes("model_ref") || t.includes("raw secret")) {
    return { message: VALIDATION_MODEL_COPY, wizardStep: "model" };
  }
  if (
    t.includes("permission") ||
    t.includes("harness") ||
    t.includes("preset") ||
    t.includes("review_mode") ||
    t.includes("deletion") ||
    t.includes("external_network") ||
    t.includes("network policy")
  ) {
    return {
      message: VALIDATION_PERMISSION_COPY,
      wizardStep: resolvedStep ?? "safety",
    };
  }
  if (resolvedStep === "model") {
    return { message: VALIDATION_MODEL_COPY, wizardStep: "model" };
  }
  if (resolvedStep === "safety") {
    return { message: VALIDATION_PERMISSION_COPY, wizardStep: "safety" };
  }
  if (raw.trim().length > 0 && raw.length < 200 && !/[{}[\]]/.test(raw)) {
    return { message: raw.trim(), wizardStep: resolvedStep };
  }
  return {
    message: VALIDATION_GENERIC_COPY,
    wizardStep: resolvedStep,
  };
}

async function validationErrorFrom422(res: Response): Promise<AdapterError> {
  const body = await safeJson(res);
  const raw = extract422DetailText(body);
  const step = classifyWizardValidationStep(raw);
  const { message, wizardStep } = userFacingValidationFromRaw(raw, step);
  return { kind: "validation", message, wizardStep };
}

function formatPreviewSummaryFromApi(summary: unknown): string {
  if (typeof summary === "string" && summary.trim()) {
    return summary.trim();
  }
  if (!summary || typeof summary !== "object") {
    return "Builder is ready to save.";
  }
  const s = summary as Record<string, unknown>;
  const name = typeof s.name === "string" ? s.name.trim() : "";
  const presetRaw = typeof s.permission_preset === "string" ? s.permission_preset : "";
  const reviewRaw = typeof s.review_mode === "string" ? s.review_mode : "";
  const modelRaw = typeof s.model_source === "string" ? s.model_source : "";
  const presetLabel =
    presetRaw in PERMISSION_PRESET_LABELS
      ? PERMISSION_PRESET_LABELS[presetRaw as PermissionPreset]
      : presetRaw || "—";
  const reviewLabel =
    reviewRaw in REVIEW_MODE_LABELS
      ? REVIEW_MODE_LABELS[reviewRaw as ReviewMode]
      : reviewRaw || "—";
  const modelLabel =
    modelRaw in MODEL_SOURCE_LABELS
      ? MODEL_SOURCE_LABELS[modelRaw as ModelSource]
      : modelRaw || "—";
  const head = name ? `“${name}” looks good to save.` : "This builder looks good to save.";
  return `${head} Safety: ${presetLabel}. Review: ${reviewLabel}. Model: ${modelLabel}.`;
}

function previewErrorsToAdapterError(errors: unknown[]): AdapterError {
  const lines = errors
    .map((e) => (typeof e === "string" ? e : JSON.stringify(e)))
    .filter((s) => s.trim().length > 0);
  const raw = lines.join("; ");
  const step = classifyWizardValidationStep(raw);
  const { message, wizardStep } = userFacingValidationFromRaw(raw, step);
  return { kind: "validation", message, wizardStep };
}

async function mapErrorResponse(res: Response, fallback: string): Promise<AdapterError> {
  if (res.status === 401 || res.status === 403) return { kind: "auth" };
  if (res.status === 404) return { kind: "not_found" };
  if (res.status === 409) return { kind: "duplicate" };
  if (res.status === 422) {
    return validationErrorFrom422(res);
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
        if (res.status === 404) {
          return { builders: [], error: { kind: "builders_list_not_found" } };
        }
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
        body: JSON.stringify(draftToApiJson(draft)),
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
        body: JSON.stringify(patchToApiJson(patch)),
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
        body: JSON.stringify(draftToApiJson(draft)),
      });
      if (!res.ok) {
        return { summary: null, error: await mapErrorResponse(res, UNKNOWN_SAVE_COPY) };
      }
      const body = (await safeJson(res)) as {
        valid?: boolean;
        summary?: unknown;
        errors?: unknown;
      } | null;
      if (body?.valid === false) {
        const errs = Array.isArray(body.errors) ? body.errors : [];
        if (errs.length === 0) {
          return {
            summary: null,
            error: { kind: "validation", message: VALIDATION_GENERIC_COPY },
          };
        }
        return { summary: null, error: previewErrorsToAdapterError(errs as unknown[]) };
      }
      const summary = formatPreviewSummaryFromApi(body?.summary);
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
      return "That builder may have been deleted or is no longer available.";
    case "builders_list_not_found":
      return LIST_NOT_FOUND_COPY;
    case "duplicate":
      return "A builder with that id already exists. Pick a different id.";
    case "unavailable":
      return UNAVAILABLE_COPY;
    default:
      return error.message;
  }
}
