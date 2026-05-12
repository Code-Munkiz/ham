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

export const MANAGED_BUILD_SUCCESS_HEADLINE = "Managed workspace snapshot ready";
export const MANAGED_BUILD_FAILURE_HEADLINE = "HAM could not finish the build";

export const MANAGED_BUILD_NO_PR_NOTE =
  "Managed workspace builds never open a pull request and never push to GitHub.";

const PROVIDER_LABEL: Record<CodingConductorProviderKind, string> = {
  no_agent: "Conversational answer",
  factory_droid_audit: "Read-only audit",
  factory_droid_build: "Low-risk pull request",
  cursor_cloud: "Cursor pull request",
  claude_code: "Local single-file edit",
};

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
  if (payload.chosen) return providerLabelForCard(payload.chosen.provider);
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
