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
}

export interface HamChatResponse {
  session_id: string;
  messages: HamChatMessage[];
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
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (cause) {
    const hint =
      typeof cause === "object" && cause !== null && "message" in cause
        ? String((cause as Error).message)
        : "Network error";
    throw new Error(
      `${hint}. Check that the Ham API is running and VITE_HAM_API_BASE points to it (production builds).`,
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
  return res.json() as Promise<HamChatResponse>;
}
