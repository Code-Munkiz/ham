import type {
  ContextEnginePayload,
  CursorCredentialsStatus,
  ModelCatalogPayload,
  ProjectRecord,
} from "./types";

/**
 * Ham API **origin** for `fetch` (scheme + host, optional port). Paths already include `/api/...`.
 * - **Dev (default):** `""` → same origin as Vite; `/api/*` is proxied to FastAPI (see `vite.config.ts`).
 * - **Override:** `VITE_HAM_API_BASE` = e.g. `https://ham-api-xxxxx.run.app` — **no** `/api` suffix (that would produce `/api/api/...` and HTTP 404).
 */
export function getApiBase(): string {
  const raw = (import.meta.env.VITE_HAM_API_BASE as string | undefined)?.trim();
  if (raw) {
    let base = raw.replace(/\/+$/, "");
    // Common Vercel/operator mistake: set base to …/run.app/api — our paths already start with /api/
    if (base.toLowerCase().endsWith("/api")) {
      base = base.slice(0, -4).replace(/\/+$/, "");
    }
    return base;
  }
  if (import.meta.env.DEV) return "";
  // Production build without VITE_HAM_API_BASE → browser would call localhost and "Failed to fetch".
  throw new Error(
    "VITE_HAM_API_BASE was not set when this site was built. In Vercel: Settings → Environment Variables → add VITE_HAM_API_BASE = your Cloud Run URL (no trailing slash, no /api suffix). Enable it for Production and Preview, then redeploy.",
  );
}

/** Build an absolute or same-origin path for the Ham API (Vite dev uses relative `/api/...` + proxy). */
export function apiUrl(path: string): string {
  const base = getApiBase();
  const p = path.startsWith("/") ? path : `/${path}`;
  return base ? `${base}${p}` : p;
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
  const res = await fetch(apiUrl("/api/models"));
  if (!res.ok) {
    throw new Error(`models catalog: HTTP ${res.status}`);
  }
  return res.json() as Promise<ModelCatalogPayload>;
}

export async function fetchContextEngine(): Promise<ContextEnginePayload> {
  const url = apiUrl("/api/context-engine");
  const res = await fetch(url);
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
  const url = apiUrl("/api/cursor/credentials-status");
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`cursor credentials: HTTP ${res.status}`);
  }
  return res.json() as Promise<CursorCredentialsStatus>;
}

/** Proxy to Cursor `GET /v0/models` — uses the same team key as Settings. */
export async function fetchCursorModels(): Promise<unknown> {
  const res = await fetch(apiUrl("/api/cursor/models"));
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return res.json() as Promise<unknown>;
}

/** Save team Cursor API key server-side (~/.ham/cursor_credentials.json). Verifies via Cursor /v0/me. */
export async function saveCursorApiKey(apiKey: string): Promise<void> {
  const res = await fetch(apiUrl("/api/cursor/credentials"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ api_key: apiKey.trim() }),
  });
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
}

/** Remove UI-saved key; falls back to CURSOR_API_KEY env on the API host. */
export async function clearSavedCursorApiKey(): Promise<void> {
  const res = await fetch(apiUrl("/api/cursor/credentials"), { method: "DELETE" });
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
}

/** Proxy `GET /v0/agents/{id}` — Cloud Agent status and metadata. */
export async function fetchCursorAgent(agentId: string): Promise<Record<string, unknown>> {
  const res = await fetch(apiUrl(`/api/cursor/agents/${encodeURIComponent(agentId)}`));
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
  const res = await fetch(
    apiUrl(`/api/cursor/agents/${encodeURIComponent(agentId)}/conversation`),
  );
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
}

async function browserRuntimeJson<T>(path: string, body?: unknown, method = "POST"): Promise<T> {
  const res = await fetch(apiUrl(path), {
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
  const res = await fetch(apiUrl(`/api/browser/sessions/${encodeURIComponent(sessionId)}?${q}`));
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
  const res = await fetch(apiUrl(`/api/browser/sessions/${encodeURIComponent(sessionId)}?${q}`), {
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
  const res = await fetch(apiUrl(`/api/browser/sessions/${encodeURIComponent(sessionId)}/screenshot`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ owner_key: ownerKey }),
  });
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
  const res = await fetch(
    apiUrl(`/api/browser/sessions/${encodeURIComponent(sessionId)}/stream/state?${q}`),
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
  const res = await fetch(
    apiUrl(`/api/cursor/agents/${encodeURIComponent(agentId)}/followup`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt_text: promptText }),
    },
  );
  if (!res.ok) {
    const msg = (await readFastApiDetail(res)) ?? `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return res.json() as Promise<Record<string, unknown>>;
}

export async function fetchProjectContextEngine(
  projectId: string,
): Promise<ContextEnginePayload> {
  const url = apiUrl(`/api/projects/${encodeURIComponent(projectId)}/context-engine`);
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`project context-engine: HTTP ${res.status}`);
  }
  return res.json() as Promise<ContextEnginePayload>;
}

/** Ham-native chat DTOs (matches `src/api/chat.py`). */
export type HamChatRole = "user" | "assistant" | "system";

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
  messages: HamChatMessage[];
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
  /** Structured confirm/apply/register/launch (see API `ChatOperatorPayload`). */
  operator?: {
    phase?: "apply_settings" | "register_project" | "launch_run" | null;
    confirmed?: boolean;
    project_id?: string | null;
    changes?: Record<string, unknown> | null;
    base_revision?: string | null;
    name?: string | null;
    root?: string | null;
    description?: string | null;
    prompt?: string | null;
    profile_id?: string | null;
  } | null;
}

/** Matches `/chat` workbench header: CHAT | SPLIT | PREVIEW | WAR ROOM */
export type HamWorkbenchViewMode = "chat" | "split" | "preview" | "war_room";

/** Structured UI actions from `POST /api/chat` (server-validated). */
export type HamUiAction =
  | { type: "navigate"; path: string }
  | { type: "open_settings"; tab?: string | null }
  | {
      type: "toast";
      level: "info" | "success" | "warning" | "error";
      message: string;
    }
  | { type: "toggle_control_panel"; open?: boolean | null }
  | { type: "set_workbench_view"; mode: HamWorkbenchViewMode };

export interface HamOperatorResult {
  handled: boolean;
  intent?: string | null;
  ok: boolean;
  blocking_reason?: string | null;
  pending_apply?: Record<string, unknown> | null;
  pending_launch?: Record<string, unknown> | null;
  pending_register?: Record<string, unknown> | null;
  data?: Record<string, unknown>;
}

export interface HamChatResponse {
  session_id: string;
  messages: HamChatMessage[];
  actions: HamUiAction[];
  active_agent?: HamChatActiveAgentMeta | null;
  operator_result?: HamOperatorResult | null;
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
function fastApiStructuredErrorCode(detail: unknown): string | null {
  if (typeof detail !== "object" || detail === null || !("error" in detail)) return null;
  const e = (detail as { error?: { code?: string } }).error;
  return typeof e?.code === "string" ? e.code : null;
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
      const parsed = messageFromFastApiDetail(j?.detail);
      if (parsed) msg = parsed;
    } catch {
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
    }
  | { type: "error"; code: string; message: string };

const streamNetworkHint =
  "Check VITE_HAM_API_BASE (redeploy after changing). If the API is up but chat still fails, the browser origin may be blocked by CORS: add it to HAM_CORS_ORIGINS or set HAM_CORS_ORIGIN_REGEX on the API (see docs/examples/ham-api-cloud-run-env.yaml).";

/**
 * Streaming assistant turn (NDJSON). Tokens arrive as `delta` events; final transcript in `done`.
 */
export async function postChatStream(
  body: HamChatRequest,
  callbacks: {
    onSession?: (sessionId: string) => void;
    onDelta?: (text: string) => void;
  } = {},
  authorization?: string,
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
  const auth = authorization?.trim();
  if (auth) headers.Authorization = `Bearer ${auth}`;
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
      const parsed = messageFromFastApiDetail(j?.detail);
      if (parsed) msg = parsed;
    } catch {
      /* ignore */
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

export async function fetchHermesSkillsCatalog(): Promise<HermesSkillsCatalogResponse> {
  const res = await fetch(apiUrl("/api/hermes-skills/catalog"));
  if (!res.ok) {
    throw new Error(`hermes-skills/catalog: HTTP ${res.status}`);
  }
  return res.json() as Promise<HermesSkillsCatalogResponse>;
}

export async function fetchHermesSkillDetail(
  catalogId: string,
): Promise<{ kind: string; entry: HermesSkillCatalogEntryDetail }> {
  const res = await fetch(
    apiUrl(`/api/hermes-skills/catalog/${encodeURIComponent(catalogId)}`),
  );
  if (!res.ok) {
    throw new Error(`hermes-skills/catalog/${catalogId}: HTTP ${res.status}`);
  }
  return res.json() as Promise<{ kind: string; entry: HermesSkillCatalogEntryDetail }>;
}

export async function fetchHermesSkillsCapabilities(): Promise<HermesSkillsCapabilities> {
  const res = await fetch(apiUrl("/api/hermes-skills/capabilities"));
  if (!res.ok) {
    throw new Error(`hermes-skills/capabilities: HTTP ${res.status}`);
  }
  return res.json() as Promise<HermesSkillsCapabilities>;
}

export async function fetchHermesSkillsTargets(): Promise<HermesSkillsTargetsResponse> {
  const res = await fetch(apiUrl("/api/hermes-skills/targets"));
  if (!res.ok) {
    throw new Error(`hermes-skills/targets: HTTP ${res.status}`);
  }
  return res.json() as Promise<HermesSkillsTargetsResponse>;
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
  const res = await fetch(apiUrl("/api/hermes-skills/install/write-status"));
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
  const res = await fetch(apiUrl("/api/hermes-skills/install/preview"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  const res = await fetch(apiUrl("/api/hermes-skills/install/apply"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${bearerToken.trim()}`,
    },
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
  const res = await fetch(apiUrl("/api/settings/write-status"));
  if (!res.ok) {
    throw new Error(`write-status: HTTP ${res.status}`);
  }
  return res.json() as Promise<{ writes_enabled: boolean }>;
}

/** Effective HAM agent profiles from merged project config. */
export async function fetchProjectAgents(projectId: string): Promise<HamAgentsConfig> {
  const res = await fetch(apiUrl(`/api/projects/${encodeURIComponent(projectId)}/agents`));
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
  const res = await fetch(apiUrl("/api/projects"));
  if (!res.ok) {
    throw new Error(`projects: HTTP ${res.status}`);
  }
  return res.json() as Promise<{ projects: ProjectRecord[] }>;
}

export async function registerHamProject(body: {
  name: string;
  root: string;
  description?: string;
}): Promise<ProjectRecord> {
  const res = await fetch(apiUrl("/api/projects"), {
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
  const res = await fetch(
    apiUrl(`/api/projects/${encodeURIComponent(projectId)}/settings/preview`),
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        changes,
        client_proposal_id: clientProposalId ?? null,
      }),
    },
  );
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
  const res = await fetch(
    apiUrl(`/api/projects/${encodeURIComponent(projectId)}/settings/apply`),
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${bearerToken.trim()}`,
      },
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
