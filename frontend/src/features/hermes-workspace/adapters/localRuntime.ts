/**
 * Local HAM runtime targeting for machine-local Files + Terminal (user's disk via local uvicorn).
 * Cloud `VITE_HAM_API_BASE` is not used for these features — the browser must call the user's machine.
 * Stored in localStorage; never use file://.
 */

import { mergeClerkAuthBearerIfNeeded } from "@/lib/ham/api";

const STORAGE_KEY = "hww.localRuntimeBase";

/** Suggested input placeholders only — not used until the user saves. */
export const LOCAL_RUNTIME_SUGGESTIONS = ["http://127.0.0.1:8001", "http://127.0.0.1:8000"] as const;

function normalizeBase(raw: string): string {
  const t = raw.trim();
  if (!t) return "";
  let u: URL;
  try {
    u = new URL(t.includes("://") ? t : `http://${t}`);
  } catch {
    return "";
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") return "";
  return u.origin;
}

/**
 * User-configured local API origin (e.g. http://127.0.0.1:8001), or null.
 */
export function getLocalRuntimeBase(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const s = localStorage.getItem(STORAGE_KEY);
    if (!s) return null;
    return normalizeBase(s) || null;
  } catch {
    return null;
  }
}

export function setLocalRuntimeBase(value: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (value == null || value.trim() === "") {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      const n = normalizeBase(value);
      if (n) localStorage.setItem(STORAGE_KEY, n);
      else localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new CustomEvent("hww-local-runtime-changed", { detail: { base: getLocalRuntimeBase() } }));
}

export function isLocalRuntimeConfigured(): boolean {
  return Boolean(getLocalRuntimeBase());
}

/**
 * Build an absolute URL for a path that starts with `/api/...` under the local runtime origin.
 */
export function localRuntimeAbsoluteUrl(path: string): string {
  const base = getLocalRuntimeBase();
  if (!base) return "";
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${base}${p}`;
}

/**
 * `fetch` against the local runtime (cross-origin from Vite/Vercel). No cloud base.
 * Attaches Clerk bearer when a publishable key is present (local API may allow optional auth).
 */
export async function localRuntimeFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const url = localRuntimeAbsoluteUrl(path);
  if (!url) {
    return Promise.reject(new Error("local_runtime_unconfigured"));
  }
  const headers = new Headers(init.headers as HeadersInit | undefined);
  await mergeClerkAuthBearerIfNeeded(headers);
  return fetch(url, {
    ...init,
    headers,
    credentials: "omit",
  });
}

/**
 * WebSocket URL for a path (e.g. `/api/workspace/terminal/sessions/.../stream`) on the local runtime.
 */
export function localRuntimeWsUrl(path: string): string {
  const http = localRuntimeAbsoluteUrl(path);
  if (!http) return "";
  const u = new URL(http);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  return u.toString();
}

export type LocalRuntimeTestResult = {
  ok: boolean;
  message: string;
  /** Full URL of the test request. */
  testedUrl: string;
  health?: {
    ok?: boolean;
    workspaceRootConfigured?: boolean;
    features?: string[];
  };
};

/**
 * GET `/api/workspace/health` when available, else `GET /api/workspace/files?action=list` as a compatibility probe.
 */
async function fetchWithRuntimeBase(
  base: string,
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const p = path.startsWith("/") ? path : `/${path}`;
  const url = `${base}${p}`;
  const headers = new Headers(init.headers as HeadersInit | undefined);
  await mergeClerkAuthBearerIfNeeded(headers);
  return fetch(url, {
    ...init,
    headers,
    credentials: "omit",
  });
}

/**
 * @param inputUrl — when set, tests this origin (e.g. unsaved text field). When omitted, uses `getLocalRuntimeBase()`.
 */
export async function testLocalRuntime(inputUrl?: string | null): Promise<LocalRuntimeTestResult> {
  const base = inputUrl != null && String(inputUrl).trim() ? normalizeBase(inputUrl) : getLocalRuntimeBase();
  if (!base) {
    return { ok: false, message: "Local runtime URL is not set or invalid", testedUrl: "" };
  }

  const healthPath = "/api/workspace/health";
  const healthUrl = `${base}${healthPath}`;

  try {
    const res = await fetchWithRuntimeBase(base, healthPath, { method: "GET" });
    if (res.ok) {
      const j = (await res.json().catch(() => ({}))) as {
        ok?: boolean;
        workspaceRootConfigured?: boolean;
        features?: string[];
      };
      const ok = j?.ok === true;
      return {
        ok,
        message: ok ? "Connected" : "Invalid health payload",
        testedUrl: healthUrl,
        health: {
          ok: j?.ok,
          workspaceRootConfigured: j?.workspaceRootConfigured,
          features: j?.features,
        },
      };
    }
    if (res.status !== 404) {
      return { ok: false, message: `HTTP ${res.status}`, testedUrl: healthUrl };
    }
  } catch {
    /* fall through to list probe */
  }

  const listPath = "/api/workspace/files?action=list";
  const listUrl = `${base}${listPath}`;
  try {
    const res2 = await fetchWithRuntimeBase(base, listPath, { method: "GET" });
    if (res2.ok) {
      return {
        ok: true,
        message: "Connected (files list; upgrade server for /api/workspace/health)",
        testedUrl: listUrl,
      };
    }
    if (res2.status === 404) {
      return {
        ok: false,
        message: "Wrong API — /api/workspace/files missing. Use your local Ham API origin.",
        testedUrl: listUrl,
      };
    }
    return { ok: false, message: `HTTP ${res2.status}`, testedUrl: listUrl };
  } catch (e) {
    return {
      ok: false,
      message: e instanceof Error ? e.message : "Not reachable (CORS or network)",
      testedUrl: listUrl,
    };
  }
}
