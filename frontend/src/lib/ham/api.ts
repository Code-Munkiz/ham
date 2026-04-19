import type { ContextEnginePayload } from "./types";

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
  /** When true (default), model may emit `HAM_UI_ACTIONS_JSON`; response includes `actions` for the UI. */
  enable_ui_actions?: boolean;
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
