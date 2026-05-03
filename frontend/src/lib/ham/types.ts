/** How HAM should relate to a Cursor Cloud Agent mission (Cloud Uplink / mission modal only). */
export type CloudMissionHandling = "direct" | "managed";

/** Defensive summary of Cursor agent + conversation for managed mode (real API fields only, no invention). */
export interface ManagedMissionSnapshot {
  status: string | null;
  progress: string | null;
  blocker: string | null;
  branchOrPr: string | null;
  updatedAt: string | null;
}

/** Deterministic, operator-facing read on polled Cloud Agent data (v1: rules only, no LLM). */
export type ManagedReviewSeverity = "info" | "success" | "warning" | "error";

/** How much concrete evidence supports the current assessment (drives conservatism + optional chat gating). */
export type ManagedReviewEvidenceLevel = "high" | "medium" | "low";

export interface ManagedMissionReview {
  severity: ManagedReviewSeverity;
  headline: string;
  details: string | null;
  nextStep: string | null;
  /** True when the assessment is for a terminal agent state (per `isCloudAgentTerminal`). */
  hasTerminalAssessment: boolean;
  evidenceLevel: ManagedReviewEvidenceLevel;
  /**
   * True when the payload is too thin for strong PR/blocker/handoff claims.
   * Panel may still show a compact notice; optional chat is suppressed.
   */
  limitedSignal: boolean;
}

export type MissionCheckpointState =
  | "queued"
  | "launched"
  | "running"
  | "blocked"
  | "pr_opened"
  | "completed"
  | "failed";

/** Deterministic deploy handoff assessment (Vercel hook is configured separately on the server). */
export type ManagedDeployReadiness = {
  ready: boolean;
  severity: "info" | "warning" | "error" | "success";
  headline: string;
  details: string | null;
  nextStep: string | null;
  prUrl: string | null;
  branch: string | null;
  repo: string | null;
  /** Human-readable target class; not a live deploy guarantee. */
  deploymentTarget: string | null;
};

export type ManagedDeployHandoffState =
  | "idle"
  | "not_ready"
  | "ready"
  | "triggering"
  | "hook_accepted"
  | "hook_failed"
  | "hook_not_configured";
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
  /** From OpenRouter /api/v1/models when available. */
  context_length?: number | null;
  /** Short pricing summary derived from provider metadata (no secrets). */
  pricing_display?: string | null;
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
  /** OpenRouter remote catalog integration (server-side fetch; never includes API keys). */
  openrouter_catalog?: {
    remote_models_fetched: boolean;
    remote_model_count: number;
    remote_fetch_failed: boolean;
    cache_ttl_sec: number;
  };
}

/** Creative-media generation flags (distinct from `image_input` / video attachment store-only). */
export interface GeneratedMediaImageGenerateResponse {
  generated_media_id: string;
  media_type: string;
  mime_type: string;
  status: string;
  /** Safe relative backend path (`/api/...`). */
  download_url: string;
  width?: number | null;
  height?: number | null;
  /** Phase 2G.3+: output used an uploaded attachment as reference input. */
  generated_from_reference_image?: boolean;
}

/** Async video generation request acknowledgement (server-owned job id only). */
export interface GeneratedMediaVideoGenerateResponse {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "canceled" | string;
}

/** Async media job status; successful video jobs resolve to a generated media artifact id. */
export interface HamMediaJobStatusResponse {
  job_id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "canceled" | string;
  generated_media_id?: string | null;
  /** Safe relative path when status is succeeded. */
  download_url?: string | null;
  media_type?: "video" | null;
  error?: { code?: string | null; message?: string | null } | null;
}

/** Sanitized artifact row from `GET /api/media/artifacts/{generated_media_id}`. */
export interface GeneratedMediaArtifactPublicMeta {
  generated_media_id: string;
  media_type: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  safe_display_name: string;
  prompt_excerpt: string;
  provider: string | null;
  model_id: string | null;
  width: number | null;
  height: number | null;
  download_url: string;
  /** Present when Phase 2G.3 reference generation was used. */
  generated_from_reference_image?: boolean;
}

/** Row from ``available_media_providers`` (Phase 2G.5+); server never includes URLs here. */
export interface MediaProviderAvailabilityRow {
  id: string;
  display_name: string;
  configured: boolean;
  supports_text_to_image: boolean;
  supports_image_to_image: boolean;
  supports_image_editing: boolean;
  supports_text_to_video: boolean;
  supports_image_to_video: boolean;
}

export interface ChatGenerationCapabilities {
  /** Phase 2G.5+: canonical backend selection after env coercion (`openrouter`, `unconfigured`, placeholders, …). */
  active_media_provider?: string;
  /** Phase 2G.5+: registry rows for product surfaces; conservative defaults when absent. */
  available_media_providers?: MediaProviderAvailabilityRow[];
  supports_text_to_image?: boolean;
  supports_text_to_video?: boolean;
  supports_image_generation: boolean;
  supports_image_editing: boolean;
  supports_image_to_image: boolean;
  supports_video_generation: boolean;
  supports_image_to_video: boolean;
  supports_video_editing: boolean;
  supports_async_media_jobs: boolean;
  supports_reference_images: boolean;
  generated_media_max_duration_sec: number | null;
  generated_media_max_resolution: string | null;
  generated_media_output_types: string[];
  media_generation_provider: string | null;
  video_generation_provider?: string | null;
  media_generation_notes: string[];
  /** Phase 2G.7: optional opaque profile (`local_gpu_workstation`, …) when provider is comfyui; sanitized server-side. */
  comfy_worker_profile?: string;
  /** Phase 2G.5+: same strings as ``media_generation_notes`` when API mirrors; no secrets or URLs. */
  provider_notes?: string[];
}

/** Safe subset from `GET /api/chat/capabilities` — no secrets or storage paths. */
export interface ChatCapabilitiesPayload {
  model: { id: string; display_name: string };
  capabilities: {
    text_chat: boolean;
    image_input: boolean;
    document_text_context: boolean;
    native_pdf: boolean;
    audio_input: boolean;
    video_input: boolean;
    pdf_export: boolean;
    tool_use: boolean;
  };
  /** Present from Phase 2G.1+ when API returns `generation`; clients should treat conservative defaults when absent. */
  generation?: ChatGenerationCapabilities;
  limitations: string[];
  document_context_mode: string;
  notes: string;
  /** Present when API exposes chat context meters feature gate. */
  context_meters_enabled?: boolean;
}

/** GET /api/chat/context-meters — safe aggregates only (no message text). */
export type ChatContextMeterColor = "green" | "amber" | "red" | "gray";

export interface ChatContextThisTurnMeter {
  fill_ratio: number;
  color: ChatContextMeterColor;
  unit: "estimate_tokens";
  used: number;
  limit: number;
  model_id: string | null;
}

export interface ChatContextWorkspaceMeter {
  fill_ratio: number;
  color: ChatContextMeterColor;
  bottleneck_role: string | null;
  source: "local" | "cloud" | "unavailable";
  used: number;
  limit: number;
  unit: "chars";
}

export interface ChatContextThreadMeter {
  fill_ratio: number;
  color: ChatContextMeterColor;
  approx_transcript_chars: number;
  thread_budget_chars: number;
  unit: "chars_estimate";
}

export interface ChatContextMetersPayload {
  enabled: boolean;
  this_turn: ChatContextThisTurnMeter | null;
  workspace: ChatContextWorkspaceMeter | null;
  thread: ChatContextThreadMeter | null;
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
  /** Present when snapshot is from ``GET /api/workspace/context-snapshot`` (local API + configured root). */
  context_source?: "local" | "cloud";
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
