/**
 * Normie-safe label maps for Builder Studio.
 *
 * Label values must never expose raw provider ids
 * (e.g. opencode_cli / factory_droid_build / claude_agent / cursor_cloud)
 * or technical routing vocabulary. The dedicated lock test in
 * `__tests__/builderStudioLabels.test.ts` enforces that invariant.
 */

export type PermissionPreset =
  | "safe_docs"
  | "app_build"
  | "bug_fix"
  | "refactor"
  | "game_build"
  | "test_write"
  | "readonly_analyst"
  | "custom";

export type ModelSource = "ham_default" | "connected_tools_byok" | "workspace_default";

export type ReviewMode = "always" | "on_mutation" | "on_delete_only" | "never";

export type DeletionPolicy = "deny" | "require_review" | "allow_with_warning";

export type ExternalNetworkPolicy = "deny" | "ask" | "allow";

export type TaskKind =
  | "explain"
  | "audit"
  | "security_review"
  | "architecture_report"
  | "doc_fix"
  | "comments_only"
  | "format_only"
  | "typo_only"
  | "single_file_edit"
  | "feature"
  | "fix"
  | "refactor"
  | "multi_file_edit";

export const PERMISSION_PRESET_LABELS: Record<PermissionPreset, string> = {
  safe_docs: "Docs Editor",
  app_build: "App Builder",
  bug_fix: "Bug Fixer",
  refactor: "Refactor Assistant",
  game_build: "Game Builder",
  test_write: "Test Writer",
  readonly_analyst: "Read-only Analyst",
  custom: "Advanced",
};

export const MODEL_SOURCE_LABELS: Record<ModelSource, string> = {
  ham_default: "HAM default",
  connected_tools_byok: "Use my connected key",
  workspace_default: "Workspace default",
};

export const REVIEW_MODE_LABELS: Record<ReviewMode, string> = {
  always: "Always review",
  on_mutation: "Review on changes",
  on_delete_only: "Review on deletes only",
  never: "Never review",
};

export const DELETION_POLICY_LABELS: Record<DeletionPolicy, string> = {
  deny: "Never delete",
  require_review: "Ask before deleting",
  allow_with_warning: "Allow deletes (with a warning)",
};

export const EXTERNAL_NETWORK_POLICY_LABELS: Record<ExternalNetworkPolicy, string> = {
  deny: "No internet access",
  ask: "Ask before going online",
  allow: "Allow internet access",
};

export const TASK_KIND_LABELS: Record<TaskKind, string> = {
  explain: "Explain code",
  audit: "Audit",
  security_review: "Security review",
  architecture_report: "Architecture report",
  doc_fix: "Documentation fix",
  comments_only: "Comments only",
  format_only: "Formatting only",
  typo_only: "Typo only",
  single_file_edit: "Single-file edit",
  feature: "New feature",
  fix: "Bug fix",
  refactor: "Refactor",
  multi_file_edit: "Multi-file edit",
};

export function formatIntentTagsForDisplay(tags: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of tags) {
    const t = raw.trim().toLowerCase();
    if (!t) continue;
    if (seen.has(t)) continue;
    seen.add(t);
    out.push(t);
  }
  return out;
}
