export interface RunRecord {
  run_id: string;
  created_at: string;
  author: string | null;
  profile_id: string;
  profile_version: string;
  backend_id: string;
  backend_version: string;
  prompt_summary: string;
  bridge_result: BridgeResult;
  hermes_review: HermesReview;
}

/** Matches `src/bridge/contracts.py` BridgeStatus */
export type BridgeStatus =
  | 'rejected'
  | 'executed'
  | 'failed'
  | 'timed_out'
  | 'partial';

/** Matches `src/bridge/contracts.py` PolicyDecision */
export interface PolicyDecision {
  accepted: boolean;
  reasons: string[];
  policy_version: string;
}

/** Matches `src/bridge/contracts.py` CommandState */
export type CommandState =
  | 'executed'
  | 'failed'
  | 'timed_out'
  | 'skipped';

/**
 * Matches `src/bridge/contracts.py` CommandEvidence
 * (serialized in RunRecord.bridge_result from pydantic).
 */
export interface CommandEvidence {
  command_id: string;
  argv: string[];
  working_dir: string;
  status: CommandState;
  exit_code: number | null;
  timed_out: boolean;
  stdout: string;
  stderr: string;
  stdout_truncated: boolean;
  stderr_truncated: boolean;
  started_at: string;
  ended_at: string;
  duration_ms: number;
}

/**
 * Matches `src/bridge/contracts.py` BridgeResult
 * (embedded in persisted run JSON and /api/runs).
 */
export interface BridgeResult {
  intent_id: string;
  request_id: string;
  run_id: string;
  status: BridgeStatus;
  policy_decision: PolicyDecision;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  commands: CommandEvidence[];
  summary: string;
  pre_exec_git_status?: string | null;
  post_exec_git_status?: string | null;
  mutation_detected?: boolean | null;
  artifacts: string[];
}

/** Bridge completed command execution successfully (green-path for inspect runs). */
export function isBridgeSuccess(b: BridgeResult): boolean {
  return b.status === 'executed';
}

export interface HermesReview {
  ok: boolean;
  notes: string[];
  code?: string;
  context?: string;
}

/** Matches `src/registry/projects.py` ProjectRecord (JSON from /api/projects, /api/projects/{id}). */
export interface ProjectRecord {
  id: string;
  version: string;
  name: string;
  root: string;
  description: string;
  metadata: Record<string, unknown>;
}

/** From `GET /api/cursor/credentials-status` — never includes the full secret. */
export interface CursorWiredFor {
  models_list: boolean;
  cloud_agents_launch: boolean;
  missions_cloud_agent: boolean;
  ci_hooks: boolean;
  ci_hooks_note: string;
  dashboard_chat_uses_cursor: boolean;
  dashboard_chat_note: string;
}

/** Single entry from `GET /api/models` (composer catalog). */
export interface ModelCatalogItem {
  id: string;
  label: string;
  tag: string | null;
  tier: string | null;
  provider: string;
  description: string;
  supports_chat: boolean;
  disabled_reason?: string | null;
  cursor_slug?: string;
  openrouter_model?: string;
}

/** Response from `GET /api/tts/health` — TTS enabled and mounted (no network probe). */
export interface HamTtsHealthPayload {
  ok: boolean;
  /** When false, UI should treat TTS as unavailable (e.g. HAM_TTS_ENABLED=0 or older API). */
  available: boolean;
  reason?: string;
  generate_path?: string;
  engine?: string;
}

/** GET/PATCH `/api/workspace/voice-settings` — persisted TTS/STT preferences (HAM-native). */
export interface HamVoiceSettingsPayload {
  kind: "ham_voice_settings";
  settings: {
    tts: { enabled: boolean; provider: "edge"; voice: string };
    stt: { enabled: boolean; provider: "openai"; mode: "auto" | "live" | "record" };
  };
  capabilities: {
    tts: {
      available: boolean;
      providers: Array<{ id: string; label: string; available: boolean; reason?: string | null }>;
      voices: Array<{ id: string; label: string }>;
    };
    stt: {
      available: boolean;
      reason?: string | null;
      providers: Array<{ id: string; label: string; available: boolean; reason?: string | null }>;
    };
  };
}

export type HamVoiceSettingsPatch = {
  tts?: Partial<{ enabled: boolean; provider: "edge"; voice: string }>;
  stt?: Partial<{ enabled: boolean; provider: "openai"; mode: "auto" | "live" | "record" }>;
};

/** Response from `GET /api/models`. */
export interface ModelCatalogPayload {
  items: ModelCatalogItem[];
  source: string;
  gateway_mode: string;
  openrouter_chat_ready: boolean;
  /** True when HERMES_GATEWAY_MODE=http and HERMES_GATEWAY_BASE_URL is non-empty. */
  http_chat_ready?: boolean;
  /** True when dashboard chat can run (OpenRouter path ready, or HTTP gateway configured, or mock). */
  dashboard_chat_ready?: boolean;
  /** When `gateway_mode` is `http`: `HERMES_GATEWAY_MODEL` sent to Hermes (informational). */
  http_chat_model_primary?: string | null;
  /** When set on API: `HAM_CHAT_FALLBACK_MODEL` for HTTP retry (informational). */
  http_chat_model_fallback?: string | null;
}

/** Uses `dashboard_chat_ready` from API when present; otherwise infers from legacy fields. */
export function isDashboardChatGatewayReady(c: ModelCatalogPayload | null | undefined): boolean {
  if (!c) return false;
  if (typeof c.dashboard_chat_ready === "boolean") return c.dashboard_chat_ready;
  return Boolean(
    c.openrouter_chat_ready || c.http_chat_ready === true || c.gateway_mode === "mock",
  );
}

/**
 * Single-line status token for /chat: distinguishes Hermes HTTP vs mock dev vs other paths.
 * Uses fields from `GET /api/models` (same payload as the composer catalog).
 */
export function getChatGatewayReadinessToken(
  catalog: ModelCatalogPayload | null | undefined,
  options: { sending: boolean; catalogLoading: boolean },
): string {
  if (options.sending) return "SENDING";
  if (options.catalogLoading) return "GATEWAY_READY";
  if (!catalog) return "GATEWAY_OFFLINE";
  if (!isDashboardChatGatewayReady(catalog)) return "GATEWAY_OFFLINE";

  const mode = (catalog.gateway_mode || "").trim().toLowerCase();

  if (mode === "http") {
    return catalog.http_chat_ready === true ? "HTTP_READY" : "GATEWAY_OFFLINE";
  }
  if (mode === "mock") {
    return "MOCK_READY";
  }
  if (mode === "openrouter") {
    return catalog.openrouter_chat_ready ? "OPENROUTER_READY" : "GATEWAY_OFFLINE";
  }
  if (!mode || mode === "unknown") {
    return "GATEWAY_READY";
  }
  return "GATEWAY_READY";
}

/** From `GET /api/cursor/credentials-status` — never includes the full secret. */
export interface CursorCredentialsStatus {
  configured: boolean;
  source: 'ui' | 'env' | 'none';
  masked_preview: string | null;
  api_key_name: string | null;
  user_email: string | null;
  key_created_at: string | null;
  error: string | null;
  /** Server path where UI-saved key is stored (API host filesystem). */
  storage_path?: string;
  /** Set when `HAM_CURSOR_CREDENTIALS_FILE` overrides the default ~/.ham path. */
  storage_override_env?: string | null;
  /** What Ham uses this key for (backend truth). */
  wired_for?: CursorWiredFor;
}

/** Matches `context_engine_dashboard_payload()` JSON from `/api/context-engine`. */
export interface ContextEngineRoleSlice {
  instruction_budget_chars: number;
  max_diff_chars: number;
  rendered_chars: number;
}

export interface ContextEnginePayload {
  cwd: string;
  current_date: string;
  platform_info: string;
  file_count: number;
  instruction_file_count: number;
  instruction_files: { relative_path: string; scope: string }[];
  config_sources: { source: string; path: string }[];
  memory_heist_section: Record<string, unknown>;
  session_memory: {
    compact_max_tokens: number;
    compact_preserve: number;
    tool_prune_chars: number;
    tool_prune_placeholder: string;
  };
  module_defaults: {
    max_instruction_file_chars: number;
    max_total_instruction_chars: number;
    max_diff_chars: number;
  };
  roles: {
    architect: ContextEngineRoleSlice;
    commander: ContextEngineRoleSlice;
    critic: ContextEngineRoleSlice;
  };
  git: {
    status_chars: number;
    diff_chars: number;
    log_chars: number;
    has_repo: boolean;
  };
}

export interface BackendRecord {
  id: string;
  version: string;
  display_name?: string;
  metadata: Record<string, any>;
  is_default?: boolean;
}

/** Originating system / mission family for workspace activity (UI + optional API payloads). */
export type ActivityEventSource =
  | "cursor"
  | "cloud_agent"
  | "factory_ai"
  | "droid"
  | "ham"
  | "unknown";

export interface ActivityEvent {
  id: string;
  type: 'run_event' | 'warning' | 'persistence_warning' | 'review_outcome' | 'runtime_event';
  level: 'info' | 'warn' | 'error';
  message: string;
  timestamp: string;
  /** When set, identifies the system that produced the event. */
  source?: ActivityEventSource;
  metadata?: Record<string, any>;
}

export interface Agent {
  id: string;
  name: string;
  role: string;
  model: string;
  provider: string;
  status: 'Ready' | 'Needs Setup' | 'Working' | 'Offline';
  keyConnected: boolean;
  assignedTools: string[];
  description?: string;
  notes?: string;

  // Persona
  systemPrompt?: string;
  traits?: string[];
  knowledgeAreas?: string[];
  communicationStyle?: string;

  // Model Config
  reasoningDepth?: 'Fast' | 'Balanced' | 'Deep';
  contextSize?: string;

  // Behavior & Safety
  autonomyLevel?: 'Supervised' | 'Semi-Auto' | 'Full Auto';
  safeMode?: boolean;
  requireApprovalFor?: string[];
  allowlist?: string;
  denylist?: string;

  // Memory
  memoryEnabled?: boolean;
  memoryScope?: string;
  knowledgeSources?: { name: string; id: string }[];
}

export interface ApiKey {
  id: string;
  provider: string;
  maskedKey: string;
  status: 'Connected' | 'Error' | 'Inactive';
  assignedAgents: string[];
}

/** Public `GET /api/control-plane-runs` row (no digests or host paths beyond audit pointers). */
export interface ControlPlaneAuditRef {
  operator_audit_id?: string | null;
  provider_audit?: { sink: string; path?: string | null } | null;
}

export interface ControlPlaneRunPublic {
  ham_run_id: string;
  provider: string;
  action_kind: string;
  project_id: string;
  status: string;
  status_reason: string;
  external_id: string | null;
  workflow_id: string | null;
  summary: string | null;
  error_summary: string | null;
  created_at: string;
  updated_at: string;
  committed_at: string;
  started_at: string | null;
  finished_at: string | null;
  last_observed_at: string | null;
  last_provider_status: string | null;
  audit_ref: ControlPlaneAuditRef | null;
}
