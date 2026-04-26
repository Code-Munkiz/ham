/**
 * HAM /api/workspace/memory — JSON-backed memory items (local v0; not full Memory Heist).
 */

import { hamApiFetch } from "@/lib/ham/api";

import { workspaceApiPending } from "../lib/workspaceHamApiState";

const BASE = "/api/workspace/memory";

export type MemoryKind = "note" | "preference";

export type WorkspaceMemoryItem = {
  id: string;
  title: string;
  body: string;
  tags: string[];
  kind: MemoryKind;
  archived: boolean;
  createdAt: number;
  updatedAt: number;
};

export type MemoryBridge = { status: "ready" } | { status: "pending"; detail: string };

async function readJson<T>(res: Response): Promise<T> {
  return (await res.json()) as T;
}

function qs(p: Record<string, string | boolean | number | undefined>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) {
    if (v === undefined) continue;
    u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

export const workspaceMemoryAdapter = {
  description: "HAM /api/workspace/memory — list/create/patch/delete items",

  async list(
    q?: string,
    archived = false,
  ): Promise<{ items: WorkspaceMemoryItem[]; bridge: MemoryBridge }> {
    try {
      const res = await hamApiFetch(
        `${BASE}/items${qs({ q: q?.trim() || undefined, archived })}`,
        { credentials: "include" },
      );
      if (!res.ok) return { items: [], bridge: workspaceApiPending("memory", res) };
      const data = await readJson<{ items?: WorkspaceMemoryItem[] }>(res);
      return { items: Array.isArray(data.items) ? data.items : [], bridge: { status: "ready" } };
    } catch (e) {
      return { items: [], bridge: workspaceApiPending("memory", null, e) };
    }
  },

  async create(body: {
    title: string;
    body: string;
    tags?: string[];
    kind: MemoryKind;
  }): Promise<{ item: WorkspaceMemoryItem | null; bridge: MemoryBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!res.ok)
        return { item: null, bridge: workspaceApiPending("memory", res), error: `HTTP ${res.status}` };
      return { item: (await res.json()) as WorkspaceMemoryItem, bridge: { status: "ready" } };
    } catch (e) {
      return {
        item: null,
        bridge: workspaceApiPending("memory", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async patch(
    id: string,
    body: Partial<{
      title: string;
      body: string;
      tags: string[];
      kind: MemoryKind;
      archived: boolean;
    }>,
  ): Promise<{ item: WorkspaceMemoryItem | null; bridge: MemoryBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/items/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!res.ok)
        return { item: null, bridge: workspaceApiPending("memory", res), error: `HTTP ${res.status}` };
      return { item: (await res.json()) as WorkspaceMemoryItem, bridge: { status: "ready" } };
    } catch (e) {
      return {
        item: null,
        bridge: workspaceApiPending("memory", null, e),
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async remove(id: string): Promise<{ ok: boolean; bridge: MemoryBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/items/${encodeURIComponent(id)}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (res.status !== 204) return { ok: false, bridge: workspaceApiPending("memory", res), error: `HTTP ${res.status}` };
      return { ok: true, bridge: { status: "ready" } };
    } catch (e) {
      return { ok: false, bridge: workspaceApiPending("memory", null, e), error: e instanceof Error ? e.message : String(e) };
    }
  },
} as const;
