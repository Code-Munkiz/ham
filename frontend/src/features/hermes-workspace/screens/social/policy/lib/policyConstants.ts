/**
 * Pinned constants that mirror the server. Drift is caught by tests in
 * policyCopy.test.ts and socialPolicyAdapter.test.ts.
 *
 * Server source of truth:
 *   src/api/social_policy.py
 *     APPLY_CONFIRMATION_PHRASE = "SAVE SOCIAL POLICY"
 *     RESTORE_CONFIRMATION_PHRASE = "RESTORE SOCIAL POLICY"
 *     LIVE_AUTONOMY_CONFIRMATION_PHRASE = "ARM SOCIAL AUTONOMY"
 */

/** The save phrase the operator must type to apply edits. */
export const APPLY_CONFIRMATION_PHRASE = "SAVE SOCIAL POLICY" as const;

/** Used by the (deferred) rollback flow. Surface here only as a constant. */
export const RESTORE_CONFIRMATION_PHRASE = "RESTORE SOCIAL POLICY" as const;

/**
 * Used to flip live_autonomy_armed elsewhere. This editor NEVER sends it
 * — exported only to assert in tests that the apply body never includes it.
 */
export const LIVE_AUTONOMY_CONFIRMATION_PHRASE = "ARM SOCIAL AUTONOMY" as const;

export const POLICY_PATHS = {
  policy: "/api/social/policy",
  preview: "/api/social/policy/preview",
  apply: "/api/social/policy/apply",
  history: "/api/social/policy/history",
  audit: "/api/social/policy/audit",
} as const;

export const SUPPORTED_PROVIDER_IDS = ["x", "telegram", "discord"] as const;
export const SUPPORTED_TARGET_LABELS = ["home_channel", "test_group"] as const;
export const SUPPORTED_POSTING_ACTIONS = ["post", "quote", "reply"] as const;

export const PROVIDER_MODE_VALUES = ["off", "preview", "approval_required", "autopilot"] as const;
export const AUTOPILOT_MODE_VALUES = ["off", "manual_only", "armed"] as const;
export const TONE_VALUES = ["neutral", "warm", "playful", "formal"] as const;
export const LENGTH_VALUES = ["short", "standard", "long"] as const;
export const EMOJI_VALUES = ["never", "sparingly", "free"] as const;

/** Server hard bounds (mirrored from schema.py). */
export const POSTING_CAP_BOUNDS = {
  max_per_day: { min: 0, max: 50 },
  max_per_run: { min: 0, max: 5 },
  min_spacing_minutes: { min: 0, max: 720 },
} as const;

export const REPLY_CAP_BOUNDS = {
  max_per_15m: { min: 0, max: 20 },
  max_per_hour: { min: 0, max: 60 },
  max_per_user_per_day: { min: 0, max: 10 },
  max_per_thread_per_day: { min: 0, max: 10 },
  min_seconds_between: { min: 0, max: 600 },
  batch_max_per_run: { min: 0, max: 5 },
} as const;

/**
 * Centralized snake_case field-name literals for the cap subtrees.
 * Editor components reference these via camelCase identifiers so the
 * snake_case literals only appear once, in this file.
 */
export const POSTING_CAP_FIELDS = {
  maxPerDay: "max_per_day",
  maxPerRun: "max_per_run",
  minSpacingMinutes: "min_spacing_minutes",
} as const;

export const REPLY_CAP_FIELDS = {
  maxPer15m: "max_per_15m",
  maxPerHour: "max_per_hour",
  maxPerUserPerDay: "max_per_user_per_day",
  maxPerThreadPerDay: "max_per_thread_per_day",
  minSecondsBetween: "min_seconds_between",
  batchMaxPerRun: "batch_max_per_run",
} as const;

export type PostingCapField =
  (typeof POSTING_CAP_FIELDS)[keyof typeof POSTING_CAP_FIELDS];
export type ReplyCapField =
  (typeof REPLY_CAP_FIELDS)[keyof typeof REPLY_CAP_FIELDS];

export const SAFETY_BOUNDS = {
  blocked_topics_max_count: 32,
  consecutive_failure_stop: { min: 1, max: 10 },
  policy_rejection_stop: { min: 1, max: 20 },
  min_relevance: { min: 0, max: 1, step: 0.05 },
} as const;

export const CONTENT_STYLE_BOUNDS = {
  nature_tags_max_count: 8,
} as const;

/** Same lower-case slug regex the server uses for tags. */
export const TAG_SLUG_RE = /^[a-z0-9][a-z0-9._-]{0,63}$/;

/** Detects content that the server's redaction layer would mangle. */
export const TOKEN_SHAPE_RE =
  /(api[_-]?key|access[_-]?token|bearer\s+[a-z0-9._~+/=-]{8,}|sk-[a-z0-9_-]{10,}|gho_[a-z0-9_-]{10,}|ghp_[a-z0-9_-]{10,}|[a-z0-9_./+=-]{48,})/i;

/** Detects raw numeric IDs (Telegram chat IDs etc.) — same as schema.py. */
export const RAW_NUMERIC_ID_RE = /(?<![A-Za-z])-?\d{6,}(?![A-Za-z])/;
