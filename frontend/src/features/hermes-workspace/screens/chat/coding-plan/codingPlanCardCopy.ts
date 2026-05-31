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
  "Nothing has started yet. Use the approval controls below when you're ready.";

export const CODING_PLAN_LAUNCH_DISABLED_TITLE =
  "Approval is required before HAM starts this work.";

export const CODING_PLAN_SECTION_LABEL = "Next step";

/**
 * Minimal chat pointer shown once the managed build approval experience has
 * been relocated to the workbench right pane. Chat no longer hosts the
 * approval controls or launch state — it only directs the user to the panel.
 */
export const CODING_PLAN_RIGHT_PANE_POINTER =
  "Preview is ready on the right — review and approve the build in the workbench.";

/**
 * Plain-language chat lifecycle pointers. Chat stays conversation-first (no
 * approval controls, no dashboards), but mirrors the right-pane build lifecycle
 * so the user can tell whether HAM is building, done, or needs attention.
 * Never references build-kit internals, providers, or routing.
 */
export const CODING_PLAN_BUILDING_POINTER =
  "HAM is building your app now — track progress in the workbench on the right.";

export const CODING_PLAN_COMPLETED_POINTER =
  "Your build is ready — open it from the workbench on the right.";

export const CODING_PLAN_ATTENTION_POINTER =
  "This build needs your attention — check the workbench on the right.";

/**
 * Lifecycle phase strings emitted by the relocated managed build panel. Kept as
 * a local string union (not a type import) so the copy module stays free of
 * component coupling while the selector below stays exhaustive.
 */
export type CodingPlanBuildPhase =
  | "idle"
  | "previewing"
  | "previewed"
  | "launching"
  | "running"
  | "succeeded"
  | "failed";

/** Pick the concise chat pointer that mirrors the right-pane build lifecycle. */
export function codingPlanPointerForPhase(phase: CodingPlanBuildPhase | null | undefined): string {
  switch (phase) {
    case "launching":
    case "running":
      return CODING_PLAN_BUILDING_POINTER;
    case "succeeded":
      return CODING_PLAN_COMPLETED_POINTER;
    case "failed":
      return CODING_PLAN_ATTENTION_POINTER;
    case "idle":
    case "previewing":
    case "previewed":
    default:
      return CODING_PLAN_RIGHT_PANE_POINTER;
  }
}

/**
 * Build-generation lifecycle phase for the **Builder Happy Path scaffold** flow
 * (a "make me an app/dashboard" prompt that streams a reply and scaffolds a
 * preview). This is distinct from the managed Droid/OpenCode approval lane: it
 * has no approval/launch controls. Chat shows a concise, persistent pointer so
 * the user always knows HAM is working, done, or recovering — even if the chat
 * stream is interrupted and the transcript is restored from the server.
 */
export type BuildGenerationPhase = "idle" | "preparing" | "generating" | "interrupted" | "ready";

export const BUILD_GENERATION_PREPARING_POINTER = "I'm preparing your preview…";
export const BUILD_GENERATION_GENERATING_POINTER =
  "I'm generating the first version — it'll appear on the right.";
export const BUILD_GENERATION_READY_POINTER = "Preview is ready on the right.";
export const BUILD_GENERATION_INTERRUPTED_POINTER = "I'm still checking the latest build status…";

/**
 * Calm toast shown when the chat stream drops while a builder generation is
 * still active. The scaffold keeps running server-side and the preview appears
 * on the right, so this avoids the alarming "connection interrupted / reply
 * failed" framing used for ordinary chat turns.
 */
export const BUILD_GENERATION_INTERRUPTED_TOAST =
  "HAM is still building your app — I'm checking the latest status on the right.";

/** Concise persistent chat pointer mirroring the build generation lifecycle. */
export function buildGenerationChatPointer(phase: BuildGenerationPhase): string | null {
  switch (phase) {
    case "preparing":
      return BUILD_GENERATION_PREPARING_POINTER;
    case "generating":
      return BUILD_GENERATION_GENERATING_POINTER;
    case "ready":
      return BUILD_GENERATION_READY_POINTER;
    case "interrupted":
      return BUILD_GENERATION_INTERRUPTED_POINTER;
    case "idle":
    default:
      return null;
  }
}

export const MANAGED_BUILD_APPROVAL_HEADLINE = "Approve build";

export const MANAGED_BUILD_APPROVAL_BODY =
  "HAM will apply a cautious edit sweep and stash a labeled workspace version you can review before sharing anything externally.";

export const MANAGED_BUILD_APPROVAL_CHECKBOX =
  "I approve HAM to save a gated workspace snapshot for this Builder run.";

export const MANAGED_BUILD_PREVIEW_CTA = "Prepare build";
export const MANAGED_BUILD_PREVIEW_BUSY = "Preparing build…";
export const MANAGED_BUILD_LAUNCH_CTA = "Approve build";
export const MANAGED_BUILD_LAUNCH_BUSY = "Building snapshot…";

export const MANAGED_BUILD_SUCCESS_HEADLINE = "Saved version created";
export const MANAGED_BUILD_FAILURE_HEADLINE = "Build did not complete. No version was saved.";

/** User-facing line for changed-path counts after a managed snapshot build. */
export function managedBuildChangedPathsLine(count: number): string {
  if (!Number.isFinite(count) || count < 0) return "";
  if (count === 0) return "No files changed";
  if (count === 1) return "1 file changed";
  return `${count} files changed`;
}

export const MANAGED_BUILD_PREVIEW_LINK = "Open app preview";
export const MANAGED_BUILD_VIEW_CHANGES_LINK = "View changes";
export const MANAGED_BUILD_TECHNICAL_DETAILS_SUMMARY = "Technical details";
export const MANAGED_BUILD_KEEP_BUILDING_CTA = "Keep building";

export const MANAGED_BUILD_NO_PR_NOTE =
  "HAM workspace snapshots never publish to GitHub and never raise pull requests.";

export const OPENCODE_BUILD_APPROVAL_HEADLINE = "Review OpenCode build";

export const OPENCODE_BUILD_APPROVAL_BODY =
  "HAM will run OpenCode against your synced workspace sources and tuck the result behind a gated snapshot you preview first.";

export const OPENCODE_BUILD_APPROVAL_CHECKBOX =
  "I approve letting OpenCode synthesize changes into a gated workspace snapshot.";

export const OPENCODE_BUILD_PREVIEW_CTA = "Prepare build";
export const OPENCODE_BUILD_PREVIEW_BUSY = "Preparing build…";
export const OPENCODE_BUILD_LAUNCH_CTA = "Approve build";
export const OPENCODE_BUILD_LAUNCH_BUSY = "Building…";

export const OPENCODE_BUILD_SUCCESS_HEADLINE = "Saved version created";
export const OPENCODE_BUILD_FAILURE_HEADLINE = "Build did not complete. No version was saved.";

export const OPENCODE_BUILD_NO_PR_NOTE =
  "OpenCode-backed workspace builds stay sandboxed and won't open a GitHub pull request.";
export const OPENCODE_BUILD_PREVIEW_LINK = "Open app preview";
export const OPENCODE_BUILD_VIEW_CHANGES_LINK = "View changes";
export const OPENCODE_BUILD_TECHNICAL_DETAILS_SUMMARY = "Details";
export const OPENCODE_BUILD_KEEP_BUILDING_CTA = "Keep building";

export const OPENCODE_BUILD_RUNNING_HEADLINE = "HAM is building with OpenCode";
export const OPENCODE_BUILD_RUNNING_NOTE =
  "This usually takes 1–2 minutes. You can navigate away — the build continues in the background.";

const OPENCODE_STATUS_REASON_MESSAGES: Record<string, string> = {
  "opencode:timeout": "The build timed out before finishing. No changes were saved.",
  "opencode:session_no_completion":
    "OpenCode worked on the task but did not produce a complete result.",
  "opencode:runner_error": "An internal error stopped the build. No changes were made.",
  "opencode:permission_denied": "HAM blocked the build — a required permission was not granted.",
  "opencode:output_requires_review": "The output needs review before it can be saved.",
  "opencode:workspace_setup_failed": "The workspace could not be prepared for this build.",
  "opencode:serve_unavailable": "The OpenCode service was not available. Try again in a moment.",
  "opencode:provider_not_configured": "OpenCode is not fully configured for this project.",
};

export function normieFailMessageForOpencode(reason: string | null | undefined): string | null {
  if (!reason) return null;
  return OPENCODE_STATUS_REASON_MESSAGES[reason] ?? null;
}

export function opencodeBuildChangedPathsLine(count: number): string {
  if (!Number.isFinite(count) || count < 0) return "";
  if (count === 0) return "No files changed";
  if (count === 1) return "1 file changed";
  return `${count} files changed`;
}

export const OPENCODE_PREFERRED_CTA = "Try with OpenCode";
export const OPENCODE_PREFERRED_HINT =
  "Use a sandboxed workspace build instead of opening a GitHub pull request.";
export const OPENCODE_PREFERRED_LOADING = "Switching to OpenCode…";

export function shouldShowOpenCodeAffordance(payload: CodingConductorPreviewPayload): boolean {
  if (payload.chosen?.provider === "opencode_cli") return false;
  const opencode = payload.candidates.find((c) => c.provider === "opencode_cli");
  if (!opencode) return false;
  if (!opencode.available) return false;
  if (opencode.blockers.length > 0) return false;
  return true;
}

/**
 * Product-branded builder labels shown in the main card headline.
 * Approved product names only: Claude, OpenCode, Factory Droid, Cursor.
 * Never expose raw provider ids or technical routing vocabulary here.
 */
const USER_FACING_BUILDER_LABEL: Record<CodingConductorProviderKind, string> = {
  no_agent: "Chat guidance",
  factory_droid_audit: "Factory Droid audit",
  factory_droid_build: "Factory Droid",
  cursor_cloud: "Cursor",
  claude_code: "Claude",
  claude_agent: "Claude",
  opencode_cli: "OpenCode",
};

const PROVIDER_LABEL: Record<CodingConductorProviderKind, string> = {
  no_agent: "Chat guidance",
  factory_droid_audit: "Factory Droid audit",
  factory_droid_build: "Factory Droid build",
  cursor_cloud: "Cursor",
  claude_code: "Claude",
  claude_agent: "Claude (preview)",
  opencode_cli: "OpenCode",
};

export type ClaudeAgentReadinessState =
  | "disabled"
  | "not_configured"
  | "sdk_missing"
  | "runner_unavailable"
  | "configured";

export const CLAUDE_AGENT_STATUS_COPY: Record<ClaudeAgentReadinessState, string> = {
  disabled: "Claude is not configured yet.",
  not_configured: "Claude can help with codebase edits once configured.",
  sdk_missing: "Claude is not installed on this server yet.",
  runner_unavailable: "Claude is not reachable right now.",
  configured: "HAM will recommend Claude when it is the right tool.",
};

export function claudeAgentStatusCopy(state: ClaudeAgentReadinessState): string {
  return CLAUDE_AGENT_STATUS_COPY[state];
}

// Managed-workspace flavor of ``factory_droid_build``: same provider id,
// different output (managed snapshot, not a PR). Mirrors the server-side
// ``_FACTORY_DROID_BUILD_MANAGED_LABEL`` in ``src/api/coding_conductor.py``
// so chat copy stays consistent across the API and UI.
export const FACTORY_DROID_BUILD_MANAGED_LABEL = "Factory Droid build";

const OUTPUT_KIND_COPY: Record<CodingConductorOutputKind, string> = {
  answer: "An answer in chat",
  report: "A read-only report",
  pull_request: "A pull request you review",
  mission: "A scoped mission you watch",
};

const APPROVAL_KIND_COPY: Record<CodingConductorApprovalKind, string> = {
  none: "No approval required.",
  confirm: "You'll review before anything is saved.",
  confirm_and_accept_pr: "You'll review the pull request before it merges.",
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
 * Label for a specific candidate. ``factory_droid_build`` carries two flavors:
 * the GitHub-oriented lane keeps PR labels, while gated snapshot lanes surface
 * ``FACTORY_DROID_BUILD_MANAGED_LABEL`` because outputs stay inside HAM.
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

/**
 * Product-branded builder label for the chosen candidate shown in the card
 * headline. Uses approved product names (Claude, OpenCode, Factory Droid,
 * Cursor) instead of technical or legacy internal builder names.
 */
export function builderLabelForCandidate(c: Pick<CodingConductorCandidate, "provider">): string {
  return USER_FACING_BUILDER_LABEL[c.provider];
}

/**
 * Outcome-based plan description for the card normal view.
 * Derived from the chosen candidate's output intent; avoids internal vocabulary.
 */
export function planDescriptionForCard(
  chosen: Pick<
    CodingConductorCandidate,
    "output_kind" | "will_modify_code" | "will_open_pull_request"
  >,
): string {
  if (chosen.output_kind === "answer") return "HAM will answer without making any code changes.";
  if (chosen.output_kind === "report")
    return "HAM will run a read-only analysis and share the findings.";
  if (chosen.will_open_pull_request)
    return "HAM will make changes and open a pull request for your review.";
  if (chosen.will_modify_code)
    return "HAM will make changes and save a version for you to preview.";
  return "HAM will handle this request.";
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

/** True when the conductor preview should surface managed-workspace build approval. */
export function shouldShowManagedBuildApproval(payload: CodingConductorPreviewPayload): boolean {
  const chosen = payload.chosen;
  if (!chosen || chosen.provider !== "factory_droid_build" || !chosen.available) {
    return false;
  }
  const project = payload.project;
  if (!project.found || !project.project_id) return false;
  const target = (project.output_target || "").trim();
  if (target !== "managed_workspace") return false;
  if (project.has_workspace_id === false) return false;
  return true;
}

/** True when the conductor preview should surface OpenCode build approval. */
export function shouldShowOpencodeBuildApproval(payload: CodingConductorPreviewPayload): boolean {
  const chosen = payload.chosen;
  if (!chosen || chosen.provider !== "opencode_cli" || !chosen.available) {
    return false;
  }
  const project = payload.project;
  if (!project.found || !project.project_id) return false;
  const target = (project.output_target || "").trim();
  if (target !== "managed_workspace") return false;
  if (project.has_workspace_id === false) return false;
  return true;
}

/**
 * Show the chat approval strip only when execution needs an explicit user gate —
 * not for answer-only routing or generic recommendations.
 */
export function shouldSurfaceCodingConductorCard(payload: CodingConductorPreviewPayload): boolean {
  if (shouldShowManagedBuildApproval(payload)) return true;
  if (shouldShowOpencodeBuildApproval(payload)) return true;
  const chosen = payload.chosen;
  if (!chosen) return false;
  if (chosen.provider === "no_agent") return false;
  if (!chosen.will_modify_code) return false;
  if (!chosen.available || chosen.blockers.length > 0) return false;
  return chosen.requires_confirmation || payload.requires_approval;
}

/**
 * Safe, normalized builder keys (backend `selected_builder_key`) that have a
 * compatible in-chat managed approval lane. cursor / claude / hermes_agent are
 * intentionally absent — they have no managed in-chat lane in this phase.
 */
export type ManagedHandoffBuilderKey = "opencode" | "factory_droid";

const MANAGED_HANDOFF_PROVIDER: Record<ManagedHandoffBuilderKey, CodingConductorProviderKind> = {
  opencode: "opencode_cli",
  factory_droid: "factory_droid_build",
};

/**
 * Read a ready selected-builder managed handoff from chat `builder` metadata.
 * Returns null unless the backend marked a ready handoff for a supported
 * managed builder. Reads only safe, product-facing fields — never provider
 * internals, env names, or digest/launch fields.
 */
export function readManagedBuilderHandoff(
  builder: Record<string, unknown> | null | undefined,
): { key: ManagedHandoffBuilderKey; label: string } | null {
  if (!builder) return null;
  if (builder.builder_handoff_required !== true) return null;
  if (builder.selected_builder_state !== "ready") return null;
  const key = builder.selected_builder_key;
  if (key !== "opencode" && key !== "factory_droid") return null;
  const label =
    typeof builder.selected_builder_label === "string" ? builder.selected_builder_label : "";
  return { key, label };
}

/**
 * Synthesize the managed-approval payload the right-pane mount expects from a
 * selected-builder handoff. Reuses the existing CodingConductorPreviewPayload
 * shape + predicates so no duplicate approval component is introduced. The
 * managed panel re-validates server-side and owns all launch / proposal_digest
 * / base_revision / confirmed / polling mechanics (unchanged).
 */
export function managedHandoffPreviewPayload(
  key: ManagedHandoffBuilderKey,
  projectId: string,
): CodingConductorPreviewPayload {
  const provider = MANAGED_HANDOFF_PROVIDER[key];
  const isOpencode = provider === "opencode_cli";
  const chosen: CodingConductorCandidate = {
    provider,
    label: isOpencode ? "OpenCode" : FACTORY_DROID_BUILD_MANAGED_LABEL,
    available: true,
    reason: "",
    blockers: [],
    confidence: 1,
    output_kind: isOpencode ? "mission" : "pull_request",
    requires_operator: false,
    requires_confirmation: true,
    will_modify_code: true,
    // Managed-workspace snapshot, not a GitHub PR.
    will_open_pull_request: false,
    builder_id: null,
    builder_name: null,
  };
  return {
    kind: "coding_conductor_preview",
    preview_id: `handoff:${key}:${projectId}`,
    task_kind: "feature",
    task_confidence: 1,
    chosen,
    candidates: [chosen],
    blockers: [],
    recommendation_reason: "",
    requires_approval: true,
    approval_kind: "confirm",
    project: {
      found: true,
      project_id: projectId,
      build_lane_enabled: true,
      has_github_repo: false,
      output_target: "managed_workspace",
      has_workspace_id: true,
    },
    is_operator: false,
  };
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
  "opencode_cli",
  "factory_droid",
  "cursor_cloud",
  "claude_agent",
  "claude_code",
] as const;
