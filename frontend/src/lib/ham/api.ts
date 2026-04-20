import type {
  ContextEnginePayload,
  CursorCredentialsStatus,
  ModelCatalogPayload,
  ProjectRecord,
} from "./types";

/**
 * Ham API origin for `fetch`.
 * - **Dev (default):** `""` → same origin as Vite; `/api/*` is proxied to FastAPI (see `vite.config.ts`).
 * - **Override:** set `VITE_HAM_API_BASE` (e.g. production full URL to the API host).
 */
export function getApiBase(): string {
  const explicit = (import.meta.env.VITE_HAM_API_BASE as string | undefined)
    ?.trim()
    .replace(/\/$/, "");
  if (explicit) return explicit;
  if (import.meta.env.DEV) return "";
  // Production build without VITE_HAM_API_BASE → browser would call localhost and "Failed to fetch".
  throw new Error(
    "VITE_HAM_API_BASE was not set when this site was built. In Vercel: Settings → Environment Variables → add VITE_HAM_API_BASE = your Cloud Run URL (no trailing slash). Enable it for Production and Preview, then redeploy.",
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
  model_id?: string;
  workbench_mode?: "ask" | "plan" | "agent";
  worker?: string;
  max_mode?: boolean;
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

export interface HamChatResponse {
  session_id: string;
  messages: HamChatMessage[];
  actions: HamUiAction[];
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

export async function postChat(body: HamChatRequest): Promise<HamChatResponse> {
  const url = apiUrl("/api/chat");
  const payload = {
    ...body,
    include_operator_skills: body.include_operator_skills ?? true,
    include_operator_subagents: body.include_operator_subagents ?? true,
    enable_ui_actions: body.enable_ui_actions ?? true,
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
): Promise<HamChatResponse> {
  const url = apiUrl("/api/chat/stream");
  const payload = {
    ...body,
    include_operator_skills: body.include_operator_skills ?? true,
    include_operator_subagents: body.include_operator_subagents ?? true,
    enable_ui_actions: body.enable_ui_actions ?? true,
  };
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/x-ndjson, application/json",
      },
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

// --- Allowlisted project settings (v1 control plane) ---

export interface HamSettingsMemoryHeistPatch {
  session_compaction_max_tokens?: number;
  session_compaction_preserve?: number;
  session_tool_prune_chars?: number;
}

export interface HamSettingsChanges {
  memory_heist?: HamSettingsMemoryHeistPatch;
  architect_instruction_chars?: number;
  commander_instruction_chars?: number;
  critic_instruction_chars?: number;
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
