/**
 * `workspaceFileAdapter` — HAM-owned bridge: `/api/workspace/files*`.
 * Targets the **user's local** Ham API (browser `localStorage` `hww.localRuntimeBase`), not
 * `VITE_HAM_API_BASE` / Cloud Run — the server must run on the machine that owns the files
 * (see HAM_WORKSPACE_ROOT). Never `file://`.
 */

import { getLocalRuntimeBase, isLocalRuntimeConfigured, localRuntimeFetch } from "./localRuntime";

const BASE = "/api/workspace/files";

export type WorkspaceFileEntry = {
  name: string;
  path: string;
  type: "file" | "folder";
  /** `null` = not loaded yet; expand via `listPath` */
  children?: WorkspaceFileEntry[] | null;
};

export type FileBridgeLocalCode = "unconfigured" | "unreachable" | "wrong_api";

export type FileBridgeState =
  | { status: "ready" }
  | { status: "pending"; detail: string; localCode?: FileBridgeLocalCode };

const DISCONNECT_HINT =
  "Start the local HAM API (e.g. uvicorn) and set HAM_WORKSPACE_ROOT to a project folder (or a broad path such as a drive) on this computer.";

function bridgeUnconfigured(): FileBridgeState {
  return {
    status: "pending",
    detail: `Local runtime is not connected. ${DISCONNECT_HINT} In Workspace → Settings → Connection, save your local API URL (e.g. http://127.0.0.1:8001).`,
    localCode: "unconfigured",
  };
}

function bridgeFromHttp(res: Response): FileBridgeState {
  if (res.status === 404) {
    return {
      status: "pending",
      detail: "Wrong API — /api/workspace/files is missing. Check that the Local runtime URL is your Ham FastAPI origin.",
      localCode: "wrong_api",
    };
  }
  return {
    status: "pending",
    detail: `Local runtime error (HTTP ${res.status}). ${DISCONNECT_HINT}`,
    localCode: "unreachable",
  };
}

function bridgeFromError(e: unknown): FileBridgeState {
  const msg = e instanceof Error ? e.message : String(e);
  if (msg === "local_runtime_unconfigured") {
    return bridgeUnconfigured();
  }
  return {
    status: "pending",
    detail: `Not reachable — ${msg}. CORS: allow this page's origin in HAM_CORS_ORIGINS on the local API.`,
    localCode: "unreachable",
  };
}

async function readJson<T>(res: Response): Promise<T> {
  return (await res.json()) as T;
}

export const workspaceFileAdapter = {
  description:
    "HAM /api/workspace/files on the **local** runtime — list/read/write; server root is HAM_WORKSPACE_ROOT on the machine where uvicorn runs.",

  async list(): Promise<{ entries: WorkspaceFileEntry[]; bridge: FileBridgeState }> {
    return workspaceFileAdapter.listPath("");
  },

  /**
   * List one directory level under the workspace root. Use `path` relative to root (e.g. `src/components`).
   */
  async listPath(
    relPath: string,
  ): Promise<{ entries: WorkspaceFileEntry[]; bridge: FileBridgeState }> {
    if (!isLocalRuntimeConfigured()) {
      return { entries: [], bridge: bridgeUnconfigured() };
    }
    const p = (relPath || "").replace(/\\/g, "/").replace(/^\/+/, "");
    const q = p ? `${BASE}?action=list&path=${encodeURIComponent(p)}` : `${BASE}?action=list`;
    try {
      const res = await localRuntimeFetch(q, { method: "GET" });
      if (!res.ok) {
        return { entries: [], bridge: bridgeFromHttp(res) };
      }
      const data = await readJson<{ entries?: WorkspaceFileEntry[] }>(res);
      const entries = Array.isArray(data.entries) ? data.entries : [];
      return { entries, bridge: { status: "ready" } };
    } catch (e) {
      return { entries: [], bridge: bridgeFromError(e) };
    }
  },

  async postJson(body: unknown): Promise<{ ok: boolean; bridge: FileBridgeState; error?: string }> {
    if (!isLocalRuntimeConfigured()) {
      return { ok: false, bridge: bridgeUnconfigured() };
    }
    try {
      const res = await localRuntimeFetch(BASE, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        return { ok: false, bridge: bridgeFromHttp(res), error: `HTTP ${res.status}` };
      }
      return { ok: true, bridge: { status: "ready" } };
    } catch (e) {
      return { ok: false, bridge: bridgeFromError(e), error: e instanceof Error ? e.message : String(e) };
    }
  },

  /**
   * Multipart upload: FormData with `file` and optional `path` (target folder, relative to workspace root).
   */
  async postFormData(form: FormData): Promise<{ ok: boolean; bridge: FileBridgeState; error?: string }> {
    if (!isLocalRuntimeConfigured()) {
      return { ok: false, bridge: bridgeUnconfigured() };
    }
    try {
      const res = await localRuntimeFetch(`${BASE}/upload`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        return { ok: false, bridge: bridgeFromHttp(res), error: `HTTP ${res.status}` };
      }
      return { ok: true, bridge: { status: "ready" } };
    } catch (e) {
      return { ok: false, bridge: bridgeFromError(e), error: e instanceof Error ? e.message : String(e) };
    }
  },

  /** Absolute `http://…/api/workspace/files?action=download&…` for the local runtime, or `""` if unset. */
  buildDownloadUrl(path: string): string {
    const base = getLocalRuntimeBase();
    if (!base) return "";
    return `${base}${BASE}?action=download&path=${encodeURIComponent(path)}`;
  },

  async readText(
    path: string,
  ): Promise<{ text: string | null; bridge: FileBridgeState; error?: string }> {
    if (!isLocalRuntimeConfigured()) {
      return { text: null, bridge: bridgeUnconfigured() };
    }
    try {
      const res = await localRuntimeFetch(`${BASE}?action=read&path=${encodeURIComponent(path)}`, {
        method: "GET",
      });
      if (!res.ok) {
        return { text: null, bridge: bridgeFromHttp(res) };
      }
      const data = (await res.json()) as { content?: string; text?: string };
      const text = typeof data.content === "string" ? data.content : data.text ?? null;
      return { text, bridge: { status: "ready" } };
    } catch (e) {
      return {
        text: null,
        bridge: bridgeFromError(e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },
} as const;
