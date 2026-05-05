/**
 * TypeScript types mirroring the server SocialPolicy schema and the
 * /api/social/policy responses landed in D.1 + the snapshot block from D.2.
 *
 * Server source of truth:
 *   src/ham/social_policy/schema.py
 *   src/api/social_policy.py
 *
 * `project_root` is intentionally OMITTED from every response type so screens
 * cannot accidentally render a server filesystem path.
 */

export type AutopilotMode = "off" | "manual_only" | "armed";
export type ProviderMode = "off" | "preview" | "approval_required" | "autopilot";
export type ProviderId = "x" | "telegram" | "discord";
export type PostingActionId = "post" | "quote" | "reply";
export type ChannelTargetLabel = "home_channel" | "test_group";

export type Tone = "neutral" | "warm" | "playful" | "formal";
export type LengthPreference = "short" | "standard" | "long";
export type EmojiPolicy = "never" | "sparingly" | "free";

export interface PostingCaps {
  max_per_day: number;
  max_per_run: number;
  min_spacing_minutes: number;
}

export interface ReplyCaps {
  max_per_15m: number;
  max_per_hour: number;
  max_per_user_per_day: number;
  max_per_thread_per_day: number;
  min_seconds_between: number;
  batch_max_per_run: number;
}

export interface ChannelTarget {
  label: ChannelTargetLabel;
  enabled: boolean;
}

export interface ProviderPolicy {
  provider_id: ProviderId;
  posting_mode: ProviderMode;
  reply_mode: ProviderMode;
  posting_caps: PostingCaps;
  reply_caps: ReplyCaps;
  posting_actions_allowed: PostingActionId[];
  targets: ChannelTarget[];
}

export interface SafetyRules {
  blocked_topics: string[];
  block_links: boolean;
  min_relevance: number;
  consecutive_failure_stop: number;
  policy_rejection_stop: number;
}

export interface ContentStyle {
  tone: Tone;
  length_preference: LengthPreference;
  emoji_policy: EmojiPolicy;
  nature_tags: string[];
}

export interface PersonaRef {
  persona_id: string;
  persona_version: number;
}

export interface SocialPolicyDoc {
  schema_version: 1;
  persona: PersonaRef;
  content_style: ContentStyle;
  safety_rules: SafetyRules;
  providers: Record<ProviderId, ProviderPolicy>;
  autopilot_mode: AutopilotMode;
  live_autonomy_armed: boolean;
}

/** GET /api/social/policy — D.1 */
export interface SocialPolicyEndpointResponse {
  write_target: string;
  exists: boolean;
  policy: SocialPolicyDoc | null;
  revision: string;
  writes_enabled: boolean;
  live_apply_token_present: boolean;
  read_only: true;
}

/** Snapshot block on GET /api/social — D.2 (advisory only). */
export interface SocialPolicySnapshotBlock {
  exists: boolean;
  revision: string;
  advisory_only: true;
  autopilot_mode: AutopilotMode;
  live_autonomy_armed: boolean;
  writes_enabled: boolean;
  live_apply_token_present: boolean;
  warnings: string[];
  policy: SocialPolicyDoc | null;
}

export interface SocialPolicyChanges {
  policy: SocialPolicyDoc;
}

export interface SocialPolicyPreviewRequest {
  changes: SocialPolicyChanges;
  client_proposal_id?: string;
}

export interface SocialPolicyDiffEntry {
  path: string;
  before: unknown;
  after: unknown;
}

export interface SocialPolicyPreviewResponse {
  effective_before: SocialPolicyDoc;
  effective_after: SocialPolicyDoc;
  diff: SocialPolicyDiffEntry[];
  warnings: string[];
  write_target: string;
  proposal_digest: string;
  base_revision: string;
  live_autonomy_change: boolean;
  client_proposal_id?: string | null;
}

export interface SocialPolicyApplyRequest {
  changes: SocialPolicyChanges;
  base_revision: string;
  confirmation_phrase: string;
  /**
   * INTENTIONALLY ALWAYS UNDEFINED.
   * The editor never flips `live_autonomy_armed`, so it never sends the
   * second confirmation phrase. The adapter strips this field defensively.
   */
  live_autonomy_phrase?: undefined;
  client_proposal_id?: string;
}

export interface SocialPolicyApplyResponse {
  backup_id: string;
  audit_id: string;
  effective_after: SocialPolicyDoc;
  diff_applied: SocialPolicyDiffEntry[];
  new_revision: string;
  live_autonomy_change: boolean;
}

export interface SocialPolicyBackupListItem {
  backup_id: string;
  timestamp_iso: string;
  size_bytes: number;
}

export interface SocialPolicyHistoryResponse {
  backups: SocialPolicyBackupListItem[];
  read_only: true;
}

export interface SocialPolicyAuditEnvelope {
  audit_id?: string;
  timestamp?: string;
  action?: string;
  backup_id?: string;
  restored_from_backup_id?: string;
  pre_rollback_backup_id?: string;
  previous_revision?: string;
  new_revision?: string;
  live_autonomy_change?: boolean;
  result?: string;
}

export interface SocialPolicyAuditResponse {
  audits: SocialPolicyAuditEnvelope[];
  read_only: true;
}

/** Stable enum of D.2 advisory codes. Adapters/UI pass strings; type used for tests. */
export type SocialPolicyAdvisoryCode =
  | "policy_document_missing"
  | "policy_provider_unmapped"
  | "policy_posting_mode_off"
  | "policy_reply_mode_off"
  | "policy_target_label_disabled"
  | "policy_live_autonomy_not_armed"
  | "policy_action_not_allowed";

/** Server error envelope for /api/social/policy/{preview,apply}. */
export interface SocialPolicyServerError {
  status: number;
  code:
    | "SOCIAL_POLICY_AUTH_REQUIRED"
    | "SOCIAL_POLICY_AUTH_INVALID"
    | "SOCIAL_POLICY_WRITES_DISABLED"
    | "SOCIAL_POLICY_PHRASE_INVALID"
    | "SOCIAL_POLICY_LIVE_AUTONOMY_DISABLED"
    | "SOCIAL_POLICY_LIVE_AUTONOMY_PHRASE_INVALID"
    | "SOCIAL_POLICY_REVISION_CONFLICT"
    | "SOCIAL_POLICY_APPLY_INVALID"
    | "SOCIAL_POLICY_PREVIEW_INVALID"
    | "SOCIAL_POLICY_DOCUMENT_INVALID"
    | "SOCIAL_POLICY_BACKUP_NOT_FOUND"
    | "SOCIAL_POLICY_ROLLBACK_INVALID"
    | "SOCIAL_POLICY_ROLLBACK_PHRASE_INVALID"
    | "UNKNOWN";
  message: string;
}
