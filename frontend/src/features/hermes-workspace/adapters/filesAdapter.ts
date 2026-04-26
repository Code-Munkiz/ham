/**
 * `workspaceFileAdapter` — HAM-owned bridge: `/api/workspace/files*`.
 * Upstream reference: `file-explorer-sidebar.tsx` (Hermes `/api/files` contract — mapped here).
 * Uses `hamApiFetch` so Vercel (and any static host) targets `VITE_HAM_API_BASE` instead of same-origin 404s.
 */

import { hamApiFetch } from "@/lib/ham/api";

const BASE = "/api/workspace/files";

export type WorkspaceFileEntry = {
  name: string;
  path: string;
  type: "file" | "folder";
  children?: WorkspaceFileEntry[];
};

export type FileBridgeState =
  | { status: "ready" }
  | { status: "pending"; detail: string };

const BRIDGE_PENDING: FileBridgeState = { status: "pending", detail: "Runtime bridge pending" };

async function readJson<T>(res: Response): Promise<T> {
  return (await res.json()) as T;
}

export const workspaceFileAdapter = {
  description:
    "HAM /api/workspace/files — list/read/write and upload; server root is HAM_WORKSPACE_ROOT (or legacy HAM_WORKSPACE_FILES_ROOT) on the machine where FastAPI runs.",

  async list(): Promise<{ entries: WorkspaceFileEntry[]; bridge: FileBridgeState }> {
    try {
      const res = await hamApiFetch(`${BASE}?action=list`, { credentials: "include" });
      if (!res.ok) {
        return { entries: [], bridge: BRIDGE_PENDING };
      }
      const data = await readJson<{ entries?: WorkspaceFileEntry[] }>(res);
      const entries = Array.isArray(data.entries) ? data.entries : [];
      return { entries, bridge: { status: "ready" } };
    } catch {
      return { entries: [], bridge: BRIDGE_PENDING };
    }
  },

  async postJson(body: unknown): Promise<{ ok: boolean; bridge: FileBridgeState; error?: string }> {
    try {
      const res = await hamApiFetch(BASE, {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        return { ok: false, bridge: BRIDGE_PENDING, error: `HTTP ${res.status}` };
      }
      return { ok: true, bridge: { status: "ready" } };
    } catch (e) {
      return {
        ok: false,
        bridge: BRIDGE_PENDING,
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  /**
   * Multipart upload: FormData with `file` and optional `path` (target folder, relative to workspace root).
   * Do not include legacy `action=upload` — server route is `POST /api/workspace/files/upload`.
   */
  async postFormData(form: FormData): Promise<{ ok: boolean; bridge: FileBridgeState; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/upload`, {
        method: "POST",
        credentials: "include",
        body: form,
      });
      if (!res.ok) {
        return { ok: false, bridge: BRIDGE_PENDING, error: `HTTP ${res.status}` };
      }
      return { ok: true, bridge: { status: "ready" } };
    } catch (e) {
      return {
        ok: false,
        bridge: BRIDGE_PENDING,
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  buildDownloadUrl(path: string): string {
    return `${BASE}?action=download&path=${encodeURIComponent(path)}`;
  },

  async readText(
    path: string,
  ): Promise<{ text: string | null; bridge: FileBridgeState; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}?action=read&path=${encodeURIComponent(path)}`, {
        credentials: "include",
      });
      if (!res.ok) {
        return { text: null, bridge: BRIDGE_PENDING };
      }
      const data = (await res.json()) as { content?: string; text?: string };
      const text = typeof data.content === "string" ? data.content : data.text ?? null;
      return { text, bridge: { status: "ready" } };
    } catch (e) {
      return {
        text: null,
        bridge: BRIDGE_PENDING,
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },
} as const;
