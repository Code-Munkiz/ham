/**
 * HAM /api/social — read-only social provider status facade.
 */

import { apiUrl, applyHamOperatorSecretHeaders, hamApiFetch } from "@/lib/ham/api";

import { workspaceApiPending } from "../lib/workspaceHamApiState";

const BASE = "/api/social";

export type SocialBridge = { status: "ready" } | { status: "pending"; detail: string };

export type SocialProvider = {
  id: string;
  label: string;
  status: "active" | "setup_required" | "blocked" | "coming_soon";
  configured: boolean;
  coming_soon: boolean;
  enabled_lanes: string[];
};

export type XProviderStatus = {
  provider_id: "x";
  label: "X";
  overall_readiness: "ready" | "limited" | "blocked" | "setup_required";
  readiness_reasons: string[];
  emergency_stop: { enabled: boolean };
  dry_run_defaults: {
    global_dry_run: boolean;
    controller_dry_run: boolean;
    reactive_dry_run: boolean;
    reactive_batch_dry_run: boolean;
  };
  broadcast_lane: {
    enabled: boolean;
    controller_enabled: boolean;
    live_controller_enabled: boolean;
    dry_run_available: boolean;
    live_configured: boolean;
    execution_allowed_now: boolean;
    reasons: string[];
  };
  reactive_lane: {
    enabled: boolean;
    inbox_discovery_enabled: boolean;
    dry_run_enabled: boolean;
    live_canary_enabled: boolean;
    batch_enabled: boolean;
    reasons: string[];
  };
  last_autonomous_post: Record<string, unknown> | null;
  last_reactive_reply: Record<string, unknown> | null;
  cap_cooldown_summary: {
    broadcast_daily_cap: number;
    broadcast_daily_used: number;
    broadcast_daily_remaining: number;
    broadcast_per_run_cap: number;
    broadcast_min_spacing_minutes: number;
    reactive_max_replies_per_15m: number;
    reactive_max_replies_per_hour: number;
    reactive_max_replies_per_user_per_day: number;
    reactive_max_replies_per_thread_per_day: number;
    reactive_min_seconds_between_replies: number;
    reactive_batch_max_replies_per_run: number;
  };
  paths: {
    execution_journal_path: string;
    audit_log_path: string;
  };
  read_only: boolean;
  mutation_attempted: boolean;
};

export type XCapabilities = {
  provider_id: "x";
  live_read_available: boolean;
  live_model_available: boolean;
  broadcast_dry_run_available: boolean;
  broadcast_live_available: boolean;
  broadcast_apply_available: boolean;
  reactive_inbox_discovery_available: boolean;
  reactive_dry_run_available: boolean;
  reactive_reply_canary_available: boolean;
  reactive_batch_available: boolean;
  reactive_reply_apply_available: boolean;
  reactive_batch_apply_available: boolean;
  live_apply_available: boolean;
  read_only: boolean;
};

export type XSetupChecklist = {
  provider_id: "x";
  items: { id: string; label: string; ok: boolean }[];
  feature_flags: Record<string, boolean>;
  read_only: boolean;
};

export type XSetupSummary = {
  provider_id: "x";
  provider_configured: boolean;
  overall_readiness: "ready" | "limited" | "blocked" | "setup_required";
  missing_requirement_ids: string[];
  ready_for_dry_run: boolean;
  ready_for_confirmed_live_reply: boolean;
  ready_for_reactive_batch: boolean;
  ready_for_broadcast: boolean;
  required_connections: Record<string, boolean>;
  lane_readiness: Record<string, Record<string, unknown>>;
  safe_identifiers: Record<string, string>;
  caps_cooldowns: Record<string, number>;
  feature_flags: Record<string, boolean>;
  recommended_next_steps: string[];
  read_only: boolean;
  mutation_attempted: boolean;
};

export type XJournalSummary = {
  provider_id: "x";
  journal_path: string;
  total_count_scanned: number;
  malformed_count: number;
  counts_by_execution_kind: Record<string, number>;
  latest_broadcast_post: Record<string, unknown> | null;
  latest_reactive_reply: Record<string, unknown> | null;
  recent_items: Record<string, unknown>[];
  bounds: {
    max_recent_items: number;
    max_rows_scanned: number;
    max_bytes_scanned: number;
  };
  read_only: boolean;
  mutation_attempted: boolean;
};

export type XAuditSummary = {
  provider_id: "x";
  audit_path: string;
  total_count_scanned: number;
  malformed_count: number;
  counts_by_event_type: Record<string, number>;
  latest_audit_ids: string[];
  recent_events: Record<string, unknown>[];
  bounds: {
    max_recent_events: number;
    max_rows_scanned: number;
    max_bytes_scanned: number;
  };
  read_only: boolean;
  mutation_attempted: boolean;
};

export type SocialMessagingRuntimeState =
  | "connected"
  | "connecting"
  | "retrying"
  | "fatal"
  | "stopped"
  | "unknown";
export type TelegramMode = "polling" | "polling_default" | "webhook" | "unset";
export type TelegramPlatformState =
  | "connected"
  | "retrying"
  | "fatal"
  | "stopped"
  | "unknown"
  | "not_reported";

export type SocialMessagingRuntimeStatus = {
  configured: boolean;
  base_url_configured: boolean;
  status_path_configured: boolean;
  status_file_available: boolean;
  source: "status_file" | "env" | "unknown";
  gateway_state: string;
  provider_runtime_state: SocialMessagingRuntimeState;
  active_agents: number | null;
  error_code: string | null;
  error_message: string | null;
};

export type SocialMessagingProviderStatus = {
  provider_id: "telegram" | "discord";
  label: "Telegram" | "Discord";
  overall_readiness: "ready" | "limited" | "blocked" | "setup_required";
  readiness_reasons: string[];
  hermes_gateway: SocialMessagingRuntimeStatus;
  required_connections: Record<string, boolean>;
  safe_identifiers: Record<string, string>;
  readiness?: "ready" | "limited" | "blocked" | "setup_required" | null;
  missing_requirements: string[];
  recommended_next_steps: string[];
  telegram_bot_token_present?: boolean | null;
  telegram_allowed_users_present?: boolean | null;
  telegram_home_channel_configured?: boolean | null;
  telegram_test_group_configured?: boolean | null;
  telegram_mode?: TelegramMode | null;
  hermes_gateway_base_url_present?: boolean | null;
  hermes_gateway_status_path_present?: boolean | null;
  hermes_gateway_runtime_state?: SocialMessagingRuntimeState | null;
  telegram_platform_state?: TelegramPlatformState | null;
  read_only: boolean;
  mutation_attempted: boolean;
  live_apply_available: false;
};

export type TelegramCapabilities = {
  provider_id: "telegram";
  bot_token_present: boolean;
  allowed_users_configured: boolean;
  home_channel_configured: boolean;
  test_group_configured: boolean;
  telegram_mode: TelegramMode;
  hermes_gateway_base_url_present: boolean;
  hermes_gateway_status_path_present: boolean;
  hermes_gateway_runtime_state: SocialMessagingRuntimeState;
  telegram_platform_state: TelegramPlatformState;
  readiness: "ready" | "limited" | "blocked" | "setup_required";
  missing_requirements: string[];
  recommended_next_steps: string[];
  polling_supported: boolean;
  webhook_supported: boolean;
  groups_supported: boolean;
  topics_supported: boolean;
  media_supported: boolean;
  voice_supported: boolean;
  inbound_available: boolean;
  preview_available: boolean;
  live_message_available: boolean;
  live_apply_available: boolean;
  activity_apply_available: boolean;
  reactive_reply_apply_available: boolean;
  read_only: boolean;
  mutation_attempted: boolean;
};

export type DiscordCapabilities = {
  provider_id: "discord";
  bot_token_present: boolean;
  allowed_users_or_roles_configured: boolean;
  guild_or_channel_configured: boolean;
  dms_supported: boolean;
  channels_supported: boolean;
  threads_supported: boolean;
  slash_commands_supported: boolean;
  media_supported: boolean;
  voice_supported: boolean;
  inbound_available: boolean;
  preview_available: false;
  live_message_available: false;
  live_apply_available: false;
  read_only: boolean;
  mutation_attempted: boolean;
};

export type SocialMessagingSetupChecklist = {
  provider_id: "telegram" | "discord";
  items: { id: string; label: string; ok: boolean }[];
  recommended_next_steps: string[];
  read_only: boolean;
  mutation_attempted: boolean;
};

export type SocialPersona = {
  persona_id: string;
  version: number;
  display_name: string;
  short_bio: string;
  mission: string;
  values: string[];
  tone_rules: string[];
  platform_adaptations: Record<
    string,
    {
      label: string;
      style: string;
      max_chars?: number | null;
      guidance: string[];
    }
  >;
  prohibited_content: string[];
  safety_boundaries: string[];
  example_replies: { input: string; output: string }[];
  example_announcements: string[];
  refusal_examples: { input: string; output: string }[];
  persona_digest: string;
  read_only: boolean;
  mutation_attempted: boolean;
};

export type SocialPreviewKind = "reactive_inbox" | "reactive_batch_dry_run" | "broadcast_preflight";

export type SocialPreviewResponse = {
  provider_id: "x";
  persona_id: string;
  persona_version: number;
  persona_digest: string;
  preview_kind: SocialPreviewKind;
  status: "completed" | "blocked" | "failed";
  execution_allowed: false;
  mutation_attempted: false;
  live_apply_available: false;
  reasons: string[];
  warnings: string[];
  result: Record<string, unknown>;
  proposal_digest: string | null;
  read_only: boolean;
};

export type TelegramMessagePreviewResponse = {
  provider_id: "telegram";
  preview_kind: "telegram_message";
  status: "completed" | "blocked" | "failed";
  execution_allowed: false;
  mutation_attempted: false;
  live_apply_available: false;
  persona_id: string;
  persona_version: number;
  persona_digest: string;
  proposal_digest: string | null;
  target: {
    kind: "home_channel" | "test_group";
    configured: boolean;
    masked_id: string;
  };
  message_preview: {
    text: string;
    char_count: number;
  };
  reasons: string[];
  warnings: string[];
  recommended_next_steps: string[];
  read_only: boolean;
};

export type TelegramActivityPreviewResponse = {
  provider_id: "telegram";
  preview_kind: "telegram_activity";
  status: "completed" | "blocked" | "failed";
  execution_allowed: false;
  mutation_attempted: false;
  live_apply_available: false;
  persona_id: string;
  persona_version: number;
  persona_digest: string;
  proposal_digest: string | null;
  target: {
    kind: "test_group";
    configured: boolean;
    masked_id: string;
  };
  activity_preview: {
    text: string;
    char_count: number;
    activity_kind: "status_update" | "test_activity";
  };
  governor: {
    allowed: boolean;
    reasons: string[];
    next_allowed_send_time: string | null;
  };
  reasons: string[];
  warnings: string[];
  recommended_next_steps: string[];
  read_only: boolean;
};

export type TelegramActivityRunOncePreviewResponse = {
  provider_id: "telegram";
  preview_kind: "telegram_activity_run_once";
  status: "completed" | "blocked" | "failed";
  dry_run: true;
  execution_allowed: false;
  mutation_attempted: false;
  live_apply_available: false;
  persona_id: string;
  persona_version: number;
  persona_digest: string;
  proposal_digest: string | null;
  target: {
    kind: "test_group";
    configured: boolean;
    masked_id: string;
  };
  activity_preview: {
    text: string;
    char_count: number;
    activity_kind: "status_update" | "test_activity";
  };
  governor: {
    allowed: boolean;
    reasons: string[];
    next_allowed_send_time: string | null;
  };
  reasons: string[];
  warnings: string[];
  recommended_next_steps: string[];
  read_only: boolean;
};

export type TelegramInboundPreviewResponse = {
  provider_id: "telegram";
  preview_kind: "telegram_inbound";
  status: "completed" | "blocked" | "failed";
  execution_allowed: false;
  mutation_attempted: false;
  live_apply_available: false;
  inbound_count: number;
  items: Array<{
    inbound_id: string;
    text: string;
    author_ref: string;
    chat_ref: string;
    session_ref: string;
    created_at: string | null;
    chat_type: string | null;
    already_answered: boolean;
    repliable: boolean;
    reasons: string[];
  }>;
  reasons: string[];
  warnings: string[];
  recommended_next_steps: string[];
  read_only: boolean;
};

export type TelegramReactiveRepliesPreviewResponse = {
  provider_id: "telegram";
  preview_kind: "telegram_reactive_replies";
  status: "completed" | "blocked" | "failed";
  execution_allowed: false;
  mutation_attempted: false;
  live_apply_available: false;
  persona_id: string;
  persona_version: number;
  persona_digest: string;
  inbound_count: number;
  processed_count: number;
  reply_candidate_count: number;
  items: Array<{
    inbound_id: string;
    inbound_text: string;
    author_ref: string;
    chat_ref: string;
    session_ref: string;
    classification: string;
    policy: {
      allowed: boolean;
      classification: string;
      reasons: string[];
    };
    governor: {
      allowed: boolean;
      reasons: string[];
      max_reply_candidates: number;
      reply_candidates_used: number;
    };
    reply_candidate_text: string;
    proposal_digest: string | null;
    already_answered: boolean;
    repliable: boolean;
    reasons: string[];
  }>;
  reasons: string[];
  warnings: string[];
  recommended_next_steps: string[];
  read_only: boolean;
};

export type TelegramReactiveReplyApplyResponse = {
  provider_id: "telegram";
  apply_kind: "telegram_reactive_reply";
  status: "blocked" | "sent" | "failed" | "duplicate";
  execution_allowed: boolean;
  mutation_attempted: boolean;
  live_apply_available: boolean;
  persona_id: string;
  persona_version: number;
  persona_digest: string;
  provider_message_id: string | null;
  target: {
    kind: "test_group";
    configured: boolean;
    masked_id: string;
  };
  inbound_id: string;
  reasons: string[];
  warnings: string[];
  result: Record<string, unknown>;
};

export type TelegramActivityApplyResponse = {
  provider_id: "telegram";
  apply_kind: "telegram_activity";
  status: "blocked" | "sent" | "failed" | "duplicate";
  execution_allowed: boolean;
  mutation_attempted: boolean;
  live_apply_available: boolean;
  persona_id: string;
  persona_version: number;
  persona_digest: string;
  provider_message_id: string | null;
  target: {
    kind: "test_group";
    configured: boolean;
    masked_id: string;
  };
  reasons: string[];
  warnings: string[];
  result: Record<string, unknown>;
};

export type TelegramMessageApplyResponse = {
  provider_id: "telegram";
  apply_kind: "telegram_message";
  status: "blocked" | "sent" | "failed" | "duplicate";
  execution_allowed: boolean;
  mutation_attempted: boolean;
  live_apply_available: boolean;
  persona_id: string;
  persona_version: number;
  persona_digest: string;
  provider_message_id: string | null;
  target: {
    kind: "home_channel" | "test_group";
    configured: boolean;
    masked_id: string;
  };
  reasons: string[];
  warnings: string[];
  result: Record<string, unknown>;
};

export type SocialReactiveReplyApplyResponse = {
  provider_id: "x";
  persona_id: string;
  persona_version: number;
  persona_digest: string;
  apply_kind: "reactive_reply";
  status: "blocked" | "executed" | "failed";
  execution_allowed: boolean;
  mutation_attempted: boolean;
  live_apply_available: boolean;
  provider_status_code: number | null;
  provider_post_id: string | null;
  execution_kind: string;
  audit_ids: string[];
  journal_path: string;
  audit_path: string;
  reasons: string[];
  warnings: string[];
  result: Record<string, unknown>;
};

export type SocialReactiveBatchApplyResponse = {
  provider_id: "x";
  persona_id: string;
  persona_version: number;
  persona_digest: string;
  apply_kind: "reactive_batch";
  status: "blocked" | "completed" | "stopped" | "failed";
  execution_allowed: boolean;
  mutation_attempted: boolean;
  live_apply_available: boolean;
  attempted_count: number;
  executed_count: number;
  failed_count: number;
  blocked_count: number;
  provider_post_ids: string[];
  execution_kind: string;
  audit_ids: string[];
  journal_path: string;
  audit_path: string;
  reasons: string[];
  warnings: string[];
  result: Record<string, unknown>;
};

export type SocialBroadcastApplyResponse = {
  provider_id: "x";
  persona_id: string;
  persona_version: number;
  persona_digest: string;
  apply_kind: "broadcast_post";
  status: "blocked" | "executed" | "failed";
  execution_allowed: boolean;
  mutation_attempted: boolean;
  live_apply_available: boolean;
  provider_status_code: number | null;
  provider_post_id: string | null;
  execution_kind: string;
  audit_ids: string[];
  journal_path: string;
  audit_path: string;
  reasons: string[];
  warnings: string[];
  result: Record<string, unknown>;
};

/**
 * D.2 advisory snapshot block surfaced on GET /api/social. Optional so older
 * server builds without the advisory layer continue to type-check.
 */
export type SocialPolicySnapshotBlockOnSocial = {
  exists: boolean;
  revision: string;
  advisory_only: true;
  autopilot_mode: "off" | "manual_only" | "armed";
  live_autonomy_armed: boolean;
  writes_enabled: boolean;
  live_apply_token_present: boolean;
  warnings: string[];
  policy: Record<string, unknown> | null;
};

export type SocialAutonomyStatus = "draft" | "running" | "paused" | "stopped";
export type SocialAutonomyChannel = "x" | "telegram" | "discord";
export type SocialAutonomyAction = "reply" | "broadcast" | "activity" | "message";

export type SocialAutonomyChannelConfig = {
  enabled: boolean;
  available: boolean;
};

export type SocialAutonomyQuietHours = {
  start_hour: number;
  end_hour: number;
  timezone: string;
};

export type GoHamSocialProfile = {
  profile_id: string;
  workspace_id: string | null;
  project_id: string | null;
  status: SocialAutonomyStatus;
  goal: string;
  persona_id: string;
  channels: Record<SocialAutonomyChannel, SocialAutonomyChannelConfig>;
  actions_allowed_per_channel: Record<SocialAutonomyChannel, SocialAutonomyAction[]>;
  daily_caps: Record<SocialAutonomyChannel, number>;
  cadence: string;
  quiet_hours: SocialAutonomyQuietHours | null;
  forbidden_topics: string[];
  safety_rules: string[];
  learning_enabled: boolean;
  emergency_stop: boolean;
  last_run_at?: string | null;
  next_run_at?: string | null;
  last_tick_summary?: SocialAutonomyTickSummary | null;
  created_at: string;
  updated_at: string;
  // M4 optional status fields — absent when backend does not yet supply them
  storage?: { backend: "file" | "firestore" } | null;
  scheduler_route?: { state: "disabled" | "dry-run-only" | "live" } | null;
  usage_today?: Record<string, { messages?: number; replies?: number; total?: number }> | null;
};

/** Poller status response from GET /api/social/providers/telegram/poller/status */
export type PollerStatus = {
  last_run_at: string | null;
  last_offset: number | null;
  transcript_count_today: number;
  last_error_code: string | null;
};

/** Telegram readiness value for the status panel row. */
export type TelegramReadinessValue =
  | "ready"
  | "setup_required"
  | "degraded"
  | "limited"
  | "blocked";

/** Shape returned by getTelegramCapabilitiesPanel — relevant fields for SocialStatusPanel. */
export type TelegramCapabilitiesPanel = {
  telegram_readiness?: TelegramReadinessValue | null;
  hermes_gateway_readiness?: string | null;
  social_critic?: { status: "available" | "unavailable" | "not configured" } | null;
};

export type SocialAutonomySettingsPatch = {
  daily_caps?: Partial<Record<SocialAutonomyChannel, number>>;
  quiet_hours?: SocialAutonomyQuietHours | null;
};

export type SocialAutonomyTickPreview = {
  channel: SocialAutonomyChannel;
  action: SocialAutonomyAction | null;
  would_run: boolean;
  reasons: string[];
  next_run_summary: string;
};

export type SocialAutonomyTickSummary = {
  ran: boolean;
  dry_run: boolean;
  actions_considered: string[];
  actions_taken: string[];
  blocked_reasons: string[];
  profile_status: SocialAutonomyStatus;
  recorded_at: string;
  next_run_summary: string | null;
};

export type SocialAutonomyTickResult = {
  ran: boolean;
  dry_run: boolean;
  actions_considered: string[];
  actions_taken: string[];
  blocked_reasons: string[];
  next_run_summary: string | null;
  profile_status: SocialAutonomyStatus;
};

export type SocialAutonomyWriteStatus = {
  kind: "ham_social_autonomy_write_status";
  writes_enabled: boolean;
};

export type SocialSnapshot = {
  providers: SocialProvider[];
  xStatus: XProviderStatus;
  xCapabilities: XCapabilities;
  xSetup: XSetupChecklist;
  xSetupSummary: XSetupSummary;
  xJournal: XJournalSummary;
  xAudit: XAuditSummary;
  telegramStatus: SocialMessagingProviderStatus;
  telegramCapabilities: TelegramCapabilities;
  telegramSetup: SocialMessagingSetupChecklist;
  discordStatus: SocialMessagingProviderStatus;
  discordCapabilities: DiscordCapabilities;
  discordSetup: SocialMessagingSetupChecklist;
  persona: SocialPersona;
  /** D.2 advisory snapshot block (optional, type-only — runtime unchanged). */
  policy?: SocialPolicySnapshotBlockOnSocial | null;
};

async function getJson<T>(path: string): Promise<T> {
  const res = await hamApiFetch(path, { credentials: "include" });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

async function postPreview<T>(path: string, body: Record<string, unknown> = {}): Promise<T> {
  const res = await hamApiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

async function requestJson<T>(
  path: string,
  init: { method?: "GET" | "POST" | "PATCH"; body?: unknown; writeToken?: string } = {},
): Promise<T> {
  const method = init.method ?? "GET";
  const headers = new Headers(
    init.body === undefined ? undefined : { "Content-Type": "application/json" },
  );
  if (init.writeToken !== undefined) {
    // Preserves Clerk Authorization and routes HAM secrets through X-Ham-Operator-Authorization.
    await applyHamOperatorSecretHeaders(headers, init.writeToken);
  }
  const requestInit: RequestInit = {
    method,
    headers,
    credentials: "include",
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  };
  const res =
    init.writeToken === undefined
      ? await hamApiFetch(path, requestInit)
      : await fetch(apiUrl(path), requestInit);
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as {
        detail?: { error?: { message?: string } } | { message?: string } | string;
      };
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail && "error" in body.detail && body.detail.error?.message) {
        detail = body.detail.error.message;
      } else if (body.detail && "message" in body.detail && body.detail.message) {
        detail = body.detail.message;
      }
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const socialAdapter = {
  description: "HAM /api/social — read-only social provider status",

  async getAutonomyProfile(): Promise<{
    profile: GoHamSocialProfile | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      return {
        profile: await requestJson<GoHamSocialProfile>(`${BASE}/autonomy`),
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        profile: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async previewAutonomyProfile(profile: GoHamSocialProfile): Promise<{
    profile: GoHamSocialProfile | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      return {
        profile: await requestJson<GoHamSocialProfile>(`${BASE}/autonomy/preview`, {
          method: "POST",
          body: profile,
        }),
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        profile: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async getAutonomyWriteStatus(): Promise<{
    status: SocialAutonomyWriteStatus | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      return {
        status: await requestJson<SocialAutonomyWriteStatus>(`${BASE}/autonomy/write-status`),
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        status: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async launchAutonomy(writeToken = ""): Promise<{
    profile: GoHamSocialProfile | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      return {
        profile: await requestJson<GoHamSocialProfile>(`${BASE}/autonomy/launch`, {
          method: "POST",
          writeToken,
        }),
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        profile: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async pauseAutonomy(writeToken = ""): Promise<{
    profile: GoHamSocialProfile | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      return {
        profile: await requestJson<GoHamSocialProfile>(`${BASE}/autonomy/pause`, {
          method: "POST",
          writeToken,
        }),
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        profile: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async stopAutonomy(
    input?: { emergency_stop?: boolean },
    writeToken = "",
  ): Promise<{
    profile: GoHamSocialProfile | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      return {
        profile: await requestJson<GoHamSocialProfile>(`${BASE}/autonomy/stop`, {
          method: "POST",
          body: input ?? {},
          writeToken,
        }),
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        profile: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async updateAutonomyLimits(
    input: SocialAutonomySettingsPatch,
    writeToken = "",
  ): Promise<{
    profile: GoHamSocialProfile | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      return {
        profile: await requestJson<GoHamSocialProfile>(`${BASE}/autonomy/settings`, {
          method: "PATCH",
          body: input,
          writeToken,
        }),
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        profile: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async previewAutonomyTick(input: { dry_run: boolean }): Promise<{
    tick: SocialAutonomyTickResult | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      return {
        tick: await requestJson<SocialAutonomyTickResult>(`${BASE}/autonomy/tick`, {
          method: "POST",
          body: input,
        }),
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        tick: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async getPollerStatus(): Promise<{
    pollerStatus: PollerStatus | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      return {
        pollerStatus: await requestJson<PollerStatus>(`${BASE}/providers/telegram/poller/status`),
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        pollerStatus: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async getTelegramCapabilitiesPanel(): Promise<{
    caps: TelegramCapabilitiesPanel | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      const raw = await requestJson<{
        telegram_readiness?: string | null;
        hermes_gateway_readiness?: string | null;
      }>(`${BASE}/providers/telegram/capabilities`);

      // Derive social_critic status from hermes_gateway_readiness.
      let socialCriticStatus: "available" | "unavailable" | "not configured" = "unavailable";
      if (raw.hermes_gateway_readiness === "ready") socialCriticStatus = "available";
      else if (raw.hermes_gateway_readiness === "not_configured")
        socialCriticStatus = "not configured";

      return {
        caps: {
          telegram_readiness: (raw.telegram_readiness as TelegramReadinessValue) ?? null,
          hermes_gateway_readiness: raw.hermes_gateway_readiness ?? null,
          social_critic: { status: socialCriticStatus },
        },
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        caps: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async loadSnapshot(): Promise<{
    snapshot: SocialSnapshot | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      const [
        providers,
        xStatus,
        xCapabilities,
        xSetup,
        xSetupSummary,
        xJournal,
        xAudit,
        telegramStatus,
        telegramCapabilities,
        telegramSetup,
        discordStatus,
        discordCapabilities,
        discordSetup,
        persona,
      ] = await Promise.all([
        getJson<{ providers?: SocialProvider[] }>(`${BASE}/providers`),
        getJson<XProviderStatus>(`${BASE}/providers/x/status`),
        getJson<XCapabilities>(`${BASE}/providers/x/capabilities`),
        getJson<XSetupChecklist>(`${BASE}/providers/x/setup/checklist`),
        getJson<XSetupSummary>(`${BASE}/providers/x/setup/summary`),
        getJson<XJournalSummary>(`${BASE}/providers/x/journal/summary`),
        getJson<XAuditSummary>(`${BASE}/providers/x/audit/summary`),
        getJson<SocialMessagingProviderStatus>(`${BASE}/providers/telegram/status`),
        getJson<TelegramCapabilities>(`${BASE}/providers/telegram/capabilities`),
        getJson<SocialMessagingSetupChecklist>(`${BASE}/providers/telegram/setup/checklist`),
        getJson<SocialMessagingProviderStatus>(`${BASE}/providers/discord/status`),
        getJson<DiscordCapabilities>(`${BASE}/providers/discord/capabilities`),
        getJson<SocialMessagingSetupChecklist>(`${BASE}/providers/discord/setup/checklist`),
        getJson<SocialPersona>(`${BASE}/persona/current`),
      ]);
      return {
        snapshot: {
          providers: Array.isArray(providers.providers) ? providers.providers : [],
          xStatus,
          xCapabilities,
          xSetup,
          xSetupSummary,
          xJournal,
          xAudit,
          telegramStatus,
          telegramCapabilities,
          telegramSetup,
          discordStatus,
          discordCapabilities,
          discordSetup,
          persona,
        },
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        snapshot: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async previewInboxDiscovery(): Promise<{
    preview: SocialPreviewResponse | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      return {
        preview: await postPreview<SocialPreviewResponse>(
          `${BASE}/providers/x/reactive/inbox/preview`,
        ),
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        preview: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async previewReactiveBatchDryRun(
    candidates: Record<string, unknown>[] = [],
  ): Promise<{ preview: SocialPreviewResponse | null; bridge: SocialBridge; error?: string }> {
    try {
      return {
        preview: await postPreview<SocialPreviewResponse>(
          `${BASE}/providers/x/reactive/batch/dry-run`,
          {
            candidates,
          },
        ),
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        preview: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async previewBroadcastPreflight(): Promise<{
    preview: SocialPreviewResponse | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      return {
        preview: await postPreview<SocialPreviewResponse>(
          `${BASE}/providers/x/broadcast/preflight`,
        ),
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        preview: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async previewTelegramMessage(): Promise<{
    preview: TelegramMessagePreviewResponse | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      return {
        preview: await postPreview<TelegramMessagePreviewResponse>(
          `${BASE}/providers/telegram/messages/preview`,
        ),
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        preview: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async previewTelegramActivity(input?: {
    activityKind?: "status_update" | "test_activity";
    clientRequestId?: string;
  }): Promise<{
    preview: TelegramActivityPreviewResponse | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      return {
        preview: await postPreview<TelegramActivityPreviewResponse>(
          `${BASE}/providers/telegram/activity/preview`,
          {
            activity_kind: input?.activityKind ?? "test_activity",
            client_request_id: input?.clientRequestId,
          },
        ),
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        preview: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async previewTelegramActivityRunOnce(input?: {
    activityKind?: "status_update" | "test_activity";
    clientRequestId?: string;
  }): Promise<{
    preview: TelegramActivityRunOncePreviewResponse | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      return {
        preview: await postPreview<TelegramActivityRunOncePreviewResponse>(
          `${BASE}/providers/telegram/activity/run-once/preview`,
          {
            activity_kind: input?.activityKind ?? "test_activity",
            client_request_id: input?.clientRequestId,
          },
        ),
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        preview: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async previewTelegramInbound(): Promise<{
    preview: TelegramInboundPreviewResponse | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      const res = await hamApiFetch(`${BASE}/providers/telegram/inbound/preview`, {
        method: "GET",
        credentials: "include",
      });
      if (!res.ok)
        return { preview: null, bridge: { status: "pending", detail: `HTTP ${res.status}` } };
      return {
        preview: (await res.json()) as TelegramInboundPreviewResponse,
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        preview: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async previewTelegramReactiveReplies(): Promise<{
    preview: TelegramReactiveRepliesPreviewResponse | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      return {
        preview: await postPreview<TelegramReactiveRepliesPreviewResponse>(
          `${BASE}/providers/telegram/reactive/replies/preview`,
          {},
        ),
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        preview: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async getReviewQueueSummary(input?: { limit?: number }): Promise<{
    summary: ReviewQueueSummary | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      const params = new URLSearchParams();
      if (typeof input?.limit === "number") {
        params.set("limit", String(input.limit));
      }
      const query = params.toString();
      const path = query ? `${BASE}/review-queue/summary?${query}` : `${BASE}/review-queue/summary`;
      const summary = await getJson<ReviewQueueSummary>(path);
      return { summary, bridge: { status: "ready" } };
    } catch (e) {
      return {
        summary: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async getLearningHints(input?: {
    channel?: "x" | "telegram" | "discord" | "other";
    limit?: number;
  }): Promise<{
    hints: LearningHints | null;
    bridge: SocialBridge;
    error?: string;
  }> {
    try {
      const params = new URLSearchParams();
      if (input?.channel) params.set("channel", input.channel);
      if (typeof input?.limit === "number") params.set("limit", String(input.limit));
      const query = params.toString();
      const path = query ? `${BASE}/learning/hints?${query}` : `${BASE}/learning/hints`;
      const hints = await getJson<LearningHints>(path);
      return { hints, bridge: { status: "ready" } };
    } catch (e) {
      return {
        hints: null,
        bridge: workspaceApiPending("social", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },
} as const;

export type ReviewQueueSafeItem = {
  record_id: string;
  action_type: string | null;
  channel: string | null;
  created_at: string | null;
  text: string;
  decision_state: string | null;
};

export type ReviewQueueSummary = {
  pending_count: number;
  approved_recent_count: number;
  rejected_recent_count: number;
  items: ReviewQueueSafeItem[];
  generated_at: string;
};

export type LearningHints = {
  hints: string;
  generated_at: string;
};
