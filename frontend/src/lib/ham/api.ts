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
  return "http://127.0.0.1:8000";
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
}

export interface HamChatResponse {
  session_id: string;
  messages: HamChatMessage[];
}

/**
 * Interactive assistant turn via Ham API (server may use a gateway adapter; browser only sees Ham).
 */
export async function postChat(body: HamChatRequest): Promise<HamChatResponse> {
  const url = apiUrl("/api/chat");
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = `Chat request failed (HTTP ${res.status})`;
    try {
      const j = (await res.json()) as {
        detail?: { error?: { message?: string; code?: string } };
      };
      const m = j?.detail?.error?.message;
      if (m) msg = m;
    } catch {
      /* ignore JSON parse */
    }
    throw new Error(msg);
  }
  return res.json() as Promise<HamChatResponse>;
}
