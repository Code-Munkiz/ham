/**
 * Local HAM runtime targeting for machine-local Files + Terminal (user's disk via local uvicorn).
 * Cloud `VITE_HAM_API_BASE` is not used for these features — the browser must call the user's machine.
 * Stored in localStorage; never use file://.
 */

import { mergeClerkAuthBearerIfNeeded } from "@/lib/ham/api";
import type { ContextEnginePayload } from "@/lib/ham/types";

const STORAGE_KEY = "hww.localRuntimeBase";

/** Suggested input placeholders only — not used until the user saves. */
export const LOCAL_RUNTIME_SUGGESTIONS = ["http://127.0.0.1:8001", "http://127.0.0.1:8000"] as const;

/**
 * Tried in order by “Connect local machine” — must be absolute origins (not paths).
 * Only origins that respond to {@link HAM_WORKSPACE_HEALTH_PATH} with a valid HAM payload are saved.
 */
export const DEFAULT_LOCAL_RUNTIME_CANDIDATES = [
  "http://127.0.0.1:8001",
  "http://localhost:8001",
  "http://127.0.0.1:8000",
  "http://localhost:8000",
] as const;

export const HAM_WORKSPACE_HEALTH_PATH = "/api/workspace/health" as const;

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

export type LocalRuntimeHealthPayload = {
  ok?: boolean;
  workspaceRootConfigured?: boolean;
  workspaceRootPath?: string;
  broadFilesystemAccess?: boolean;
  features?: string[];
};

export type LocalRuntimeTestResult = {
  ok: boolean;
  message: string;
  /** Full URL of the test request. */
  testedUrl: string;
  health?: LocalRuntimeHealthPayload;
};

/** GET `/api/workspace/health` on the saved local runtime (Files/Terminal probe). */
export async function fetchLocalWorkspaceHealth(): Promise<LocalRuntimeHealthPayload | null> {
  if (!isLocalRuntimeConfigured()) return null;
  try {
    const res = await localRuntimeFetch(HAM_WORKSPACE_HEALTH_PATH, { method: "GET" });
    if (!res.ok) return null;
    return (await res.json()) as LocalRuntimeHealthPayload;
  } catch {
    return null;
  }
}

const LOCAL_CONTEXT_SNAPSHOT_PATH = "/api/workspace/context-snapshot" as const;

/**
 * Context engine snapshot from the **local** HAM API using configured workspace root only.
 * Throws on HTTP errors or invalid JSON (caller falls back to cloud routes).
 */
export async function fetchLocalWorkspaceContextSnapshot(): Promise<ContextEnginePayload> {
  const res = await localRuntimeFetch(LOCAL_CONTEXT_SNAPSHOT_PATH, { method: "GET" });
  const rawText = await res.text();
  let body: unknown = null;
  try {
    body = rawText ? JSON.parse(rawText) : null;
  } catch {
    body = null;
  }
  if (!res.ok) {
    const d =
      body && typeof body === "object" && body !== null && "detail" in body
        ? (body as { detail?: unknown }).detail
        : null;
    const msg =
      d && typeof d === "object" && d !== null && "message" in d && typeof (d as { message: unknown }).message === "string"
        ? (d as { message: string }).message
        : `Local context snapshot failed (${res.status})`;
    throw new Error(msg);
  }
  if (!body || typeof body !== "object") {
    throw new Error("Invalid local context snapshot response");
  }
  return { ...(body as ContextEnginePayload), context_source: "local" };
}

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

function isValidHamHealthJson(j: unknown): j is LocalRuntimeHealthPayload {
  if (!j || typeof j !== "object") return false;
  const o = j as Record<string, unknown>;
  return o.ok === true && Array.isArray(o.features);
}

/**
 * Probes `DEFAULT_LOCAL_RUNTIME_CANDIDATES` in order. Only a valid HAM
 * `/api/workspace/health` JSON payload causes success — a random process on
 * the same port is not auto-saved.
 */
export type LocalRuntimeConnectResult =
  | {
      ok: true;
      base: string;
      health: LocalRuntimeHealthPayload;
      testedUrl: string;
    }
  | {
      ok: false;
      code: "no_ham_reachable" | "wrong_service";
      message: string;
      tried: readonly string[];
      wrongAt?: string;
    };

export async function probeLocalRuntimeCandidates(): Promise<LocalRuntimeConnectResult> {
  const tried: string[] = [];
  let wrongAt: string | undefined;
  for (const base of DEFAULT_LOCAL_RUNTIME_CANDIDATES) {
    const healthUrl = `${base}${HAM_WORKSPACE_HEALTH_PATH}`;
    tried.push(healthUrl);
    try {
      const res = await fetchWithRuntimeBase(base, HAM_WORKSPACE_HEALTH_PATH, { method: "GET" });
      const j = (await res.json().catch(() => null)) as unknown;
      if (res.ok && isValidHamHealthJson(j)) {
        return { ok: true, base, health: j, testedUrl: healthUrl };
      }
      if (res.status === 404) {
        continue;
      }
      if (res.ok && !isValidHamHealthJson(j)) {
        wrongAt = base;
        continue;
      }
    } catch {
      /* try next */
    }
  }
  if (wrongAt) {
    return {
      ok: false,
      code: "wrong_service",
      message:
        "Something responded, but it is not the HAM local API (expected /api/workspace/health with ok: true and features).",
      tried: [...tried],
      wrongAt,
    };
  }
  return {
    ok: false,
    code: "no_ham_reachable",
    message:
      "No HAM local runtime on the usual addresses. If it is already running, the browser may be blocking the connection (CORS or private-network rules); restart the API from the latest main or check Settings → advanced.",
    tried: [...tried],
  };
}

/**
 * Probes, then calls {@link setLocalRuntimeBase} only on success. Dispatches
 * `hww-local-runtime-changed` via `setLocalRuntimeBase` so Files/Terminal refresh.
 */
export async function connectLocalMachine(): Promise<LocalRuntimeConnectResult> {
  const r = await probeLocalRuntimeCandidates();
  if (r.ok) {
    setLocalRuntimeBase(r.base);
  }
  return r;
}

/**
 * This page’s origin (e.g. `https://…vercel.app`) — for user-facing CORS copy only.
 */
export function getBrowserPageOrigin(): string {
  if (typeof window === "undefined") return "";
  return window.location.origin;
}

/**
 * PowerShell to run HAM on Windows from a clone. Path is a hint; user should edit
 * to their own repo directory.
 */
export function getLocalConnectSetupScript(
  hamRepoPath = "C:\\Projects\\GoHam\\ham",
): string {
  return `cd ${hamRepoPath}
git pull origin main
$env:HAM_WORKSPACE_ROOT = "C:\\"
python -m uvicorn src.api.server:app --host 127.0.0.1 --port 8001`;
}

/**
 * @param inputUrl — when set, tests this origin (e.g. unsaved text field). When omitted, uses `getLocalRuntimeBase()`.
 */
export async function testLocalRuntime(inputUrl?: string | null): Promise<LocalRuntimeTestResult> {
  const base = inputUrl != null && String(inputUrl).trim() ? normalizeBase(inputUrl) : getLocalRuntimeBase();
  if (!base) {
    return { ok: false, message: "Local runtime URL is not set or invalid", testedUrl: "" };
  }

  const healthPath = HAM_WORKSPACE_HEALTH_PATH;
  const healthUrl = `${base}${healthPath}`;

  try {
    const res = await fetchWithRuntimeBase(base, healthPath, { method: "GET" });
    if (res.ok) {
      const j = (await res.json().catch(() => ({}))) as LocalRuntimeHealthPayload;
      const ok = j?.ok === true;
      return {
        ok,
        message: ok ? "Connected" : "Invalid health payload",
        testedUrl: healthUrl,
        health: {
          ok: j?.ok,
          workspaceRootConfigured: j?.workspaceRootConfigured,
          workspaceRootPath: j?.workspaceRootPath,
          broadFilesystemAccess: j?.broadFilesystemAccess,
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
