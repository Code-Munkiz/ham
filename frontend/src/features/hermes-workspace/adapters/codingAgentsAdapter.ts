/**
 * Coding Agents — frontend adapter.
 *
 * The first actionable Coding Agents MVP. Action-first surface that drives
 * the already-shipped Cursor Cloud Agent endpoints behind normie-friendly
 * labels. No new backend shapes; no provider-neutral launch endpoint; no
 * Factory Droid / Claude Code / OpenCode runtime.
 *
 * The adapter exposes only product-truth helpers (readiness, status, launch
 * normalization) to keep the screen thin and the contract testable.
 */

import {
  fetchCursorCredentialsStatus,
  fetchDroidAuditRuns,
  launchCursorAgent,
  launchDroidAudit,
  previewDroidAudit,
  shortenHamApiErrorMessage,
  type DroidAuditLaunchPayload,
  type DroidAuditPreviewPayload,
  type LaunchCursorAgentRequest,
} from "@/lib/ham/api";
import type { ControlPlaneRunPublic, CursorCredentialsStatus } from "@/lib/ham/types";
import { CODING_AGENT_LABELS } from "@/features/hermes-workspace/screens/coding-agents/codingAgentLabels";

/** Normie-friendly readiness for the single launchable provider in MVP. */
export type CodingAgentReadiness = "ready" | "needs_setup";

/** Normie-friendly run status — never expose Cursor enums or HAM lifecycle keys. */
export type CodingAgentRunStatus = "in_progress" | "complete" | "failed";

/** Strings the API may return for a finished Cursor Cloud Agent run. */
const CURSOR_TERMINAL_OK = new Set(["FINISHED", "COMPLETED", "SUCCEEDED", "SUCCESS", "DONE"]);

/** Strings the API may return when a Cursor Cloud Agent run has clearly failed. */
const CURSOR_TERMINAL_FAIL = new Set(["FAILED", "ERROR", "ERRORED", "CANCELLED", "CANCELED"]);

/** Map raw launch errors to normie-friendly copy (no status codes or API paths in primary UI). */
export function userFacingLaunchFailureMessage(raw: string): string {
  const normalized = raw.replace(/\s+/g, " ").trim();
  const t = normalized.toLowerCase();
  if (
    t.includes("clerk_session_required") ||
    t.includes("ham_clerk_require_auth") ||
    t.includes("ham_clerk_enforce_email")
  ) {
    return CODING_AGENT_LABELS.launchSessionAuthorizeHelp;
  }
  if (
    t.includes("rejected this api key") ||
    (t.includes("cursor") && t.includes("rejected") && t.includes("api key"))
  ) {
    return CODING_AGENT_LABELS.launchCursorConnectionHelp;
  }
  const shortened = shortenHamApiErrorMessage(normalized);
  const st = shortened.toLowerCase();
  if (st === "http 401" || /\b401\b/.test(st)) {
    return CODING_AGENT_LABELS.launchCursorConnectionHelp;
  }
  return shortened;
}

/**
 * Map any cursor-side status string to the friendly run status used in
 * primary UI. Anything we don't recognize as terminal is "in progress" so
 * the user is never told "Complete" for an unknown live state.
 */
export function deriveCodingAgentRunStatus(
  rawCursorStatus: string | null | undefined,
): CodingAgentRunStatus {
  const s = (rawCursorStatus ?? "").trim().toUpperCase();
  if (!s) return "in_progress";
  if (CURSOR_TERMINAL_OK.has(s)) return "complete";
  if (CURSOR_TERMINAL_FAIL.has(s)) return "failed";
  return "in_progress";
}

/**
 * Compute readiness for the single launchable provider this MVP exposes.
 *
 * "Ready" only when the server reports `configured: true` AND no Cursor-side
 * error string. Any other shape is "Needs setup" so the user sees the same
 * unambiguous CTA.
 */
export function deriveCursorReadiness(
  status: CursorCredentialsStatus | null,
): CodingAgentReadiness {
  if (!status) return "needs_setup";
  if (!status.configured) return "needs_setup";
  if (status.error) return "needs_setup";
  return "ready";
}

/** Repository URL must look like an https GitHub URL we can hand to Cursor. */
function isLikelyGithubRepoUrl(raw: string): boolean {
  const t = raw.trim();
  if (!t) return false;
  let u: URL;
  try {
    u = new URL(t);
  } catch {
    return false;
  }
  if (u.protocol !== "https:") return false;
  if (u.hostname.toLowerCase() !== "github.com") return false;
  const parts = u.pathname.split("/").filter(Boolean);
  return parts.length >= 2;
}

/** Inputs captured by the New task form (raw, untrimmed where relevant). */
export interface NewCodingTaskFormInput {
  projectId: string;
  repository: string;
  taskPrompt: string;
  ref?: string | null;
  branchName?: string | null;
  autoCreatePr?: boolean;
}

/** Validation outcome — single product-truth source for the form. */
export interface NewCodingTaskValidation {
  ok: boolean;
  errors: {
    projectId?: string;
    repository?: string;
    taskPrompt?: string;
  };
}

export function validateNewCodingTaskForm(
  input: NewCodingTaskFormInput,
  copy: {
    validationProjectRequired: string;
    validationRepositoryRequired: string;
    validationTaskRequired: string;
  },
): NewCodingTaskValidation {
  const errors: NewCodingTaskValidation["errors"] = {};
  if (!input.projectId.trim()) {
    errors.projectId = copy.validationProjectRequired;
  }
  const repo = input.repository.trim();
  if (!repo || !isLikelyGithubRepoUrl(repo)) {
    errors.repository = copy.validationRepositoryRequired;
  }
  if (!input.taskPrompt.trim()) {
    errors.taskPrompt = copy.validationTaskRequired;
  }
  return { ok: Object.keys(errors).length === 0, errors };
}

/**
 * Normalize form inputs into the launch payload accepted by the existing
 * `POST /api/cursor/agents/launch` endpoint. Always pins `mission_handling`
 * to "managed" so the result lands in the existing managed mission
 * tracking surface rather than as a one-off direct launch.
 */
export function buildLaunchRequest(input: NewCodingTaskFormInput): LaunchCursorAgentRequest {
  const ref = input.ref?.trim() ?? "";
  const branch = input.branchName?.trim() ?? "";
  return {
    prompt_text: input.taskPrompt.trim(),
    repository: input.repository.trim(),
    ref: ref ? ref : undefined,
    model: "default",
    auto_create_pr: Boolean(input.autoCreatePr),
    branch_name: branch ? branch : undefined,
    mission_handling: "managed",
    project_id: input.projectId.trim(),
  };
}

/** What the Preview pane displays before the user approves the launch. */
export interface CodingTaskPreview {
  projectId: string;
  repository: string;
  taskPromptPreview: string;
  ref: string | null;
  branchName: string | null;
  autoCreatePr: boolean;
}

const PREVIEW_PROMPT_MAX = 600;

export function buildPreview(input: NewCodingTaskFormInput): CodingTaskPreview {
  const prompt = input.taskPrompt.trim();
  const truncated =
    prompt.length > PREVIEW_PROMPT_MAX ? `${prompt.slice(0, PREVIEW_PROMPT_MAX - 1)}…` : prompt;
  return {
    projectId: input.projectId.trim(),
    repository: input.repository.trim(),
    taskPromptPreview: truncated,
    ref: input.ref?.trim() ? input.ref.trim() : null,
    branchName: input.branchName?.trim() ? input.branchName.trim() : null,
    autoCreatePr: Boolean(input.autoCreatePr),
  };
}

/** Outcome of the launch RPC, normalized for the primary UI. */
export interface LaunchOutcome {
  ok: boolean;
  cursorAgentId: string | null;
  errorMessage: string | null;
}

export async function fetchCursorReadiness(): Promise<{
  readiness: CodingAgentReadiness;
  status: CursorCredentialsStatus | null;
  error: string | null;
}> {
  try {
    const status = await fetchCursorCredentialsStatus();
    return { readiness: deriveCursorReadiness(status), status, error: null };
  } catch (e) {
    return {
      readiness: "needs_setup",
      status: null,
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

export async function launchNewCodingTask(input: NewCodingTaskFormInput): Promise<LaunchOutcome> {
  const body = buildLaunchRequest(input);
  try {
    const resp = await launchCursorAgent(body);
    const id = typeof resp.id === "string" && resp.id.trim() ? resp.id.trim() : null;
    return { ok: true, cursorAgentId: id, errorMessage: null };
  } catch (e) {
    const raw = e instanceof Error ? e.message : String(e);
    return {
      ok: false,
      cursorAgentId: null,
      errorMessage: userFacingLaunchFailureMessage(raw),
    };
  }
}

// ---------------------------------------------------------------------------
// Factory Droid — read-only repository audit lane
// ---------------------------------------------------------------------------
//
// Distinct from Cursor: not a freeform agent. The audit lane only exposes the
// approved read-only workflow on the server. The frontend never sees workflow
// ids, registry revisions, or token gates, so the UI cannot widen the scope.

/** Friendly run status used for both Cursor and Factory Droid runs. */
export type DroidAuditRunStatus = "running" | "complete" | "failed" | "needs_attention";

/** Inputs captured by the audit form (project + freeform "what to look at"). */
export interface NewDroidAuditFormInput {
  projectId: string;
  taskPrompt: string;
}

export interface NewDroidAuditValidation {
  ok: boolean;
  errors: { projectId?: string; taskPrompt?: string };
}

export function validateNewDroidAuditForm(
  input: NewDroidAuditFormInput,
  copy: { validationProjectRequired: string; validationTaskRequired: string },
): NewDroidAuditValidation {
  const errors: NewDroidAuditValidation["errors"] = {};
  if (!input.projectId.trim()) errors.projectId = copy.validationProjectRequired;
  if (!input.taskPrompt.trim()) errors.taskPrompt = copy.validationTaskRequired;
  return { ok: Object.keys(errors).length === 0, errors };
}

const AUDIT_PROMPT_MAX = 600;

export interface DroidAuditPreview {
  projectId: string;
  projectName: string;
  taskPromptPreview: string;
  summaryPreview: string;
  proposalDigest: string;
  baseRevision: string;
}

export function buildDroidAuditPreviewView(payload: DroidAuditPreviewPayload): DroidAuditPreview {
  const prompt = payload.user_prompt.trim();
  const truncated =
    prompt.length > AUDIT_PROMPT_MAX ? `${prompt.slice(0, AUDIT_PROMPT_MAX - 1)}…` : prompt;
  return {
    projectId: payload.project_id,
    projectName: payload.project_name,
    taskPromptPreview: truncated,
    summaryPreview: (payload.summary_preview ?? "").trim(),
    proposalDigest: payload.proposal_digest,
    baseRevision: payload.base_revision,
  };
}

export interface DroidAuditLaunchOutcome {
  ok: boolean;
  hamRunId: string | null;
  errorMessage: string | null;
  payload: DroidAuditLaunchPayload | null;
}

export async function previewDroidAuditFlow(
  input: NewDroidAuditFormInput,
): Promise<{ ok: true; preview: DroidAuditPreview } | { ok: false; errorMessage: string }> {
  try {
    const payload = await previewDroidAudit({
      project_id: input.projectId,
      user_prompt: input.taskPrompt,
    });
    return { ok: true, preview: buildDroidAuditPreviewView(payload) };
  } catch (e) {
    const raw = e instanceof Error ? e.message : String(e);
    return { ok: false, errorMessage: shortenHamApiErrorMessage(raw) };
  }
}

export async function launchDroidAuditFlow(
  input: NewDroidAuditFormInput,
  preview: DroidAuditPreview,
): Promise<DroidAuditLaunchOutcome> {
  try {
    const payload = await launchDroidAudit({
      project_id: input.projectId,
      user_prompt: input.taskPrompt,
      proposal_digest: preview.proposalDigest,
      base_revision: preview.baseRevision,
      confirmed: true,
    });
    return {
      ok: payload.ok,
      hamRunId: payload.ham_run_id,
      errorMessage: payload.ok ? null : (payload.blocking_reason ?? null),
      payload,
    };
  } catch (e) {
    const raw = e instanceof Error ? e.message : String(e);
    return {
      ok: false,
      hamRunId: null,
      errorMessage: shortenHamApiErrorMessage(raw),
      payload: null,
    };
  }
}

/**
 * HAM `ControlPlaneRun` `status` is one of: `running`, `succeeded`, `failed`,
 * `unknown`. Map to friendly labels. Anything we don't recognize is shown as
 * "Needs attention" so the user can investigate, not "Complete".
 */
export function deriveDroidRunStatus(rawStatus: string | null | undefined): DroidAuditRunStatus {
  const s = (rawStatus ?? "").trim().toLowerCase();
  if (!s) return "needs_attention";
  if (s === "running" || s === "in_progress") return "running";
  if (s === "succeeded" || s === "complete" || s === "completed" || s === "ok") return "complete";
  if (s === "failed" || s === "error" || s === "errored" || s === "cancelled") return "failed";
  return "needs_attention";
}

/** Friendly label for a Factory Droid run row in the audits list. */
export function droidRunStatusLabel(status: DroidAuditRunStatus): string {
  switch (status) {
    case "running":
      return CODING_AGENT_LABELS.statusRunning;
    case "complete":
      return CODING_AGENT_LABELS.statusComplete;
    case "failed":
      return CODING_AGENT_LABELS.statusFailed;
    default:
      return CODING_AGENT_LABELS.statusNeedsAttention;
  }
}

export async function fetchDroidAuditRunsForProject(
  projectId: string | null,
): Promise<{ ok: true; runs: ControlPlaneRunPublic[] } | { ok: false; errorMessage: string }> {
  try {
    const runs = await fetchDroidAuditRuns(projectId ?? null, { limit: 25 });
    return { ok: true, runs };
  } catch (e) {
    const raw = e instanceof Error ? e.message : String(e);
    return { ok: false, errorMessage: shortenHamApiErrorMessage(raw) };
  }
}
