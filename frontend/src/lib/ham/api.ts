import type { HamChatUserContentV1, HamChatUserContentV2 } from "./chatUserContent";
import type {
  ContextEnginePayload,
  CursorCredentialsStatus,
  HamTtsHealthPayload,
  HamVoiceSettingsPayload,
  HamVoiceSettingsPatch,
  ModelCatalogPayload,
  ProjectRecord,
} from "./types";
import type { HermesGatewaySnapshot } from "./hermesGateway";
import { getRegisteredClerkSessionToken } from "./clerkSession";
import { getHamDesktopConfig } from "./desktopConfig";

function normalizeApiBaseOrigin(raw: string): string {
  let base = raw.replace(/\/+$/, "");
  if (base.toLowerCase().endsWith("/api")) {
    base = base.slice(0, -4).replace(/\/+$/, "");
  }
  return base;
}

/**
 * Ham API **origin** for `fetch` (scheme + host, optional port). Paths already include `/api/...`.
 * - **Desktop (Electron):** non-empty `window.__HAM_DESKTOP_CONFIG__.apiBase` wins at runtime (no rebuild per environment).
 * - **Dev (default):** `""` → same origin as Vite; `/api/*` is proxied to FastAPI (see `vite.config.ts`).
 * - **Override:** `VITE_HAM_API_BASE` = e.g. `https://ham-api-xxxxx.run.app` — **no** `/api` suffix (that would produce `/api/api/...` and HTTP 404).
 */
export function getApiBase(): string {
  const desktop = getHamDesktopConfig();
  const desktopRaw = desktop?.apiBase?.trim();
  if (desktopRaw) {
    return normalizeApiBaseOrigin(desktopRaw);
  }
  const raw = (import.meta.env.VITE_HAM_API_BASE as string | undefined)?.trim();
  if (raw) {
    return normalizeApiBaseOrigin(raw);
  }
  if (import.meta.env.DEV) return "";
  // Production build without VITE_HAM_API_BASE → browser would call localhost and "Failed to fetch".
  throw new Error(
    "VITE_HAM_API_BASE was not set when this site was built. In Vercel: Settings → Environment Variables → add VITE_HAM_API_BASE = your Cloud Run URL (no trailing slash, no /api suffix). Enable it for Production and Preview, then redeploy. For the desktop app, set HAM_DESKTOP_API_BASE or ham-desktop-config.json (see desktop/README.md).",
  );
}

/** Build an absolute or same-origin path for the Ham API (Vite dev uses relative `/api/...` + proxy). */
export function apiUrl(path: string): string {
  const base = getApiBase();
  const p = path.startsWith("/") ? path : `/${path}`;
  return base ? `${base}${p}` : p;
}

/** If `Authorization` is unset and the dashboard has a Clerk publishable key, attach the session JWT. */
export async function mergeClerkAuthBearerIfNeeded(headers: Headers): Promise<void> {
  if (headers.has("Authorization")) return;
  const pk = (import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined)?.trim();
  if (!pk) return;
  const tok = (await getRegisteredClerkSessionToken())?.trim();
  if (tok) headers.set("Authorization", `Bearer ${tok}`);
}

/**
 * Clerk session on `Authorization` when present; otherwise legacy `Authorization: Bearer` for HAM secrets.
 * When both are needed, sets `X-Ham-Operator-Authorization` for the HAM token.
 */
export async function applyHamOperatorSecretHeaders(headers: Headers, hamBearerToken: string): Promise<void> {
  await mergeClerkAuthBearerIfNeeded(headers);
  const ham = hamBearerToken.trim();
  if (!ham) return;
  if (headers.has("Authorization")) {
    headers.set("X-Ham-Operator-Authorization", `Bearer ${ham}`);
  } else {
    headers.set("Authorization", `Bearer ${ham}`);
  }
}

/**
 * Same-origin Ham API `fetch` with optional Clerk `Authorization` (skips if already set).
 * Returns the raw `Response` — use `.json()` for JSON, `.blob()` for binary (e.g. `POST /api/tts/generate` → `audio/mpeg`).
 */
export async function hamApiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const url = apiUrl(path);
  const headers = new Headers(init.headers as HeadersInit | undefined);
  await mergeClerkAuthBearerIfNeeded(headers);
  return fetch(url, { ...init, headers });
}

/** Multipart upload for workspace chat; returns an opaque `attachment_id` (blob stored server-side). */
export async function postChatUploadAttachment(file: File): Promise<{
  attachment_id: string;
  filename: string;
  mime: string;
  size: number;
  kind: string;
}> {
  const body = new FormData();
  body.append("file", file, file.name);
  const res = await hamApiFetch("/api/chat/attachments", { method: "POST", body });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const j = (await res.json()) as { detail?: { error?: { message?: string } } };
      const m = j?.detail?.error?.message;
      if (m) detail = m;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<{
    attachment_id: string;
    filename: string;
    mime: string;
    size: number;
    kind: string;
  }>;
}

async function readFastApiDetail(res: Response): Promise<string | null> {
  try {
    const j = (await res.json()) as { detail?: unknown };
    const d = j?.detail;
    if (typeof d === "string") return d;
    if (typeof d === "object" && d !== null && "detail" in d) {
      return String((d as { detail?: string }).detail ?? "");
    }
  } catch {
    /* ignore */
  }
  return null;
}

/** Unified composer catalog (OpenRouter chat rows + Cursor slugs, honest flags). */
export async function fetchModelsCatalog(): Promise<ModelCatalogPayload> {
  const res = await hamApiFetch("/api/models");
  if (!res.ok) {
    throw new Error(`models catalog: HTTP ${res.status}`);
  }
  return res.json() as Promise<ModelCatalogPayload>;
}

/** GET /api/tts/health — whether TTS routes are enabled on this API (no Microsoft network call). */
export async function fetchTtsHealth(): Promise<HamTtsHealthPayload> {
  const res = await hamApiFetch("/api/tts/health");
  if (!res.ok) {
    throw new Error(`TTS health: HTTP ${res.status}`);
  }
  return res.json() as Promise<HamTtsHealthPayload>;
}

/** GET /api/workspace/voice-settings — persisted voice prefs + capabilities. */
export async function fetchVoiceSettings(): Promise<HamVoiceSettingsPayload> {
  const res = await hamApiFetch("/api/workspace/voice-settings");
  if (!res.ok) {
    throw new Error(`voice settings: HTTP ${res.status}`);
  }
  return res.json() as Promise<HamVoiceSettingsPayload>;
}

/** PATCH /api/workspace/voice-settings — partial updates; returns normalized saved settings. */
export async function patchVoiceSettings(patch: HamVoiceSettingsPatch): Promise<HamVoiceSettingsPayload> {
  const res = await hamApiFetch("/api/workspace/voice-settings", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const j = (await res.json()) as { detail?: unknown };
      if (j.detail !== undefined) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<HamVoiceSettingsPayload>;
}

/** GET /api/hermes-hub — gateway + Hermes skills capabilities; no fake Hermes inventory. */
export interface HermesHubDashboardChat {
  active_upstream: string;
  short_label: string;
  summary: string;
}

export interface HermesHubScopeNotes {
  in_ham_today: string[];
  not_in_ham_yet: string[];
}

export interface HermesHubSnapshot {
  kind: "ham_hermes_control_plane_snapshot";
  gateway_mode: string;
  openrouter_chat_ready: boolean;
  http_chat_ready?: boolean;
  dashboard_chat_ready?: boolean;
  dashboard_chat: HermesHubDashboardChat;
  skills_capabilities: HermesSkillsCapabilities;
  scope_notes: HermesHubScopeNotes;
}

export async function fetchHermesHubSnapshot(): Promise<HermesHubSnapshot> {
  const res = await hamApiFetch("/api/hermes-hub");
  if (!res.ok) {
    throw new Error(`hermes-hub: HTTP ${res.status}`);
  }
  return res.json() as Promise<HermesHubSnapshot>;
}

export type { HermesGatewaySnapshot } from "./hermesGateway";

/** GET /api/hermes-gateway/snapshot — broker-backed command center (Path B). */
export async function fetchHermesGatewaySnapshot(opts?: {
  projectId?: string;
  refresh?: boolean;
}): Promise<HermesGatewaySnapshot> {
  const q = new URLSearchParams();
  if (opts?.projectId?.trim()) q.set("project_id", opts.projectId.trim());
  if (opts?.refresh) q.set("refresh", "true");
  const suffix = q.toString() ? `?${q}` : "";
  const res = await hamApiFetch(`/api/hermes-gateway/snapshot${suffix}`);
  if (!res.ok) {
    throw new Error(`hermes-gateway/snapshot: HTTP ${res.status}`);
  }
  return res.json() as Promise<HermesGatewaySnapshot>;
}

/** GET /api/hermes-gateway/capabilities — static capability manifest. */
export async function fetchHermesGatewayCapabilities(): Promise<Record<string, unknown>> {
  const res = await hamApiFetch("/api/hermes-gateway/capabilities");
  if (!res.ok) {
    throw new Error(`hermes-gateway/capabilities: HTTP ${res.status}`);
  }
  return res.json() as Promise<Record<string, unknown>>;
}

/** GET /api/hermes-runtime/inventory — read-only Hermes CLI + sanitized config (local/co-located). */
export interface HermesRuntimeInventory {
  kind: "ham_hermes_runtime_inventory";
  mode: string;
  available: boolean;
  source: {
    hermes_binary: string;
    hermes_home: string;
    colocated: boolean;
  };
  tools: {
    status: string;
    summary_text?: string;
    toolsets: string[];
    config_toolsets?: string[];
    warning?: string;
    raw_redacted: string;
  };
  plugins: {
    status: string;
    items: Array<{ text: string }>;
    raw_redacted: string;
  };
  mcp: {
    status: string;
    servers: Array<{ text?: string; name?: string; transport?: string }>;
    raw_redacted: string;
  };
  config: Record<string, unknown>;
  skills: {
    status: string;
    catalog_count: number;
    static_catalog: boolean;
    installed_note?: string;
  };
  status: {
    status_all: { status: string; raw_redacted: string };
  };
  warnings: string[];
}

export async function fetchHermesRuntimeInventory(): Promise<HermesRuntimeInventory> {
  const res = await hamApiFetch("/api/hermes-runtime/inventory");
  if (!res.ok) {
    throw new Error(`hermes-runtime/inventory: HTTP ${res.status}`);
  }
  return res.json() as Promise<HermesRuntimeInventory>;
}

/** GET /api/browser/policy — HAM Playwright policy snapshot (not a remote Hermes service). */
export interface BrowserRuntimePolicySnapshot {
  runtime_host: string;
  session_ownership: string;
  screenshot_transport: string;
  streaming_supported: boolean;
  cursor_embedding_supported: boolean;
  supported_live_transports: string[];
  webrtc_enabled: boolean;
  allow_private_network: boolean;
  allowed_domains: string[];
  blocked_domains: string[];
  session_ttl_seconds: number;
  max_actions_per_minute: number;
  max_screenshot_bytes: number;
}

export async function fetchBrowserRuntimePolicy(): Promise<BrowserRuntimePolicySnapshot> {
  const res = await hamApiFetch("/api/browser/policy");
  if (!res.ok) {
    throw new Error(`browser policy: HTTP ${res.status}`);
  }
  return res.json() as Promise<BrowserRuntimePolicySnapshot>;
}

export async function fetchContextEngine(): Promise<ContextEnginePayload> {
  const res = await hamApiFetch("/api/context-engine");
  if (!res.ok) {
    const hint =
      res.status === 404
        ? " (server has no /api/context-engine — use latest `src.api.server` and restart uvicorn; in dev use Vite proxy + run FastAPI on the proxy target port)"
        : "";
    throw new Error(`context-engine: HTTP ${res.status}${hint}`);
  }
  return res.json() as Promise<ContextEnginePayload>;
}

export async function fetchCursorCredentialsStatus(): Promise<CursorCredentialsStatus> {
  const res = await hamApiFetch("/api/cursor/credentials-status");
  if (!res.ok) {
    throw new Error(`cursor credentials: HTTP ${res.status}`);
  }
  return res.json() as Promise<CursorCredentialsStatus>;
}

/** Proxy to Cursor `GET /v0/models` — uses the same team key as Settings. */
export async function fetchCursorModels(): Promise<unknown> {
  const res = await hamApiFetch("/api/cursor/models");
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return res.json() as Promise<unknown>;
}

/** Save team Cursor API key server-side (~/.ham/cursor_credentials.json). Verifies via Cursor /v0/me. */
export async function saveCursorApiKey(apiKey: string): Promise<void> {
  const headers = new Headers({ "Content-Type": "application/json" });
  await mergeClerkAuthBearerIfNeeded(headers);
  const res = await fetch(apiUrl("/api/cursor/credentials"), {
    method: "POST",
    headers,
    body: JSON.stringify({ api_key: apiKey.trim() }),
  });
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
}

/** Remove UI-saved key; falls back to CURSOR_API_KEY env on the API host. */
export async function clearSavedCursorApiKey(): Promise<void> {
  const headers = new Headers();
  await mergeClerkAuthBearerIfNeeded(headers);
  const res = await fetch(apiUrl("/api/cursor/credentials"), { method: "DELETE", headers });
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
}

/**
 * `POST /api/cursor/agents/{id}/sync` — Cursor GET + observe mission; returns `ManagedMission` JSON only.
 * @throws Error on HTTP error; message includes server detail when available.
 */
export async function postCursorAgentSync(agentId: string): Promise<ManagedMissionRow> {
  const res = await hamApiFetch(`/api/cursor/agents/${encodeURIComponent(agentId)}/sync`, {
    method: "POST",
  });
  if (res.status === 404) {
    throw new Error("No managed mission for this Cloud Agent. Try after a managed launch is recorded.");
  }
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(shortenHamApiErrorMessage(msg));
  }
  return res.json() as Promise<ManagedMissionRow>;
}

/** Proxy `GET /v0/agents/{id}` — Cloud Agent status and metadata. */
export async function fetchCursorAgent(agentId: string): Promise<Record<string, unknown>> {
  const res = await hamApiFetch(`/api/cursor/agents/${encodeURIComponent(agentId)}`);
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return res.json() as Promise<Record<string, unknown>>;
}

/** Proxy `GET /v0/agents/{id}/conversation`. */
export async function fetchCursorAgentConversation(
  agentId: string,
): Promise<Record<string, unknown>> {
  const res = await hamApiFetch(`/api/cursor/agents/${encodeURIComponent(agentId)}/conversation`);
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return res.json() as Promise<Record<string, unknown>>;
}

/** Body for Ham → Cursor `POST /v0/agents` (see `LaunchCloudAgentBody` on server). */
export interface LaunchCursorAgentRequest {
  prompt_text: string;
  repository: string;
  ref?: string | null;
  model?: string;
  auto_create_pr?: boolean;
  branch_name?: string | null;
  /** HAM-only audit; not forwarded to Cursor. */
  mission_handling?: "direct" | "managed";
  /** When set, managed missions snapshot deploy approval from this registered project. */
  project_id?: string | null;
}

/** Turn FastAPI / proxy error text into a short UI string (single line, capped). */
export function shortenHamApiErrorMessage(raw: string, maxLen = 120): string {
  const oneLine = raw.replace(/\s+/g, " ").trim();
  if (oneLine.length <= maxLen) return oneLine;
  return `${oneLine.slice(0, maxLen - 1)}…`;
}

/** `POST /api/cursor/agents/launch` — Cursor Cloud Agent create; returns Cursor JSON (incl. `id` when successful). */
export async function launchCursorAgent(
  body: LaunchCursorAgentRequest,
): Promise<Record<string, unknown>> {
  const res = await fetch(apiUrl("/api/cursor/agents/launch"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      prompt_text: body.prompt_text.trim(),
      repository: body.repository.trim(),
      ref: body.ref?.trim() || undefined,
      model: (body.model ?? "default").trim() || "default",
      auto_create_pr: Boolean(body.auto_create_pr),
      branch_name: body.branch_name?.trim() || undefined,
      mission_handling: body.mission_handling,
      ...(body.project_id?.trim() ? { project_id: body.project_id.trim() } : {}),
    }),
  });
  if (!res.ok) {
    const detail = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(shortenHamApiErrorMessage(detail));
  }
  return res.json() as Promise<Record<string, unknown>>;
}

export function cloudAgentIdFromLaunchResponse(payload: Record<string, unknown>): string | null {
  const id = payload.id;
  return typeof id === "string" && id.trim() ? id.trim() : null;
}

export type VercelHookMapping = {
  repo_key: string | null;
  mapping_tier: "mapped" | "global" | "unavailable";
  hook_configured: boolean;
  deploy_hook_env_name: string | null;
  used_global_hook_fallback: boolean;
  fail_closed: boolean;
  message: string;
  map_load_error: string | null;
};

export type ManagedDeployHookStatusPayload = {
  configured: boolean;
  vercel_mapping?: VercelHookMapping;
};

/** Without agent_id, reports global deploy hook only. With agent_id, per-repo map resolution (no secrets). */
export async function fetchManagedDeployHookStatus(
  agentId?: string | null,
): Promise<ManagedDeployHookStatusPayload> {
  const q = agentId?.trim() ? new URLSearchParams({ agent_id: agentId.trim() }) : null;
  const res = await hamApiFetch(q ? `/api/cursor/managed/deploy-hook?${q.toString()}` : "/api/cursor/managed/deploy-hook");
  if (!res.ok) return { configured: false };
  return res.json() as Promise<ManagedDeployHookStatusPayload>;
}

/** Whether HAM has a server-side Vercel deploy hook URL (legacy: global only). */
export async function fetchManagedDeployHookConfigured(): Promise<boolean> {
  const p = await fetchManagedDeployHookStatus();
  return Boolean(p.configured);
}

export type ManagedDeployHookResult = {
  ok: boolean;
  outcome: string;
  message: string;
  status_code?: number;
  vercel_mapping?: VercelHookMapping;
};

export type ManagedDeployApprovalPolicy = "off" | "audit" | "soft" | "hard";

export type ManagedDeployApprovalStatusPayload = {
  kind: "managed_deploy_approval_status";
  policy: ManagedDeployApprovalPolicy;
  mission_registry_id: string | null;
  latest_approval: Record<string, unknown> | null;
  deploy_hook_would_allow: boolean;
};

export async function fetchManagedDeployApprovalStatus(
  agentId: string,
): Promise<ManagedDeployApprovalStatusPayload | null> {
  const q = new URLSearchParams({ agent_id: agentId.trim() });
  const res = await hamApiFetch(`/api/cursor/managed/deploy-approval?${q.toString()}`);
  if (!res.ok) {
    return null;
  }
  return res.json() as Promise<ManagedDeployApprovalStatusPayload>;
}

/** Server-backed managed Cloud Agent missions (newest first). */
export type ManagedMissionRow = {
  kind?: string;
  mission_registry_id?: string;
  cursor_agent_id?: string;
  mission_lifecycle?: string;
  /** Create-time snapshot from project default (managed missions). */
  mission_deploy_approval_mode?: "off" | "audit" | "soft" | "hard";
  repo_key?: string | null;
  repository_observed?: string | null;
  cursor_status_last_observed?: string | null;
  status_reason_last_observed?: string | null;
  last_server_observed_at?: string;
  updated_at?: string;
};

/** Single mission row for the current Cloud Agent, when the server has recorded a managed mission. */
export async function fetchManagedMissionForAgent(
  agentId: string,
): Promise<ManagedMissionRow | null> {
  const q = new URLSearchParams({
    cursor_agent_id: agentId.trim(),
    limit: "5",
  });
  const res = await hamApiFetch(`/api/cursor/managed/missions?${q.toString()}`);
  if (!res.ok) {
    return null;
  }
  const j = (await res.json()) as { missions?: ManagedMissionRow[] };
  const rows = Array.isArray(j.missions) ? j.missions : [];
  return rows[0] ?? null;
}

export async function fetchManagedMissionsList(limit = 40): Promise<ManagedMissionRow[]> {
  const res = await hamApiFetch(`/api/cursor/managed/missions?limit=${limit}`);
  if (!res.ok) {
    return [];
  }
  const j = (await res.json()) as { missions?: ManagedMissionRow[] };
  return Array.isArray(j.missions) ? j.missions : [];
}

export async function postManagedDeployApprovalDecision(body: {
  agent_id: string;
  state: "approved" | "denied";
  mission_registry_id?: string | null;
  note?: string | null;
  override?: boolean;
  override_justification?: string | null;
  source?: "operator_ui" | "api" | "script";
}): Promise<{ kind: string; approval: Record<string, unknown> }> {
  const res = await hamApiFetch("/api/cursor/managed/deploy-approval", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      agent_id: body.agent_id.trim(),
      state: body.state,
      mission_registry_id: body.mission_registry_id ?? null,
      note: body.note ?? null,
      override: Boolean(body.override),
      override_justification: body.override_justification ?? null,
      source: body.source ?? "operator_ui",
    }),
  });
  if (!res.ok) {
    const detail = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(detail);
  }
  return res.json() as Promise<{ kind: string; approval: Record<string, unknown> }>;
}

/** GET /api/cursor/managed/vercel/deploy-status — server-side Vercel poll + match confidence. */
export type VercelManagedDeployState =
  | "not_configured"
  | "not_observed"
  | "pending"
  | "building"
  | "ready"
  | "error"
  | "canceled"
  | "unknown";

export type VercelListMapping = {
  repo_key: string | null;
  mapping_tier: "mapped" | "global" | "unavailable";
  project_id_used: string | null;
  team_id_used: string | null;
  use_global_project_fallback: boolean;
  message: string;
  map_load_error: string | null;
};

export type VercelManagedDeployStatus = {
  checked_at: string;
  vercel: { configured: boolean };
  state: VercelManagedDeployState;
  match_confidence: "high" | "medium" | "low" | null;
  match_reason: string | null;
  message: string;
  deployment: {
    id: string | null;
    url: string | null;
    vercel_state: string | null;
    created_at: string | null;
  } | null;
  api_error: string | null;
  vercel_mapping?: VercelListMapping;
};

export async function fetchVercelManagedDeployStatus(agentId: string): Promise<VercelManagedDeployStatus> {
  const q = new URLSearchParams({ agent_id: agentId.trim() });
  const res = await hamApiFetch(`/api/cursor/managed/vercel/deploy-status?${q.toString()}`);
  if (!res.ok) {
    const detail = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(detail);
  }
  return res.json() as Promise<VercelManagedDeployStatus>;
}

/** GET /api/cursor/managed/vercel/post-deploy-validation — server-side HTTP probe (deployment URL from Vercel match only). */
export type PostDeployValidationState = "not_attempted" | "pending" | "passed" | "failed" | "inconclusive";

export type VercelPostDeployValidationPayload = {
  state: PostDeployValidationState;
  checked_at: string;
  url_probed: string | null;
  final_url?: string | null | undefined;
  http_status: string | null;
  match_confidence: "high" | "medium" | "low" | null;
  reason_code: string | null;
  message: string;
};

export type VercelPostDeployValidationResponse = {
  vercel_mapping?: VercelListMapping;
  deploy_ref: {
    state: string;
    match_confidence: "high" | "medium" | "low" | null;
    match_reason: string | null;
    deployment: { url: string | null; vercel_state: string | null };
  } | null;
  post_deploy_validation: VercelPostDeployValidationPayload;
};

export async function fetchVercelPostDeployValidation(
  agentId: string,
  options?: { force?: boolean },
): Promise<VercelPostDeployValidationResponse> {
  const q = new URLSearchParams({ agent_id: agentId.trim() });
  if (options?.force) q.set("force", "true");
  const res = await hamApiFetch(`/api/cursor/managed/vercel/post-deploy-validation?${q.toString()}`);
  if (!res.ok) {
    const detail = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(detail);
  }
  return res.json() as Promise<VercelPostDeployValidationResponse>;
}

/** POST Vercel deploy hook via HAM (hook URL stays on server). */
export async function postManagedDeployHook(agentId: string): Promise<ManagedDeployHookResult> {
  const res = await hamApiFetch("/api/cursor/managed/deploy-hook", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agent_id: agentId.trim() }),
  });
  if (res.status === 503) {
    const detail = (await readFastApiDetail(res)) ?? "Deploy hook is not configured on the API host.";
    return {
      ok: false,
      outcome: "not_configured",
      message: typeof detail === "string" ? detail : "Deploy hook is not configured.",
    };
  }
  if (res.status === 403) {
    const detail =
      (await readFastApiDetail(res)) ??
      "Deploy blocked: managed deploy approval policy is hard and the latest decision is not approved.";
    return {
      ok: false,
      outcome: "approval_required",
      message: detail,
      status_code: 403,
    };
  }
  const j = (await res.json()) as Record<string, unknown> & { vercel_mapping?: VercelHookMapping };
  return {
    ok: Boolean(j.ok),
    outcome: typeof j.outcome === "string" ? j.outcome : "unknown",
    message: typeof j.message === "string" ? j.message : "Unknown response",
    status_code: typeof j.status_code === "number" ? j.status_code : undefined,
    vercel_mapping: j.vercel_mapping,
  };
}

export interface BrowserRuntimeState {
  session_id: string;
  status: "ready" | "busy" | "error";
  last_error: string | null;
  current_url: string;
  title: string;
  viewport: {
    width: number;
    height: number;
  };
  created_at: string;
  updated_at: string;
  ownership: "pane_owner_key";
  runtime_host: "ham_api_local";
  screenshot_transport: "binary_png_endpoint";
  streaming_supported: boolean;
  cursor_embedding_supported: boolean;
  stream_state: BrowserStreamState;
  /** When true, direct mutating /api/browser/* actions return 409; use Browser Operator proposals. */
  operator_mode_required?: boolean;
}

export interface BrowserStreamState {
  status: "disconnected" | "connecting" | "live" | "reconnecting" | "degraded" | "error";
  mode: string;
  requested_transport: string;
  last_error: string | null;
}

export interface BrowserSessionCreateRequest {
  owner_key: string;
  viewport_width?: number;
  viewport_height?: number;
  /** When true, session requires proposal + approve for mutating browser actions. */
  operator_mode?: boolean;
}

/** FastAPI detail when a direct browser action is blocked in operator mode. */
export const BROWSER_OPERATOR_APPROVAL_REQUIRED_DETAIL = "OPERATOR_MODE_REQUIRES_APPROVAL";

export type BrowserProposalState =
  | "proposed"
  | "approved"
  | "denied"
  | "executed"
  | "failed"
  | "expired";

export type BrowserProposalActionType =
  | "browser.navigate"
  | "browser.click_xy"
  | "browser.scroll"
  | "browser.key"
  | "browser.type"
  | "browser.reset";

export interface BrowserProposalActionPayload {
  action_type: BrowserProposalActionType;
  url?: string | null;
  selector?: string | null;
  text?: string | null;
  clear_first?: boolean | null;
  x?: number | null;
  y?: number | null;
  delta_x?: number | null;
  delta_y?: number | null;
  key?: string | null;
}

export interface BrowserProposerActor {
  kind?: "operator" | "agent" | "chat" | "unknown";
  label?: string | null;
}

export interface BrowserActionProposal {
  kind?: "browser_action_proposal";
  proposal_id: string;
  session_id: string;
  owner_key: string;
  state: BrowserProposalState;
  action: BrowserProposalActionPayload;
  proposer: BrowserProposerActor;
  created_at: string;
  expires_at: string;
  decided_at?: string | null;
  decision_note?: string | null;
  executed_at?: string | null;
  result_status?: "ok" | "error" | null;
  result_last_error?: string | null;
}

export interface BrowserOperatorPolicy {
  kind: "browser_operator_policy";
  approval_only: boolean;
  allowed_action_types: string[];
  ttl_seconds: number;
  max_pending_per_session: number;
  dispatch_mode: string;
  header_unlock_supported: boolean;
}

export async function fetchBrowserOperatorPolicy(): Promise<BrowserOperatorPolicy | null> {
  const res = await hamApiFetch("/api/browser-operator/policy");
  if (!res.ok) {
    return null;
  }
  return res.json() as Promise<BrowserOperatorPolicy>;
}

export async function createBrowserProposal(body: {
  session_id: string;
  owner_key: string;
  action: BrowserProposalActionPayload;
  proposer?: BrowserProposerActor | null;
}): Promise<BrowserActionProposal> {
  const res = await hamApiFetch("/api/browser-operator/proposals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: body.session_id.trim(),
      owner_key: body.owner_key.trim(),
      action: body.action,
      proposer: body.proposer ?? undefined,
    }),
  });
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return res.json() as Promise<BrowserActionProposal>;
}

export async function listBrowserProposals(
  sessionId: string,
  ownerKey: string,
  limit = 64,
): Promise<BrowserActionProposal[]> {
  const q = new URLSearchParams({
    session_id: sessionId.trim(),
    owner_key: ownerKey.trim(),
    limit: String(limit),
  });
  const res = await hamApiFetch(`/api/browser-operator/proposals?${q.toString()}`);
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
  const j = (await res.json()) as { items?: BrowserActionProposal[] };
  return Array.isArray(j.items) ? j.items : [];
}

export async function fetchBrowserProposal(
  proposalId: string,
  ownerKey: string,
): Promise<BrowserActionProposal> {
  const q = new URLSearchParams({ owner_key: ownerKey.trim() }).toString();
  const res = await hamApiFetch(
    `/api/browser-operator/proposals/${encodeURIComponent(proposalId)}?${q}`,
  );
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return res.json() as Promise<BrowserActionProposal>;
}

export async function approveBrowserProposal(
  proposalId: string,
  ownerKey: string,
  note?: string | null,
): Promise<BrowserActionProposal> {
  const res = await hamApiFetch(
    `/api/browser-operator/proposals/${encodeURIComponent(proposalId)}/approve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ owner_key: ownerKey.trim(), note: note?.trim() || undefined }),
    },
  );
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return res.json() as Promise<BrowserActionProposal>;
}

export async function denyBrowserProposal(
  proposalId: string,
  ownerKey: string,
  note?: string | null,
): Promise<BrowserActionProposal> {
  const res = await hamApiFetch(
    `/api/browser-operator/proposals/${encodeURIComponent(proposalId)}/deny`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ owner_key: ownerKey.trim(), note: note?.trim() || undefined }),
    },
  );
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return res.json() as Promise<BrowserActionProposal>;
}

/** True if error message indicates direct action was blocked (operator mode). */
export function isBrowserOperatorApprovalRequiredError(message: string): boolean {
  return message.includes(BROWSER_OPERATOR_APPROVAL_REQUIRED_DETAIL);
}

/** Use ``hamApiFetch`` (not raw ``fetch``) so production sends Clerk session JWT like other API calls. */
async function browserRuntimeJson<T>(path: string, body?: unknown, method = "POST"): Promise<T> {
  const res = await hamApiFetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body == null ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export async function createBrowserSession(
  body: BrowserSessionCreateRequest,
): Promise<BrowserRuntimeState> {
  return browserRuntimeJson<BrowserRuntimeState>("/api/browser/sessions", body, "POST");
}

export async function getBrowserSessionState(
  sessionId: string,
  ownerKey: string,
): Promise<BrowserRuntimeState> {
  const q = new URLSearchParams({ owner_key: ownerKey.trim() }).toString();
  const res = await hamApiFetch(`/api/browser/sessions/${encodeURIComponent(sessionId)}?${q}`);
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return res.json() as Promise<BrowserRuntimeState>;
}

export async function navigateBrowserSession(
  sessionId: string,
  ownerKey: string,
  url: string,
): Promise<BrowserRuntimeState> {
  return browserRuntimeJson<BrowserRuntimeState>(
    `/api/browser/sessions/${encodeURIComponent(sessionId)}/navigate`,
    { owner_key: ownerKey, url },
    "POST",
  );
}

export async function clickBrowserSession(
  sessionId: string,
  ownerKey: string,
  selector: string,
): Promise<BrowserRuntimeState> {
  return browserRuntimeJson<BrowserRuntimeState>(
    `/api/browser/sessions/${encodeURIComponent(sessionId)}/actions/click`,
    { owner_key: ownerKey, selector },
    "POST",
  );
}

export async function typeBrowserSession(
  sessionId: string,
  ownerKey: string,
  selector: string,
  text: string,
  clearFirst = true,
): Promise<BrowserRuntimeState> {
  return browserRuntimeJson<BrowserRuntimeState>(
    `/api/browser/sessions/${encodeURIComponent(sessionId)}/actions/type`,
    { owner_key: ownerKey, selector, text, clear_first: clearFirst },
    "POST",
  );
}

export async function resetBrowserSession(
  sessionId: string,
  ownerKey: string,
): Promise<BrowserRuntimeState> {
  return browserRuntimeJson<BrowserRuntimeState>(
    `/api/browser/sessions/${encodeURIComponent(sessionId)}/reset`,
    { owner_key: ownerKey },
    "POST",
  );
}

export async function closeBrowserSession(sessionId: string, ownerKey: string): Promise<void> {
  const q = new URLSearchParams({ owner_key: ownerKey.trim() }).toString();
  const res = await hamApiFetch(`/api/browser/sessions/${encodeURIComponent(sessionId)}?${q}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
}

export async function captureBrowserScreenshot(
  sessionId: string,
  ownerKey: string,
): Promise<Blob> {
  const res = await hamApiFetch(
    `/api/browser/sessions/${encodeURIComponent(sessionId)}/screenshot`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ owner_key: ownerKey }),
    },
  );
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return res.blob();
}

export async function clickBrowserSessionXY(
  sessionId: string,
  ownerKey: string,
  x: number,
  y: number,
  button: "left" | "right" | "middle" = "left",
): Promise<BrowserRuntimeState> {
  return browserRuntimeJson<BrowserRuntimeState>(
    `/api/browser/sessions/${encodeURIComponent(sessionId)}/actions/click-xy`,
    { owner_key: ownerKey, x, y, button },
    "POST",
  );
}

export async function scrollBrowserSession(
  sessionId: string,
  ownerKey: string,
  deltaX: number,
  deltaY: number,
): Promise<BrowserRuntimeState> {
  return browserRuntimeJson<BrowserRuntimeState>(
    `/api/browser/sessions/${encodeURIComponent(sessionId)}/actions/scroll`,
    { owner_key: ownerKey, delta_x: deltaX, delta_y: deltaY },
    "POST",
  );
}

export async function sendBrowserSessionKey(
  sessionId: string,
  ownerKey: string,
  key: string,
): Promise<BrowserRuntimeState> {
  return browserRuntimeJson<BrowserRuntimeState>(
    `/api/browser/sessions/${encodeURIComponent(sessionId)}/actions/key`,
    { owner_key: ownerKey, key },
    "POST",
  );
}

export async function startBrowserLiveStream(
  sessionId: string,
  ownerKey: string,
  requestedTransport = "webrtc",
): Promise<BrowserStreamState> {
  return browserRuntimeJson<BrowserStreamState>(
    `/api/browser/sessions/${encodeURIComponent(sessionId)}/stream/start`,
    { owner_key: ownerKey, requested_transport: requestedTransport },
    "POST",
  );
}

export async function getBrowserLiveStreamState(
  sessionId: string,
  ownerKey: string,
): Promise<BrowserStreamState> {
  const q = new URLSearchParams({ owner_key: ownerKey.trim() }).toString();
  const res = await hamApiFetch(
    `/api/browser/sessions/${encodeURIComponent(sessionId)}/stream/state?${q}`,
  );
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return res.json() as Promise<BrowserStreamState>;
}

export async function stopBrowserLiveStream(
  sessionId: string,
  ownerKey: string,
): Promise<BrowserStreamState> {
  return browserRuntimeJson<BrowserStreamState>(
    `/api/browser/sessions/${encodeURIComponent(sessionId)}/stream/stop`,
    { owner_key: ownerKey },
    "POST",
  );
}

/** Proxy `POST /v0/agents/{id}/followup`. */
export async function postCursorAgentFollowup(
  agentId: string,
  promptText: string,
): Promise<Record<string, unknown>> {
  const headers = new Headers({ "Content-Type": "application/json" });
  await mergeClerkAuthBearerIfNeeded(headers);
  const res = await fetch(apiUrl(`/api/cursor/agents/${encodeURIComponent(agentId)}/followup`), {
    method: "POST",
    headers,
    body: JSON.stringify({ prompt_text: promptText }),
  });
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return res.json() as Promise<Record<string, unknown>>;
}

export async function fetchProjectContextEngine(
  projectId: string,
): Promise<ContextEnginePayload> {
  const res = await hamApiFetch(`/api/projects/${encodeURIComponent(projectId)}/context-engine`);
  if (!res.ok) {
    throw new Error(`project context-engine: HTTP ${res.status}`);
  }
  return res.json() as Promise<ContextEnginePayload>;
}

/** Ham-native chat DTOs (matches `src/api/chat.py`). */
export type HamChatRole = "user" | "assistant" | "system";

/** Inbound only: server accepts structured screenshot payloads; responses use string `content` only. */
export interface HamChatRequestMessage {
  role: HamChatRole;
  content: string | HamChatUserContentV1 | HamChatUserContentV2;
}

export interface HamChatMessage {
  role: HamChatRole;
  content: string;
}

/** HAM-owned metadata when Agent Builder guidance was applied to the chat turn (not a Hermes runtime profile). */
export interface HamChatActiveAgentMeta {
  profile_id: string;
  profile_name: string;
  skills_requested: number;
  skills_resolved: number;
  skills_skipped_catalog_miss?: number;
  guidance_applied: boolean;
}

export interface HamChatRequest {
  session_id?: string;
  messages: HamChatRequestMessage[];
  client_request_id?: string;
  /** When true (default), API injects `.cursor/skills` summary into system context for intent routing. */
  include_operator_skills?: boolean;
  /** When true (default), API injects `.cursor/rules/subagent-*.mdc` index (review charters). */
  include_operator_subagents?: boolean;
  /** When true (default), model may emit `HAM_UI_ACTIONS_JSON`; response includes `actions` for the UI. */
  enable_ui_actions?: boolean;
  /** Registered HAM project id — when set, server may inject Agent Builder active-agent guidance (catalog descriptors only). */
  project_id?: string;
  /** When true (default), append compact HAM active-agent guidance from project settings. */
  include_active_agent_guidance?: boolean;
  model_id?: string;
  workbench_mode?: "ask" | "plan" | "agent";
  worker?: string;
  max_mode?: boolean;
  /** Server-side operator (projects, agents, runs). */
  enable_operator?: boolean;
  /** Structured confirm/apply/register/launch (see API `ChatOperatorPayload` / `src/ham/chat_operator.py`). */
  operator?: HamChatOperatorPayload | null;
  /** Execution routing hint: auto/browser/machine/chat. */
  execution_mode_preference?: "auto" | "browser" | "machine" | "chat";
  /** Client environment hint for routing policy. */
  execution_environment?: "web" | "desktop" | "unknown";
}

/** Matches server `ChatOperatorPayload` (subset used by the dashboard; extra fields are ignored if unset). */
export type HamChatOperatorPhase =
  | "apply_settings"
  | "register_project"
  | "launch_run"
  | "droid_preview"
  | "droid_launch"
  | "cursor_agent_preview"
  | "cursor_agent_launch"
  | "cursor_agent_status";

export interface HamChatOperatorPayload {
  phase?: HamChatOperatorPhase | null;
  confirmed?: boolean;
  project_id?: string | null;
  changes?: Record<string, unknown> | null;
  base_revision?: string | null;
  name?: string | null;
  root?: string | null;
  description?: string | null;
  prompt?: string | null;
  profile_id?: string | null;
  droid_workflow_id?: string | null;
  droid_user_prompt?: string | null;
  droid_proposal_digest?: string | null;
  droid_base_revision?: string | null;
  cursor_task_prompt?: string | null;
  cursor_repository?: string | null;
  cursor_ref?: string | null;
  cursor_model?: string;
  cursor_auto_create_pr?: boolean;
  cursor_branch_name?: string | null;
  cursor_expected_deliverable?: string | null;
  cursor_proposal_digest?: string | null;
  cursor_base_revision?: string | null;
  cursor_mission_handling?: "direct" | "managed" | null;
  cursor_agent_id?: string | null;
}

/** Structured UI actions from `POST /api/chat` (server-validated). */
export type HamUiAction =
  | { type: "navigate"; path: string }
  | { type: "open_settings"; tab?: string | null }
  | {
      type: "toast";
      level: "info" | "success" | "warning" | "error";
      message: string;
    }
  | { type: "toggle_control_panel"; open?: boolean | null };

export interface HamOperatorResult {
  handled: boolean;
  intent?: string | null;
  ok: boolean;
  blocking_reason?: string | null;
  pending_apply?: Record<string, unknown> | null;
  pending_launch?: Record<string, unknown> | null;
  pending_register?: Record<string, unknown> | null;
  pending_droid?: Record<string, unknown> | null;
  pending_cursor_agent?: Record<string, unknown> | null;
  harness_advisory?: Record<string, unknown> | null;
  data?: Record<string, unknown>;
}

export interface HamChatExecutionMode {
  requested_mode: "auto" | "browser" | "machine" | "chat";
  selected_mode: "browser" | "machine" | "chat";
  auto_selected: boolean;
  environment: "web" | "desktop" | "unknown";
  browser_available: boolean;
  local_machine_available: boolean;
  browser_adapter?: "playwright" | "chromium" | null;
  reason: string;
}

export interface HamChatResponse {
  session_id: string;
  messages: HamChatMessage[];
  actions: HamUiAction[];
  active_agent?: HamChatActiveAgentMeta | null;
  operator_result?: HamOperatorResult | null;
  execution_mode?: HamChatExecutionMode | null;
  /** Present on terminal `done` when the model gateway failed after retries; safe text is in `messages`. */
  gateway_error?: { code: string };
}

/**
 * Interactive assistant turn via Ham API (server may use a gateway adapter; browser only sees Ham).
 */
function messageFromFastApiDetail(detail: unknown): string | null {
  if (detail == null) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((x) =>
        typeof x === "object" && x !== null && "msg" in x
          ? String((x as { msg: string }).msg)
          : "",
      )
      .filter(Boolean);
    return parts.length ? parts.join("; ") : null;
  }
  if (typeof detail === "object" && detail !== null && "error" in detail) {
    const e = (detail as { error?: { message?: string } }).error;
    return e?.message ?? null;
  }
  return null;
}

/** FastAPI `HTTPException` detail shape `{ "error": { "code", "message" } }`. */
export function fastApiStructuredErrorCode(detail: unknown): string | null {
  if (typeof detail !== "object" || detail === null || !("error" in detail)) return null;
  const e = (detail as { error?: { code?: string } }).error;
  return typeof e?.code === "string" ? e.code : null;
}

/** Ham API rejected the Clerk identity (email/domain allowlist). */
export class HamAccessRestrictedError extends Error {
  readonly code = "HAM_EMAIL_RESTRICTION";

  constructor(message: string) {
    super(message);
    this.name = "HamAccessRestrictedError";
  }
}

/* ─── Chat session history ────────────────────────────────────────── */

export type ChatSessionSummary = {
  session_id: string;
  preview: string;
  turn_count: number;
  created_at: string | null;
};

export type ChatSessionDetail = {
  session_id: string;
  messages: HamChatMessage[];
  created_at: string | null;
};

export type ChatSessionTurn = {
  role: "user" | "assistant";
  content: string;
};

/** List past chat sessions (newest first). */
export async function fetchChatSessions(
  limit = 50,
  offset = 0,
): Promise<{ sessions: ChatSessionSummary[] }> {
  const path = `/api/chat/sessions?limit=${limit}&offset=${offset}`;
  const res = await hamApiFetch(path);
  if (!res.ok) {
    const target = apiUrl(path);
    throw new Error(`Failed to list chat sessions (HTTP ${res.status}) via ${target}. Retry, or verify desktop API base.`);
  }
  return (await res.json()) as { sessions: ChatSessionSummary[] };
}

/** Fetch full message history for a single chat session. */
export async function fetchChatSession(sessionId: string): Promise<ChatSessionDetail> {
  const path = `/api/chat/sessions/${encodeURIComponent(sessionId)}`;
  const res = await hamApiFetch(path);
  if (!res.ok) {
    if (res.status === 404) throw new Error("Session not found");
    throw new Error(`Failed to fetch chat session (HTTP ${res.status}) via ${apiUrl(path)}.`);
  }
  return (await res.json()) as ChatSessionDetail;
}

/** Create an empty chat session id for explicit turn persistence (desktop local-control turns). */
export async function createChatSession(): Promise<{ session_id: string; created_at: string | null }> {
  const path = "/api/chat/sessions";
  const res = await hamApiFetch(path, { method: "POST" });
  if (!res.ok) {
    throw new Error(`Failed to create chat session (HTTP ${res.status}) via ${apiUrl(path)}.`);
  }
  return (await res.json()) as { session_id: string; created_at: string | null };
}

/** Append already-finalized user/assistant turns to an existing chat session. */
export async function appendChatSessionTurns(
  sessionId: string,
  turns: ChatSessionTurn[],
): Promise<{ session_id: string; messages: HamChatMessage[] }> {
  const path = `/api/chat/sessions/${encodeURIComponent(sessionId)}/turns`;
  const res = await hamApiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ turns }),
  });
  if (!res.ok) {
    throw new Error(`Failed to append chat turns (HTTP ${res.status}) via ${apiUrl(path)}.`);
  }
  return (await res.json()) as { session_id: string; messages: HamChatMessage[] };
}

export async function postChat(body: HamChatRequest): Promise<HamChatResponse> {
  const url = apiUrl("/api/chat");
  const payload = {
    ...body,
    include_operator_skills: body.include_operator_skills ?? true,
    include_operator_subagents: body.include_operator_subagents ?? true,
    enable_ui_actions: body.enable_ui_actions ?? true,
    include_active_agent_guidance: body.include_active_agent_guidance ?? true,
  };
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (cause) {
    const hint =
      typeof cause === "object" && cause !== null && "message" in cause
        ? String((cause as Error).message)
        : "Network error";
    throw new Error(
      `${hint}. Check VITE_HAM_API_BASE (redeploy after changing). If the API is up but chat still fails, the browser origin may be blocked by CORS: add it to HAM_CORS_ORIGINS or set HAM_CORS_ORIGIN_REGEX on the API (see docs/examples/ham-api-cloud-run-env.yaml).`,
    );
  }
  if (!res.ok) {
    let msg = `Chat request failed (HTTP ${res.status})`;
    try {
      const j = (await res.json()) as { detail?: unknown };
      if (fastApiStructuredErrorCode(j?.detail) === "HAM_EMAIL_RESTRICTION") {
        throw new HamAccessRestrictedError(
          messageFromFastApiDetail(j?.detail) ?? "Access restricted for this Ham deployment.",
        );
      }
      const parsed = messageFromFastApiDetail(j?.detail);
      if (parsed) msg = parsed;
    } catch (err) {
      if (err instanceof HamAccessRestrictedError) throw err;
      /* ignore JSON parse */
    }
    throw new Error(msg);
  }
  const data = (await res.json()) as HamChatResponse;
  if (!Array.isArray(data.actions)) {
    data.actions = [];
  }
  return data;
}

/** One NDJSON line from `POST /api/chat/stream`. */
export type HamChatStreamEvent =
  | { type: "session"; session_id: string }
  | { type: "delta"; text: string }
  | {
      type: "done";
      session_id: string;
      messages: HamChatMessage[];
      actions?: HamUiAction[];
      active_agent?: HamChatActiveAgentMeta | null;
      operator_result?: HamOperatorResult | null;
      execution_mode?: HamChatExecutionMode | null;
      /** Structured signal when the assistant turn ended in a gateway failure (safe copy in `messages`). */
      gateway_error?: { code: string };
    }
  | { type: "error"; code: string; message: string };

const streamNetworkHint =
  "Check VITE_HAM_API_BASE (redeploy after changing). If the API is up but chat still fails, the browser origin may be blocked by CORS: add it to HAM_CORS_ORIGINS or set HAM_CORS_ORIGIN_REGEX on the API (see docs/examples/ham-api-cloud-run-env.yaml).";

/** When Clerk is enabled: Clerk session JWT as `Authorization`; HAM operator secrets on `X-Ham-Operator-Authorization`. */
export type HamChatStreamAuth =
  | string
  | {
      sessionToken?: string | null;
      hamOperatorToken?: string | null;
    };

function applyChatStreamAuthHeaders(
  headers: Record<string, string>,
  authorization?: HamChatStreamAuth,
) {
  if (authorization == null) return;
  if (typeof authorization === "string") {
    const raw = authorization.trim();
    if (!raw) return;
    headers.Authorization = raw.startsWith("Bearer ") ? raw : `Bearer ${raw}`;
    return;
  }
  const s = authorization.sessionToken?.trim();
  const h = authorization.hamOperatorToken?.trim();
  if (s) headers.Authorization = `Bearer ${s}`;
  if (h) {
    headers["X-Ham-Operator-Authorization"] = h.startsWith("Bearer ") ? h : `Bearer ${h}`;
  }
}

/**
 * Streaming assistant turn (NDJSON). Tokens arrive as `delta` events; final transcript in `done`.
 */
export async function postChatStream(
  body: HamChatRequest,
  callbacks: {
    onSession?: (sessionId: string) => void;
    onDelta?: (text: string) => void;
  } = {},
  authorization?: HamChatStreamAuth,
): Promise<HamChatResponse> {
  const url = apiUrl("/api/chat/stream");
  const payload = {
    ...body,
    include_operator_skills: body.include_operator_skills ?? true,
    include_operator_subagents: body.include_operator_subagents ?? true,
    enable_ui_actions: body.enable_ui_actions ?? true,
    include_active_agent_guidance: body.include_active_agent_guidance ?? true,
    enable_operator: body.enable_operator ?? true,
  };
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/x-ndjson, application/json",
  };
  applyChatStreamAuthHeaders(headers, authorization);
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
    });
  } catch (cause) {
    const hint =
      typeof cause === "object" && cause !== null && "message" in cause
        ? String((cause as Error).message)
        : "Network error";
    throw new Error(`${hint}. ${streamNetworkHint}`);
  }
  if (!res.ok) {
    let msg = `Chat stream failed (HTTP ${res.status})`;
    try {
      const j = (await res.json()) as { detail?: unknown };
      if (fastApiStructuredErrorCode(j?.detail) === "HAM_EMAIL_RESTRICTION") {
        throw new HamAccessRestrictedError(
          messageFromFastApiDetail(j?.detail) ?? "Access restricted for this Ham deployment.",
        );
      }
      const parsed = messageFromFastApiDetail(j?.detail);
      if (parsed) msg = parsed;
    } catch (err) {
      if (err instanceof HamAccessRestrictedError) throw err;
      /* ignore JSON parse */
    }
    throw new Error(msg);
  }
  if (!res.body) {
    throw new Error(`No response body. ${streamNetworkHint}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: HamChatResponse | null = null;

  const handleLine = (line: string) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    let ev: HamChatStreamEvent;
    try {
      ev = JSON.parse(trimmed) as HamChatStreamEvent;
    } catch {
      throw new Error("Invalid NDJSON line from chat stream");
    }
    if (ev.type === "session") {
      callbacks.onSession?.(ev.session_id);
      return;
    }
    if (ev.type === "delta") {
      callbacks.onDelta?.(ev.text);
      return;
    }
    if (ev.type === "done") {
      final = {
        session_id: ev.session_id,
        messages: ev.messages,
        actions: Array.isArray(ev.actions) ? ev.actions : [],
        active_agent: ev.active_agent ?? undefined,
        operator_result: ev.operator_result ?? undefined,
        execution_mode: ev.execution_mode ?? undefined,
        ...(ev.gateway_error ? { gateway_error: ev.gateway_error } : {}),
      };
      return;
    }
    if (ev.type === "error") {
      throw new Error(ev.message || ev.code || "Chat stream error");
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      handleLine(line);
    }
  }
  buffer += decoder.decode();
  for (const line of buffer.split("\n")) {
    if (line.trim()) {
      handleLine(line);
    }
  }

  if (!final) {
    throw new Error("Chat stream ended without a done event");
  }
  return final;
}

/**
 * Multipart voice clip → server-side OpenAI transcription; appends returned text in the UI.
 */
export async function postChatTranscribe(audio: Blob, filename: string = "dictation.webm"): Promise<string> {
  const fd = new FormData();
  fd.append("file", audio, filename);
  const headers = new Headers();
  await mergeClerkAuthBearerIfNeeded(headers);
  const res = await fetch(apiUrl("/api/chat/transcribe"), { method: "POST", body: fd, headers });
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = (await res.json()) as { detail?: unknown };
    } catch {
      detail = undefined;
    }
    const d = typeof detail === "object" && detail !== null ? (detail as { detail?: unknown }).detail : undefined;
    if (fastApiStructuredErrorCode(d) === "HAM_EMAIL_RESTRICTION") {
      throw new HamAccessRestrictedError(
        messageFromFastApiDetail(d) ?? "Access restricted for this Ham deployment.",
      );
    }
    const errCode = fastApiStructuredErrorCode(d);
    if (
      res.status === 503 &&
      (errCode === "TRANSCRIPTION_NOT_CONFIGURED" || errCode === "TRANSCRIPTION_PROVIDER_REJECTED")
    ) {
      throw new Error(
        "Transcription failed. Check HAM transcription configuration.",
      );
    }
    if (res.status === 502 && errCode === "TRANSCRIPTION_UPSTREAM_FAILED") {
      throw new Error("Transcription failed. Check HAM transcription configuration.");
    }
    const msg =
      messageFromFastApiDetail(d) ?? `Transcription failed (HTTP ${res.status}).`;
    throw new Error(msg);
  }
  const data = (await res.json()) as { text?: string };
  return typeof data.text === "string" ? data.text : "";
}

// --- Hermes runtime skills (Phase 1: read-only catalog + probe; not Cursor operator skills) ---

export type HermesSkillsMode = "local" | "remote_only" | "unsupported";

export interface HermesSkillCatalogEntry {
  catalog_id: string;
  display_name: string;
  summary: string;
  trust_level: string;
  source_kind: string;
  source_ref: string;
  version_pin: string;
  content_hash_sha256: string;
  platforms: string[];
  required_environment_variables: Array<{ name: string; description?: string }>;
  config_keys: string[];
  has_scripts: boolean;
  installable_by_default: boolean;
}

export interface HermesSkillDetailBlock {
  provenance_note: string;
  warnings: string[];
  manifest_files: string[];
}

export interface HermesSkillCatalogEntryDetail extends HermesSkillCatalogEntry {
  detail: HermesSkillDetailBlock;
}

export interface HermesSkillsCatalogResponse {
  kind: "hermes_runtime_skills_catalog";
  schema_version: number;
  count: number;
  entries: HermesSkillCatalogEntry[];
  /** Present when manifest was generated from a pinned hermes-agent commit. */
  upstream?: { repo: string; commit: string };
  catalog_note?: string;
}

export interface HermesSkillsCapabilities {
  kind: "hermes_skills_capabilities";
  hermes_home_detected: boolean;
  hermes_home_path_hint: string | null;
  shared_target_supported: boolean;
  profile_target_supported: boolean;
  profile_listing_supported: boolean;
  mode: HermesSkillsMode;
  warnings: string[];
  profile_count?: number;
  /** Phase 2a: local Hermes home + source pin + not remote_only — shared runtime install preview/apply is meaningful. */
  shared_runtime_install_supported?: boolean;
  /** Server has HAM_SKILLS_WRITE_TOKEN (apply may work). */
  skills_apply_writes_enabled?: boolean;
}

export interface HermesSkillTarget {
  kind: "shared" | "hermes_profile";
  id: string;
  label: string;
  available: boolean;
  notes?: string;
}

export interface HermesSkillsTargetsResponse {
  kind: "hermes_skills_targets";
  targets: HermesSkillTarget[];
  capabilities_summary: {
    mode?: HermesSkillsMode;
    hermes_home_detected?: boolean;
    profile_listing_supported?: boolean;
  };
  warnings: string[];
}

/** GET /api/hermes-skills/installed — live CLI observation joined to vendored catalog (read-only). */
export type HermesSkillsInstalledStatus =
  | "ok"
  | "remote_only"
  | "unavailable"
  | "error"
  | "parse_degraded";

export type HermesSkillLiveResolution = "linked" | "live_only" | "unknown";

export interface HermesSkillLiveInstallation {
  name: string;
  category: string;
  hermes_source: string;
  hermes_trust: string;
  catalog_id: string | null;
  resolution: HermesSkillLiveResolution;
}

export interface HermesSkillsInstalledResponse {
  kind: "hermes_skills_live_overlay";
  status: HermesSkillsInstalledStatus;
  cli_source: string;
  live_count: number;
  linked_count: number;
  live_only_count: number;
  unknown_count: number;
  catalog_only_count: number;
  installations: HermesSkillLiveInstallation[];
  warnings: string[];
  raw_redacted: string;
}

export async function fetchHermesSkillsCatalog(): Promise<HermesSkillsCatalogResponse> {
  const res = await hamApiFetch("/api/hermes-skills/catalog");
  if (!res.ok) {
    throw new Error(`hermes-skills/catalog: HTTP ${res.status}`);
  }
  return res.json() as Promise<HermesSkillsCatalogResponse>;
}

export async function fetchHermesSkillDetail(
  catalogId: string,
): Promise<{ kind: string; entry: HermesSkillCatalogEntryDetail }> {
  const res = await hamApiFetch(`/api/hermes-skills/catalog/${encodeURIComponent(catalogId)}`);
  if (!res.ok) {
    throw new Error(`hermes-skills/catalog/${catalogId}: HTTP ${res.status}`);
  }
  return res.json() as Promise<{ kind: string; entry: HermesSkillCatalogEntryDetail }>;
}

export async function fetchHermesSkillsCapabilities(): Promise<HermesSkillsCapabilities> {
  const res = await hamApiFetch("/api/hermes-skills/capabilities");
  if (!res.ok) {
    throw new Error(`hermes-skills/capabilities: HTTP ${res.status}`);
  }
  return res.json() as Promise<HermesSkillsCapabilities>;
}

export async function fetchHermesSkillsTargets(): Promise<HermesSkillsTargetsResponse> {
  const res = await hamApiFetch("/api/hermes-skills/targets");
  if (!res.ok) {
    throw new Error(`hermes-skills/targets: HTTP ${res.status}`);
  }
  return res.json() as Promise<HermesSkillsTargetsResponse>;
}

export async function fetchHermesSkillsInstalled(): Promise<HermesSkillsInstalledResponse> {
  const res = await hamApiFetch("/api/hermes-skills/installed");
  if (!res.ok) {
    throw new Error(`hermes-skills/installed: HTTP ${res.status}`);
  }
  return res.json() as Promise<HermesSkillsInstalledResponse>;
}

/** Phase 2a — Hermes runtime skill install (shared target only; not Cursor operator skills). */
export interface HermesSkillsInstallPreviewResponse {
  kind: "hermes_skills_install_preview";
  catalog_id: string;
  target: { kind: "shared" };
  client_proposal_id?: string | null;
  paths_touched: string[];
  config_path: string;
  config_diff: { before: string[]; after: string[]; added: string[] };
  config_snippet_after: { skills: { external_dirs: string[] } };
  warnings: string[];
  proposal_digest: string;
  base_revision: string;
  bundle_dest: string;
  entry: Record<string, unknown>;
}

export interface HermesSkillsInstallApplyResponse {
  kind: "hermes_skills_install_apply";
  audit_id: string;
  backup_id: string;
  catalog_id: string;
  target: { kind: "shared" };
  installed_paths: string[];
  new_revision: string;
  warnings: string[];
  client_proposal_id?: string | null;
}

export async function fetchHermesSkillsInstallWriteStatus(): Promise<{
  writes_enabled: boolean;
}> {
  const res = await hamApiFetch("/api/hermes-skills/install/write-status");
  if (!res.ok) {
    throw new Error(`hermes-skills/install/write-status: HTTP ${res.status}`);
  }
  return res.json() as Promise<{ writes_enabled: boolean }>;
}

export async function postHermesSkillsInstallPreview(body: {
  catalog_id: string;
  target: { kind: "shared" };
  client_proposal_id?: string | null;
}): Promise<HermesSkillsInstallPreviewResponse> {
  const headers = new Headers({ "Content-Type": "application/json" });
  await mergeClerkAuthBearerIfNeeded(headers);
  const res = await fetch(apiUrl("/api/hermes-skills/install/preview"), {
    method: "POST",
    headers,
    body: JSON.stringify({
      catalog_id: body.catalog_id,
      target: body.target,
      client_proposal_id: body.client_proposal_id ?? null,
    }),
  });
  if (!res.ok) {
    const msg = await detailMessageFromResponse(res);
    throw new Error(msg || `hermes-skills install preview failed (HTTP ${res.status})`);
  }
  return res.json() as Promise<HermesSkillsInstallPreviewResponse>;
}

export async function postHermesSkillsInstallApply(
  body: {
    catalog_id: string;
    target: { kind: "shared" };
    proposal_digest: string;
    base_revision: string;
    client_proposal_id?: string | null;
  },
  bearerToken: string,
): Promise<HermesSkillsInstallApplyResponse> {
  const headers = new Headers({ "Content-Type": "application/json" });
  await applyHamOperatorSecretHeaders(headers, bearerToken);
  const res = await fetch(apiUrl("/api/hermes-skills/install/apply"), {
    method: "POST",
    headers,
    body: JSON.stringify({
      catalog_id: body.catalog_id,
      target: body.target,
      proposal_digest: body.proposal_digest,
      base_revision: body.base_revision,
      client_proposal_id: body.client_proposal_id ?? null,
    }),
  });
  if (!res.ok) {
    const msg = await detailMessageFromResponse(res);
    throw new Error(msg || `hermes-skills install apply failed (HTTP ${res.status})`);
  }
  return res.json() as Promise<HermesSkillsInstallApplyResponse>;
}

// --- Capability Directory (Phase 1 — read-only; no apply from UI) ---

export interface CapabilityDirectoryProvenance {
  source_kind: string;
  registry_revision?: string;
  note?: string;
  [key: string]: unknown;
}

export interface CapabilityDirectorySurface {
  route: string;
  label: string;
  api?: string;
}

export interface CapabilityDirectoryRecord {
  id: string;
  schema_version: string;
  kind: "atomic_capability" | "bundle" | "profile_template";
  display_name: string;
  summary: string;
  description: string;
  trust_tier: string;
  provenance: CapabilityDirectoryProvenance;
  version: string;
  required_backends: string[];
  capabilities: string[];
  skills: string[];
  tools_policy: Record<string, unknown>;
  mcp_policy: Record<string, unknown>;
  model_policy: Record<string, unknown>;
  memory_policy: Record<string, unknown>;
  surfaces: CapabilityDirectorySurface[];
  mutability: string;
  preview_available: boolean;
  apply_available: boolean;
  risks: string[];
  evidence_expectations: string[];
  tags: string[];
  /** Optional autonomy tier labels (e.g. Computer Control Pack). */
  permission_tiers?: Record<string, string>;
}

export interface CapabilityDirectoryIndexResponse {
  kind: "capability_directory_index";
  schema_version: string;
  registry_id: string;
  mutation_policy: string;
  apply_available_globally: boolean;
  no_execution_notice?: string;
  counts: {
    capabilities: number;
    bundles: number;
    profile_templates: number;
  };
  trust_tier_counts: Record<string, number>;
  endpoints: Record<string, string>;
  registry_note?: string | null;
}

export interface CapabilityDirectoryCapabilitiesResponse {
  kind: "capability_directory_capabilities";
  schema_version: string;
  registry_id: string;
  mutation_policy: string;
  apply_available_globally: boolean;
  count: number;
  capabilities: CapabilityDirectoryRecord[];
}

export interface CapabilityDirectoryBundlesResponse {
  kind: "capability_directory_bundles";
  schema_version: string;
  registry_id: string;
  mutation_policy: string;
  apply_available_globally: boolean;
  count: number;
  bundles: CapabilityDirectoryRecord[];
}

export interface CapabilityDirectoryBundleResponse {
  kind: "capability_directory_bundle";
  schema_version: string;
  registry_id: string;
  mutation_policy: string;
  apply_available_globally: boolean;
  no_execution_notice?: string;
  bundle: CapabilityDirectoryRecord;
}

export async function fetchCapabilityDirectoryIndex(): Promise<CapabilityDirectoryIndexResponse> {
  const res = await hamApiFetch("/api/capability-directory");
  if (!res.ok) {
    throw new Error(`capability-directory: HTTP ${res.status}`);
  }
  return res.json() as Promise<CapabilityDirectoryIndexResponse>;
}

export async function fetchCapabilityDirectoryCapabilities(): Promise<CapabilityDirectoryCapabilitiesResponse> {
  const res = await hamApiFetch("/api/capability-directory/capabilities");
  if (!res.ok) {
    throw new Error(`capability-directory/capabilities: HTTP ${res.status}`);
  }
  return res.json() as Promise<CapabilityDirectoryCapabilitiesResponse>;
}

export async function fetchCapabilityDirectoryBundles(): Promise<CapabilityDirectoryBundlesResponse> {
  const res = await hamApiFetch("/api/capability-directory/bundles");
  if (!res.ok) {
    throw new Error(`capability-directory/bundles: HTTP ${res.status}`);
  }
  return res.json() as Promise<CapabilityDirectoryBundlesResponse>;
}

export async function fetchCapabilityDirectoryBundle(
  bundleId: string,
): Promise<CapabilityDirectoryBundleResponse> {
  const res = await hamApiFetch(
    `/api/capability-directory/bundles/${encodeURIComponent(bundleId)}`,
  );
  if (!res.ok) {
    const msg = await detailMessageFromResponse(res);
    throw new Error(
      msg || `capability-directory/bundles/${bundleId}: HTTP ${res.status}`,
    );
  }
  return res.json() as Promise<CapabilityDirectoryBundleResponse>;
}

// --- Capability library (saved catalog refs; token-gated writes) ---

export interface CapabilityLibraryWriteStatus {
  kind: "ham_capability_library_write_status";
  writes_enabled: boolean;
}

export interface CapabilityLibraryEntryRow {
  ref: string;
  notes: string;
  user_order: number;
  created_at: string;
  updated_at: string;
}

export interface CapabilityLibraryResponse {
  kind: "ham_capability_library";
  schema_version: string;
  project_root: string;
  revision: string;
  entries: CapabilityLibraryEntryRow[];
}

export interface CapabilityLibraryAggregateItem {
  ref: string;
  source: string;
  in_library: boolean;
  library: {
    notes: string;
    user_order: number;
    created_at: string;
    updated_at: string;
  };
  in_catalog?: boolean;
  in_directory?: boolean;
  hermes?: {
    catalog_id?: string;
    display_name?: string;
    summary?: string;
    trust_level?: string;
    installed_summary?: { status?: string; linked?: boolean };
  };
  capability_directory?: {
    kind?: string;
    id?: string;
    display_name?: string;
    trust_tier?: string;
  };
}

export interface CapabilityLibraryAggregateResponse {
  kind: "ham_capability_library_aggregate";
  schema_version: string;
  project_root: string;
  revision: string;
  entry_count: number;
  items: CapabilityLibraryAggregateItem[];
}

export async function fetchCapabilityLibraryWriteStatus(): Promise<CapabilityLibraryWriteStatus> {
  const res = await hamApiFetch("/api/capability-library/write-status");
  if (!res.ok) {
    throw new Error(`capability-library write-status: HTTP ${res.status}`);
  }
  return res.json() as Promise<CapabilityLibraryWriteStatus>;
}

export async function fetchCapabilityLibrary(projectId: string): Promise<CapabilityLibraryResponse> {
  const res = await hamApiFetch(
    `/api/capability-library/library?project_id=${encodeURIComponent(projectId)}`,
  );
  if (!res.ok) {
    const msg = await detailMessageFromResponse(res);
    throw new Error(msg || `capability-library: HTTP ${res.status}`);
  }
  return res.json() as Promise<CapabilityLibraryResponse>;
}

export async function fetchCapabilityLibraryAggregate(
  projectId: string,
): Promise<CapabilityLibraryAggregateResponse> {
  const res = await hamApiFetch(
    `/api/capability-library/aggregate?project_id=${encodeURIComponent(projectId)}`,
  );
  if (!res.ok) {
    const msg = await detailMessageFromResponse(res);
    throw new Error(msg || `capability-library aggregate: HTTP ${res.status}`);
  }
  return res.json() as Promise<CapabilityLibraryAggregateResponse>;
}

export async function postCapabilityLibrarySave(
  projectId: string,
  body: { ref: string; notes: string; base_revision: string },
  writeToken: string,
): Promise<{ new_revision: string; audit_id: string }> {
  const headers = new Headers({ "Content-Type": "application/json" });
  await applyHamOperatorSecretHeaders(headers, writeToken);
  const res = await fetch(
    apiUrl(`/api/capability-library/save?project_id=${encodeURIComponent(projectId)}`),
    { method: "POST", headers, body: JSON.stringify(body) },
  );
  if (!res.ok) {
    const msg = await detailMessageFromResponse(res);
    throw new Error(msg || `capability-library save: HTTP ${res.status}`);
  }
  return res.json() as Promise<{ new_revision: string; audit_id: string }>;
}

export async function postCapabilityLibraryRemove(
  projectId: string,
  body: { ref: string; base_revision: string },
  writeToken: string,
): Promise<{ new_revision: string; audit_id: string }> {
  const headers = new Headers({ "Content-Type": "application/json" });
  await applyHamOperatorSecretHeaders(headers, writeToken);
  const res = await fetch(
    apiUrl(`/api/capability-library/remove?project_id=${encodeURIComponent(projectId)}`),
    { method: "POST", headers, body: JSON.stringify(body) },
  );
  if (!res.ok) {
    const msg = await detailMessageFromResponse(res);
    throw new Error(msg || `capability-library remove: HTTP ${res.status}`);
  }
  return res.json() as Promise<{ new_revision: string; audit_id: string }>;
}

// --- Allowlisted project settings (v1 control plane) ---

export interface HamSettingsMemoryHeistPatch {
  session_compaction_max_tokens?: number;
  session_compaction_preserve?: number;
  session_tool_prune_chars?: number;
}

/** HAM agent builder profile (project-scoped; not a Hermes runtime profile). */
export interface HamAgentProfile {
  id: string;
  name: string;
  description?: string;
  skills: string[];
  enabled: boolean;
  /** `https?://` or `data:image/jpeg;base64,...` from Agent Builder (optional). */
  avatar_url?: string;
}

export interface HamAgentsConfig {
  profiles: HamAgentProfile[];
  primary_agent_id: string;
}

export interface HamSettingsChanges {
  memory_heist?: HamSettingsMemoryHeistPatch;
  architect_instruction_chars?: number;
  commander_instruction_chars?: number;
  critic_instruction_chars?: number;
  /** Full replacement for the `agents` key in `.ham/settings.json`. */
  agents?: HamAgentsConfig;
}

export interface HamSettingsPreviewRow {
  path: string;
  old: unknown;
  new: unknown;
}

export interface HamSettingsPreviewResponse {
  project_id: string;
  project_root: string;
  client_proposal_id?: string | null;
  effective_before: Record<string, unknown>;
  effective_after: Record<string, unknown>;
  diff: HamSettingsPreviewRow[];
  warnings: string[];
  write_target: string;
  proposal_digest: string;
  base_revision: string;
}

export async function fetchSettingsWriteStatus(): Promise<{ writes_enabled: boolean }> {
  const res = await hamApiFetch("/api/settings/write-status");
  if (!res.ok) {
    throw new Error(`write-status: HTTP ${res.status}`);
  }
  return res.json() as Promise<{ writes_enabled: boolean }>;
}

/** Effective HAM agent profiles from merged project config. */
export async function fetchProjectAgents(projectId: string): Promise<HamAgentsConfig> {
  const res = await hamApiFetch(`/api/projects/${encodeURIComponent(projectId)}/agents`);
  const text = await res.text();
  let payload: unknown;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = null;
  }
  const detail =
    payload && typeof payload === "object" && payload !== null && "detail" in payload
      ? (payload as { detail: unknown }).detail
      : null;
  const apiMsg = messageFromFastApiDetail(detail);
  const errCode = fastApiStructuredErrorCode(detail);

  if (!res.ok) {
    if (res.status === 404 && errCode === "PROJECT_NOT_FOUND") {
      throw new Error(
        [
          `Agent Builder: project ${projectId} is not registered on this API instance (PROJECT_NOT_FOUND).`,
          "On Cloud Run / serverless, each instance has its own project registry file unless you use min instances = 1 or shared storage.",
          "Try again (retry may hit a warm instance), run the API locally, or configure a single warm instance.",
          apiMsg ? `(${apiMsg})` : "",
        ]
          .filter(Boolean)
          .join(" "),
      );
    }
    if (res.status === 404) {
      throw new Error(
        [
          "Agent Builder: GET /api/projects/…/agents returned 404.",
          'If the response is plain "Not Found" with no structured error, the API may be missing this route — redeploy Ham API from current main.',
          "Also confirm VITE_HAM_API_BASE is only the API origin (no /api suffix).",
          apiMsg ? `Detail: ${apiMsg}` : "",
        ]
          .filter(Boolean)
          .join(" "),
      );
    }
    throw new Error(apiMsg || `agents: HTTP ${res.status}`);
  }

  const data = payload as { agents?: HamAgentsConfig };
  if (!data?.agents?.profiles) {
    throw new Error("Invalid agents response");
  }
  return data.agents;
}

export async function listHamProjects(): Promise<{ projects: ProjectRecord[] }> {
  const res = await hamApiFetch("/api/projects");
  if (!res.ok) {
    throw new Error(`projects: HTTP ${res.status}`);
  }
  return res.json() as Promise<{ projects: ProjectRecord[] }>;
}

/**
 * Shallow-merges into `ProjectRecord.metadata` (PATCH). Send `null` for a value to remove that key.
 */
export async function patchHamProjectMetadata(
  projectId: string,
  metadata: Record<string, unknown | null>,
): Promise<ProjectRecord> {
  const res = await hamApiFetch(`/api/projects/${encodeURIComponent(projectId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ metadata }),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`patch project (HTTP ${res.status}): ${t}`);
  }
  return res.json() as Promise<ProjectRecord>;
}

export async function registerHamProject(body: {
  name: string;
  root: string;
  description?: string;
}): Promise<ProjectRecord> {
  const res = await hamApiFetch("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: body.name,
      root: body.root,
      description: body.description ?? "",
      metadata: {},
    }),
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`register project failed (HTTP ${res.status}): ${t}`);
  }
  return res.json() as Promise<ProjectRecord>;
}

/**
 * Find or create a Ham API project whose root matches the context-engine cwd
 * (same path the API uses for GET /api/context-engine).
 */
export async function ensureProjectIdForWorkspaceRoot(cwd: string): Promise<string> {
  const norm = cwd.replace(/\/$/, "");
  const { projects } = await listHamProjects();
  const hit = projects.find((p) => p.root.replace(/\/$/, "") === norm);
  if (hit) {
    return hit.id;
  }
  const name = norm.split("/").filter(Boolean).pop() || "workspace";
  const rec = await registerHamProject({
    name,
    root: norm,
    description: "Registered from Ham dashboard (Context & Memory).",
  });
  return rec.id;
}

async function detailMessageFromResponse(res: Response): Promise<string | null> {
  try {
    const j = (await res.json()) as { detail?: unknown };
    return messageFromFastApiDetail(j?.detail);
  } catch {
    return null;
  }
}

export async function postSettingsPreview(
  projectId: string,
  changes: HamSettingsChanges,
  clientProposalId?: string,
): Promise<HamSettingsPreviewResponse> {
  const res = await hamApiFetch(`/api/projects/${encodeURIComponent(projectId)}/settings/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      changes,
      client_proposal_id: clientProposalId ?? null,
    }),
  });
  if (!res.ok) {
    const msg = await detailMessageFromResponse(res);
    throw new Error(msg || `settings preview failed (HTTP ${res.status})`);
  }
  return res.json() as Promise<HamSettingsPreviewResponse>;
}

export async function postSettingsApply(
  projectId: string,
  changes: HamSettingsChanges,
  baseRevision: string,
  bearerToken: string,
): Promise<{
  backup_id: string;
  audit_id: string;
  effective_after: Record<string, unknown>;
  diff_applied: HamSettingsPreviewRow[];
  new_revision: string;
}> {
  const headers = new Headers({ "Content-Type": "application/json" });
  await applyHamOperatorSecretHeaders(headers, bearerToken);
  const res = await fetch(
    apiUrl(`/api/projects/${encodeURIComponent(projectId)}/settings/apply`),
    {
      method: "POST",
      headers,
      body: JSON.stringify({
        changes,
        base_revision: baseRevision,
      }),
    },
  );
  if (!res.ok) {
    const msg = await detailMessageFromResponse(res);
    throw new Error(msg || `settings apply failed (HTTP ${res.status})`);
  }
  return res.json() as Promise<{
    backup_id: string;
    audit_id: string;
    effective_after: Record<string, unknown>;
    diff_applied: HamSettingsPreviewRow[];
    new_revision: string;
  }>;
}
