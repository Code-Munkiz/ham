/**
 * HAM /api/workspace/profiles — JSON-backed agent profile cards (local v0).
 */

const BASE = "/api/workspace/profiles";

export type WorkspaceProfile = {
  id: string;
  name: string;
  emoji: string;
  model: string;
  systemPrompt: string;
  isDefault: boolean;
  createdAt: number;
  updatedAt: number;
};

export type ProfilesBridge = { status: "ready" } | { status: "pending"; detail: string };

const PENDING: ProfilesBridge = { status: "pending", detail: "Runtime bridge pending" };

export const workspaceProfilesAdapter = {
  description: "HAM /api/workspace/profiles — list/create/patch/default/delete",

  async list(q?: string): Promise<{
    profiles: WorkspaceProfile[];
    defaultProfileId: string | null;
    bridge: ProfilesBridge;
  }> {
    try {
      const url = q?.trim() ? `${BASE}?q=${encodeURIComponent(q.trim())}` : BASE;
      const res = await fetch(url, { credentials: "include" });
      if (!res.ok) return { profiles: [], defaultProfileId: null, bridge: PENDING };
      const data = (await res.json()) as {
        profiles?: WorkspaceProfile[];
        defaultProfileId?: string | null;
      };
      return {
        profiles: Array.isArray(data.profiles) ? data.profiles : [],
        defaultProfileId: data.defaultProfileId ?? null,
        bridge: { status: "ready" },
      };
    } catch {
      return { profiles: [], defaultProfileId: null, bridge: PENDING };
    }
  },

  async create(body: {
    name: string;
    emoji: string;
    model: string;
    systemPrompt: string;
  }): Promise<{ profile: WorkspaceProfile | null; bridge: ProfilesBridge; error?: string }> {
    try {
      const res = await fetch(BASE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!res.ok) return { profile: null, bridge: PENDING, error: `HTTP ${res.status}` };
      return { profile: (await res.json()) as WorkspaceProfile, bridge: { status: "ready" } };
    } catch (e) {
      return { profile: null, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },

  async patch(
    id: string,
    body: Partial<{
      name: string;
      emoji: string;
      model: string;
      systemPrompt: string;
    }>,
  ): Promise<{ profile: WorkspaceProfile | null; bridge: ProfilesBridge; error?: string }> {
    try {
      const res = await fetch(`${BASE}/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!res.ok) return { profile: null, bridge: PENDING, error: `HTTP ${res.status}` };
      return { profile: (await res.json()) as WorkspaceProfile, bridge: { status: "ready" } };
    } catch (e) {
      return { profile: null, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },

  async setDefault(
    id: string,
  ): Promise<{ ok: boolean; defaultProfileId: string | null; bridge: ProfilesBridge; error?: string }> {
    try {
      const res = await fetch(`${BASE}/${encodeURIComponent(id)}/set-default`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) return { ok: false, defaultProfileId: null, bridge: PENDING, error: `HTTP ${res.status}` };
      const j = (await res.json()) as { ok?: boolean; defaultProfileId?: string };
      return {
        ok: Boolean(j.ok),
        defaultProfileId: j.defaultProfileId ?? null,
        bridge: { status: "ready" },
      };
    } catch (e) {
      return {
        ok: false,
        defaultProfileId: null,
        bridge: PENDING,
        error: e instanceof Error ? e.message : String(e),
      };
    }
  },

  async remove(id: string): Promise<{ ok: boolean; bridge: ProfilesBridge; error?: string }> {
    try {
      const res = await fetch(`${BASE}/${encodeURIComponent(id)}`, { method: "DELETE", credentials: "include" });
      if (res.status !== 204) return { ok: false, bridge: PENDING, error: `HTTP ${res.status}` };
      return { ok: true, bridge: { status: "ready" } };
    } catch (e) {
      return { ok: false, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },
} as const;
