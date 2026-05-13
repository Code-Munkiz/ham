/**
 * Pure-string helpers for the chat-side coding plan card.
 *
 * The conductor preview payload is already sanitized server-side, but the
 * card still owns the user-facing copy: provider labels mirror the
 * server's ``_LABEL`` table, output-kind copy reads as a plain English
 * "what you'll get back", and the safety footer is identical regardless of
 * recommendation. These helpers are exported so the React component stays
 * trivially testable without rendering.
 */

import type {
  CodingConductorApprovalKind,
  CodingConductorCandidate,
  CodingConductorOutputKind,
  CodingConductorPreviewPayload,
  CodingConductorProviderKind,
} from "@/lib/ham/api";

export const CODING_PLAN_NO_LAUNCH_FOOTER =
  "No action has been launched yet — this is a recommendation only. Launch approval is coming in a later step.";

export const CODING_PLAN_LAUNCH_DISABLED_TITLE = "Launch approval is coming in a later step.";

export const MANAGED_BUILD_APPROVAL_HEADLINE = "Approve a managed workspace build";

export const MANAGED_BUILD_APPROVAL_BODY =
  "HAM will run a low-risk edit pass and capture a managed workspace snapshot you can review before anything is shared.";

export const MANAGED_BUILD_APPROVAL_CHECKBOX =
  "I approve HAM to create a managed workspace snapshot.";

export const MANAGED_BUILD_PREVIEW_CTA = "Preview this build";
export const MANAGED_BUILD_PREVIEW_BUSY = "Preparing preview…";
export const MANAGED_BUILD_LAUNCH_CTA = "Approve and build";
export const MANAGED_BUILD_LAUNCH_BUSY = "Building snapshot…";

export const MANAGED_BUILD_SUCCESS_HEADLINE = "Saved version created";
export const MANAGED_BUILD_FAILURE_HEADLINE = "HAM could not finish the build";

/** User-facing line for changed-path counts after a managed snapshot build. */
export function managedBuildChangedPathsLine(count: number): string {
  if (!Number.isFinite(count) || count < 0) return "";
  if (count === 0) return "No files changed";
  if (count === 1) return "1 file changed";
  return `${count} files changed`;
}

export const MANAGED_BUILD_PREVIEW_LINK = "Preview";
export const MANAGED_BUILD_VIEW_CHANGES_LINK = "View changes";
export const MANAGED_BUILD_TECHNICAL_DETAILS_SUMMARY = "Technical details";
export const MANAGED_BUILD_KEEP_BUILDING_CTA = "Keep building";

export const MANAGED_BUILD_NO_PR_NOTE =
  "Managed workspace builds never open a pull request and never push to GitHub.";

const PROVIDER_LABEL: Record<CodingConductorProviderKind, string> = {
  no_agent: "Conversational answer",
  factory_droid_audit: "Read-only audit",
  factory_droid_build: "Low-risk pull request",
  cursor_cloud: "Cursor pull request",
  claude_code: "Local single-file edit",
  claude_agent: "Claude Agent (preview)",
};

export type ClaudeAgentReadinessState =
  | "disabled"
  | "not_configured"
  | "sdk_missing"
  | "runner_unavailable"
  | "configured";

export const CLAUDE_AGENT_STATUS_COPY: Record<ClaudeAgentReadinessState, string> = {
  disabled: "Claude Agent is not configured yet.",
  not_configured: "Claude Agent can help with codebase edits once configured.",
  sdk_missing: "Claude Agent SDK is not installed on this server yet.",
  runner_unavailable: "Claude Agent runner is not reachable right now.",
  configured: "HAM will recommend Claude Agent when it is the right tool.",
};

export function claudeAgentStatusCopy(state: ClaudeAgentReadinessState): string {
  return CLAUDE_AGENT_STATUS_COPY[state];
}

// Managed-workspace flavor of ``factory_droid_build``: same provider id,
// different output (managed snapshot, not a PR). Mirrors the server-side
// ``_FACTORY_DROID_BUILD_MANAGED_LABEL`` in ``src/api/coding_conductor.py``
// so chat copy stays consistent across the API and UI.
export const FACTORY_DROID_BUILD_MANAGED_LABEL = "Managed workspace build";

const OUTPUT_KIND_COPY: Record<CodingConductorOutputKind, string> = {
  answer: "An answer in chat",
  report: "A read-only report",
  pull_request: "A pull request you review",
  mission: "A scoped mission you watch",
};

const APPROVAL_KIND_COPY: Record<CodingConductorApprovalKind, string> = {
  none: "No approval needed.",
  confirm: "You'll confirm before HAM launches anything.",
  confirm_and_accept_pr:
    "You'll confirm before HAM opens the pull request, and you can decline it without merging.",
};

const TASK_KIND_DISPLAY: Record<string, string> = {
  explain: "Explain",
  audit: "Audit",
  security_review: "Security review",
  architecture_report: "Architecture report",
  doc_fix: "Documentation fix",
  comments_only: "Comments only",
  format_only: "Formatting only",
  typo_only: "Typo only",
  single_file_edit: "Single-file edit",
  feature: "Feature work",
  fix: "Bug fix",
  refactor: "Refactor",
  multi_file_edit: "Multi-file edit",
  unknown: "Unclassified",
};

export function providerLabelForCard(p: CodingConductorProviderKind): string {
  return PROVIDER_LABEL[p];
}

/**
 * Label for a specific candidate. ``factory_droid_build`` carries two
 * flavors: the github_pr variant (opens a PR) keeps the "Low-risk pull
 * request" label; the managed_workspace variant uses
 * ``Managed workspace build`` because the output is a snapshot, not a PR.
 * Derivation is purely from ``provider`` + ``will_open_pull_request`` to
 * mirror the server-side mapping in ``src/api/coding_conductor.py`` and
 * keep the frontend deterministic regardless of any stale ``label`` field
 * on the candidate.
 */
export function cardLabelForCandidate(
  c: Pick<CodingConductorCandidate, "provider" | "will_open_pull_request">,
): string {
  if (c.provider === "factory_droid_build" && !c.will_open_pull_request) {
    return FACTORY_DROID_BUILD_MANAGED_LABEL;
  }
  return PROVIDER_LABEL[c.provider];
}

export function outputKindCopyForCard(o: CodingConductorOutputKind): string {
  return OUTPUT_KIND_COPY[o];
}

export function approvalCopyForCard(k: CodingConductorApprovalKind): string {
  return APPROVAL_KIND_COPY[k];
}

export function taskKindDisplayForCard(kind: string): string {
  return TASK_KIND_DISPLAY[kind] ?? "Coding task";
}

export function confidenceBadgeForCard(confidence: number): "high" | "medium" | "low" {
  if (confidence >= 0.8) return "high";
  if (confidence >= 0.5) return "medium";
  return "low";
}

export function emptyStateHeadlineForCard(payload: CodingConductorPreviewPayload): string {
  if (payload.chosen) return cardLabelForCandidate(payload.chosen);
  if (payload.task_kind === "unknown") {
    return "HAM isn't sure which provider to use";
  }
  return "No coding agent is available yet";
}

export function isLaunchableInThisPhase(_c: CodingConductorCandidate | null): false {
  // Phase 2B is preview-only. There is no approve/launch button anywhere
  // in the card; this helper is a single source of truth so component
  // tests can lock the invariant without re-deriving the gating logic.
  return false;
}

/**
 * Word-list of strings the card MUST NEVER render in user-facing copy.
 * The card itself doesn't include any of these in its source; this list
 * is consumed by the component's snapshot test to assert no rendered DOM
 * (label, blocker, reason, footer) accidentally surfaces them.
 */
export const FORBIDDEN_CARD_TOKENS = [
  "safe_edit_low",
  "readonly_repo_audit",
  "low_edit",
  "--auto low",
  "ham_droid_exec_token",
  "ham_droid_runner_url",
  "ham_droid_runner_token",
  "anthropic_api_key",
  "cursor_api_key",
  "argv",
  "droid exec",
  "workflow_id",
  "registry_revision",
] as const;
