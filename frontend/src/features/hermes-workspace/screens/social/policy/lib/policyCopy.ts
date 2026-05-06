/**
 * UI strings for SocialPolicy editor. Centralized to keep components clean
 * and to allow tests to lock copy + error code mappings.
 */
import type {
  AutopilotMode,
  EmojiPolicy,
  LengthPreference,
  PostingActionId,
  ProviderId,
  ProviderMode,
  SocialPolicyAdvisoryCode,
  SocialPolicyServerError,
  Tone,
} from "./policyTypes";

export const PROVIDER_LABELS: Record<ProviderId, string> = {
  x: "X (Twitter)",
  telegram: "Telegram",
  discord: "Discord",
};

export const PROVIDER_MODE_LABELS: Record<ProviderMode, string> = {
  off: "Off",
  preview: "Preview only",
  approval_required: "Approval required",
  autopilot: "Autopilot",
};

export const AUTOPILOT_MODE_LABELS: Record<AutopilotMode, string> = {
  off: "Off",
  manual_only: "Manual only",
  armed: "Armed",
};

export const POSTING_ACTION_LABELS: Record<PostingActionId, string> = {
  post: "Post",
  quote: "Quote",
  reply: "Reply",
};

export const TONE_LABELS: Record<Tone, string> = {
  neutral: "Neutral",
  warm: "Warm",
  playful: "Playful",
  formal: "Formal",
};

export const LENGTH_LABELS: Record<LengthPreference, string> = {
  short: "Short",
  standard: "Standard",
  long: "Long",
};

export const EMOJI_LABELS: Record<EmojiPolicy, string> = {
  never: "Never",
  sparingly: "Sparingly",
  free: "Free",
};

/** D.2 advisory code → operator-facing label. */
export const ADVISORY_LABELS: Record<SocialPolicyAdvisoryCode, string> = {
  policy_document_missing: "No SocialPolicy on disk yet — saving the editor will create one.",
  policy_provider_unmapped: "This provider is not mapped in the SocialPolicy.",
  policy_posting_mode_off: "Posting mode is off in the SocialPolicy for this provider.",
  policy_reply_mode_off: "Reply mode is off in the SocialPolicy for this provider.",
  policy_target_label_disabled: "This delivery target is disabled in the SocialPolicy.",
  policy_live_autonomy_not_armed: "Live autonomy is not armed for this provider.",
  policy_action_not_allowed: "This action is not in the SocialPolicy's allowed action list.",
};

/** Server error code → friendly message. */
export const ERROR_LABELS: Record<SocialPolicyServerError["code"], string> = {
  SOCIAL_POLICY_AUTH_REQUIRED:
    "Server requires an operator write token. Provide one and try again.",
  SOCIAL_POLICY_AUTH_INVALID:
    "Server rejected the operator write token. Check the token with your operator.",
  SOCIAL_POLICY_WRITES_DISABLED:
    "Policy writes are disabled on the server. Ask your operator to enable HAM_SOCIAL_POLICY_WRITE_TOKEN.",
  SOCIAL_POLICY_PHRASE_INVALID: "Confirmation phrase did not match. Type it exactly as shown.",
  SOCIAL_POLICY_LIVE_AUTONOMY_DISABLED:
    "Live autonomy changes are disabled — the editor never asks for this. Reload and re-preview.",
  SOCIAL_POLICY_LIVE_AUTONOMY_PHRASE_INVALID:
    "Live autonomy phrase mismatch — the editor never asks for this. Reload and re-preview.",
  SOCIAL_POLICY_REVISION_CONFLICT:
    "Policy was changed elsewhere since you previewed. Reload to see the latest, then re-preview.",
  SOCIAL_POLICY_APPLY_INVALID:
    "Server rejected the apply payload. Fix the highlighted fields and re-preview.",
  SOCIAL_POLICY_PREVIEW_INVALID:
    "Server rejected the preview payload. Fix the highlighted fields and try again.",
  SOCIAL_POLICY_DOCUMENT_INVALID: "Server could not read the existing policy document.",
  SOCIAL_POLICY_BACKUP_NOT_FOUND: "Backup not found.",
  SOCIAL_POLICY_ROLLBACK_INVALID: "Rollback request rejected by the server.",
  SOCIAL_POLICY_ROLLBACK_PHRASE_INVALID: "Rollback confirmation phrase did not match.",
  UNKNOWN: "Unexpected server error.",
};

/** Static UI strings reused by multiple components. */
export const UI_TEXT = {
  screenTitle: "SocialPolicy editor",
  screenSubtitle:
    "Read, edit, preview, and save the persisted SocialPolicy. Live autonomy is intentionally not editable here.",
  tabsEdit: "Edit",
  tabsHistory: "History",
  tabsAudit: "Audit",
  loadButton: "Reload",
  resetButton: "Reset to loaded",
  previewButton: "Preview changes",
  applyButton: "Save policy",
  cancelButton: "Cancel",
  closeButton: "Close",
  loading: "Loading policy…",
  loadFailed: "Could not load the policy. Try Reload.",
  noChanges: "No changes pending.",
  invalidDocBanner:
    "The policy document on disk is not currently valid. The editor is showing defaults; saving will create a fresh valid document.",
  writesDisabledBanner:
    "Policy writes are disabled on the server. Apply will not succeed until your operator enables them.",
  liveAutonomyReadOnly: "Live autonomy is armed elsewhere — not editable here.",
  liveAutonomyReadOnlyOff: "Live autonomy is not armed — flipping it requires a separate flow.",
  personaReadOnly: "Persona reference is read-only in this editor.",
  applyChecklistTitle: "Pre-flight checklist",
  applyPhraseLabel: "Type the confirmation phrase exactly to save",
  applyTokenLabel: "Operator write token (Bearer)",
  applyTokenHelp:
    "Provided by your operator. The browser holds it only in memory and only sends it as the Authorization header.",
  applyConflictTitle: "Policy changed elsewhere",
  applyConflictBody:
    "Reload to see the latest version, then re-preview. Your local edits will be preserved.",
  reloadAndKeepEdits: "Reload and keep my edits",
  applySuccessTitle: "Policy saved",
  applySuccessNewRevision: "New revision",
  noPolicyOnDisk: "No SocialPolicy on disk yet — saving creates one.",
  historyEmpty: "No backups yet — they appear after the first save.",
  auditEmpty: "No audit entries yet.",
  cockpitChipsTitle: "SocialPolicy advisories",
  cockpitOpenEditor: "Open SocialPolicy editor →",
} as const;

/** Helper: map a server error envelope to a user-facing label. */
export function labelForError(err: SocialPolicyServerError): string {
  return ERROR_LABELS[err.code] ?? ERROR_LABELS.UNKNOWN;
}
