/**
 * HAM /api/workspace/skills — local catalog + install/enable (no upstream Hermes).
 */

import { hamApiFetch } from "@/lib/ham/api";

import { workspaceApiPending } from "../lib/workspaceHamApiState";

const BASE = "/api/workspace/skills";

export type WorkspaceSkill = {
  id: string;
  name: string;
  description: string;
  installed: boolean;
  enabled: boolean;
  config: string;
  createdAt: number;
  updatedAt: number;
};

export type SkillsBridge = { status: "ready" } | { status: "pending"; detail: string };

export const workspaceSkillsAdapter = {
  description: "HAM /api/workspace/skills — list/create/patch/delete items",

  async list(q?: string): Promise<{ skills: WorkspaceSkill[]; bridge: SkillsBridge }> {
    try {
      const url = q?.trim() ? `${BASE}/items?q=${encodeURIComponent(q.trim())}` : `${BASE}/items`;
      const res = await hamApiFetch(url, { credentials: "include" });
      if (!res.ok) return { skills: [], bridge: workspaceApiPending("skills", res) };
      const data = (await res.json()) as { skills?: WorkspaceSkill[] };
      return { skills: Array.isArray(data.skills) ? data.skills : [], bridge: { status: "ready" } };
    } catch (e) {
      return { skills: [], bridge: workspaceApiPending("skills", null, e) };
    }
  },

  async create(
    name: string,
    description: string,
  ): Promise<{ skill: WorkspaceSkill | null; bridge: SkillsBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/items`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ name, description: description || "" }),
      });
      if (!res.ok) return { skill: null, bridge: workspaceApiPending("skills", res), error: `HTTP ${res.status}` };
      return { skill: (await res.json()) as WorkspaceSkill, bridge: { status: "ready" } };
    } catch (e) {
      return { skill: null, bridge: workspaceApiPending("skills", null, e), error: e instanceof Error ? e.message : String(e) };
    }
  },

  async patch(
    id: string,
    body: Partial<{
      name: string;
      description: string;
      installed: boolean;
      enabled: boolean;
      config: string;
    }>,
  ): Promise<{ skill: WorkspaceSkill | null; bridge: SkillsBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/items/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!res.ok) return { skill: null, bridge: workspaceApiPending("skills", res), error: `HTTP ${res.status}` };
      return { skill: (await res.json()) as WorkspaceSkill, bridge: { status: "ready" } };
    } catch (e) {
      return { skill: null, bridge: workspaceApiPending("skills", null, e), error: e instanceof Error ? e.message : String(e) };
    }
  },

  async remove(id: string): Promise<{ ok: boolean; bridge: SkillsBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/items/${encodeURIComponent(id)}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (res.status !== 204) return { ok: false, bridge: workspaceApiPending("skills", res), error: `HTTP ${res.status}` };
      return { ok: true, bridge: { status: "ready" } };
    } catch (e) {
      return { ok: false, bridge: workspaceApiPending("skills", null, e), error: e instanceof Error ? e.message : String(e) };
    }
  },
} as const;
