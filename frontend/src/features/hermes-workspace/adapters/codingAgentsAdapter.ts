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
  launchCursorAgent,
  shortenHamApiErrorMessage,
  type LaunchCursorAgentRequest,
} from "@/lib/ham/api";
import type { CursorCredentialsStatus } from "@/lib/ham/types";
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
