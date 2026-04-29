/**
 * HAM /api/workspace/conductor — JSON-backed missions (no upstream Hermes calls).
 */

import { hamApiFetch } from "@/lib/ham/api";

import { workspaceApiPending } from "../lib/workspaceHamApiState";

const BASE = "/api/workspace/conductor";

export type MissionPhase = "draft" | "running" | "completed" | "failed";
export type QuickAction = "research" | "build" | "review" | "deploy";

export type MissionOutputLine = { at: number; line: string };

export type WorkspaceMission = {
  id: string;
  title: string;
  body: string;
  phase: MissionPhase;
  quickAction: string | null;
  outputs: MissionOutputLine[];
  costCents: number;
  createdAt: number;
  updatedAt: number;
};

export type ConductorSettings = {
  budgetCents: number;
  defaultModel: string;
  notes: string;
};

export type ConductorBridge = { status: "ready" } | { status: "pending"; detail: string };

async function readJson<T>(res: Response): Promise<T> {
  return (await res.json()) as T;
}

export const workspaceConductorAdapter = {
  description: "HAM /api/workspace/conductor — missions, quick presets, run, settings",

  async list(params?: {
    q?: string;
    phase?: MissionPhase;
    historyOnly?: boolean;
  }): Promise<{ missions: WorkspaceMission[]; bridge: ConductorBridge }> {
    try {
      const sp = new URLSearchParams();
      if (params?.q?.trim()) sp.set("q", params.q.trim());
      if (params?.phase) sp.set("phase", params.phase);
      if (params?.historyOnly) sp.set("historyOnly", "true");
      const q = sp.toString();
      const res = await hamApiFetch(q ? `${BASE}/missions?${q}` : `${BASE}/missions`, { credentials: "include" });
      if (!res.ok) return { missions: [], bridge: workspaceApiPending("conductor", res) };
      const data = await readJson<{ missions?: WorkspaceMission[] }>(res);
      return { missions: Array.isArray(data.missions) ? data.missions : [], bridge: { status: "ready" } };
    } catch (e) {
      return { missions: [], bridge: workspaceApiPending("conductor", null, e) };
    }
  },

  async create(
    title: string,
    body: string,
    quickAction?: QuickAction | null,
  ): Promise<{ mission: WorkspaceMission | null; bridge: ConductorBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/missions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ title, body: body || "", quickAction: quickAction ?? null }),
      });
      if (!res.ok) return { mission: null, bridge: workspaceApiPending("conductor", res), error: `HTTP ${res.status}` };
      return { mission: (await res.json()) as WorkspaceMission, bridge: { status: "ready" } };
    } catch (e) {
      return { mission: null, bridge: workspaceApiPending("conductor", null, e), error: e instanceof Error ? e.message : String(e) };
    }
  },

  async createQuick(
    quick: QuickAction,
    title?: string,
  ): Promise<{ mission: WorkspaceMission | null; bridge: ConductorBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/missions/quick`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ quick, title: title || null }),
      });
      if (!res.ok) return { mission: null, bridge: workspaceApiPending("conductor", res), error: `HTTP ${res.status}` };
      return { mission: (await res.json()) as WorkspaceMission, bridge: { status: "ready" } };
    } catch (e) {
      return { mission: null, bridge: workspaceApiPending("conductor", null, e), error: e instanceof Error ? e.message : String(e) };
    }
  },

  async patch(
    id: string,
    body: Partial<{ title: string; body: string; phase: MissionPhase; quickAction: QuickAction | null }>,
  ): Promise<{ mission: WorkspaceMission | null; bridge: ConductorBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/missions/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!res.ok) return { mission: null, bridge: workspaceApiPending("conductor", res), error: `HTTP ${res.status}` };
      return { mission: (await res.json()) as WorkspaceMission, bridge: { status: "ready" } };
    } catch (e) {
      return { mission: null, bridge: workspaceApiPending("conductor", null, e), error: e instanceof Error ? e.message : String(e) };
    }
  },

  async run(id: string): Promise<{ mission: WorkspaceMission | null; bridge: ConductorBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/missions/${encodeURIComponent(id)}/run`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) return { mission: null, bridge: workspaceApiPending("conductor", res), error: (await res.text()) || `HTTP ${res.status}` };
      return { mission: (await res.json()) as WorkspaceMission, bridge: { status: "ready" } };
    } catch (e) {
      return { mission: null, bridge: workspaceApiPending("conductor", null, e), error: e instanceof Error ? e.message : String(e) };
    }
  },

  async fail(id: string): Promise<{ mission: WorkspaceMission | null; bridge: ConductorBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/missions/${encodeURIComponent(id)}/fail`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) return { mission: null, bridge: workspaceApiPending("conductor", res), error: `HTTP ${res.status}` };
      return { mission: (await res.json()) as WorkspaceMission, bridge: { status: "ready" } };
    } catch (e) {
      return { mission: null, bridge: workspaceApiPending("conductor", null, e), error: e instanceof Error ? e.message : String(e) };
    }
  },

  async appendOutput(
    id: string,
    line: string,
  ): Promise<{ mission: WorkspaceMission | null; bridge: ConductorBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/missions/${encodeURIComponent(id)}/output`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ line }),
      });
      if (!res.ok) return { mission: null, bridge: workspaceApiPending("conductor", res), error: `HTTP ${res.status}` };
      return { mission: (await res.json()) as WorkspaceMission, bridge: { status: "ready" } };
    } catch (e) {
      return { mission: null, bridge: workspaceApiPending("conductor", null, e), error: e instanceof Error ? e.message : String(e) };
    }
  },

  async delete(id: string): Promise<{ ok: boolean; bridge: ConductorBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/missions/${encodeURIComponent(id)}`, { method: "DELETE", credentials: "include" });
      if (res.status !== 204) return { ok: false, bridge: workspaceApiPending("conductor", res), error: `HTTP ${res.status}` };
      return { ok: true, bridge: { status: "ready" } };
    } catch (e) {
      return { ok: false, bridge: workspaceApiPending("conductor", null, e), error: e instanceof Error ? e.message : String(e) };
    }
  },

  async getSettings(): Promise<{ settings: ConductorSettings | null; bridge: ConductorBridge }> {
    try {
      const res = await hamApiFetch(`${BASE}/settings`, { credentials: "include" });
      if (!res.ok) return { settings: null, bridge: workspaceApiPending("conductor", res) };
      const data = await readJson<{ settings?: ConductorSettings }>(res);
      return { settings: data.settings ?? null, bridge: { status: "ready" } };
    } catch (e) {
      return { settings: null, bridge: workspaceApiPending("conductor", null, e) };
    }
  },

  async patchSettings(
    body: Partial<Pick<ConductorSettings, "budgetCents" | "defaultModel" | "notes">>,
  ): Promise<{ settings: ConductorSettings | null; bridge: ConductorBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!res.ok) return { settings: null, bridge: workspaceApiPending("conductor", res), error: `HTTP ${res.status}` };
      const data = await readJson<{ settings?: ConductorSettings }>(res);
      return { settings: data.settings ?? null, bridge: { status: "ready" } };
    } catch (e) {
      return { settings: null, bridge: workspaceApiPending("conductor", null, e), error: e instanceof Error ? e.message : String(e) };
    }
  },
} as const;
