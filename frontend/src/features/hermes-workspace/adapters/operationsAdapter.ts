/**
 * HAM /api/workspace/operations — JSON-backed agent cards (no upstream calls).
 */

import { hamApiFetch } from "@/lib/ham/api";

const BASE = "/api/workspace/operations";

export type AgentStatus = "idle" | "active" | "paused" | "error";

export type AgentOutputLine = { at: number; line: string };

export type WorkspaceAgent = {
  id: string;
  name: string;
  model: string;
  emoji: string;
  systemPrompt: string;
  status: AgentStatus;
  cronEnabled: boolean;
  cronExpr: string;
  outputs: AgentOutputLine[];
  createdAt: number;
  updatedAt: number;
};

export type ScheduledJob = {
  id: string;
  name: string;
  cronExpr: string;
  enabled: boolean;
  createdAt: number;
  updatedAt: number;
};

export type OperationsSettings = {
  defaultModel: string;
  outputsRetention: number;
  notes: string;
};

export type OperationsBridge = { status: "ready" } | { status: "pending"; detail: string };

const PENDING: OperationsBridge = { status: "pending", detail: "Runtime bridge pending" };

async function readJson<T>(res: Response): Promise<T> {
  return (await res.json()) as T;
}

export const workspaceOperationsAdapter = {
  description: "HAM /api/workspace/operations — agents, scheduled jobs, settings",

  async listAgents(): Promise<{ agents: WorkspaceAgent[]; bridge: OperationsBridge }> {
    try {
      const res = await hamApiFetch(`${BASE}/agents`, { credentials: "include" });
      if (!res.ok) return { agents: [], bridge: PENDING };
      const data = await readJson<{ agents?: WorkspaceAgent[] }>(res);
      return { agents: Array.isArray(data.agents) ? data.agents : [], bridge: { status: "ready" } };
    } catch {
      return { agents: [], bridge: PENDING };
    }
  },

  async createAgent(
    name: string,
    model: string,
    opts?: { emoji?: string; systemPrompt?: string },
  ): Promise<{ agent: WorkspaceAgent | null; bridge: OperationsBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/agents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          name,
          model: model || "ham-local",
          emoji: opts?.emoji,
          systemPrompt: opts?.systemPrompt,
        }),
      });
      if (!res.ok) return { agent: null, bridge: PENDING, error: `HTTP ${res.status}` };
      return { agent: (await res.json()) as WorkspaceAgent, bridge: { status: "ready" } };
    } catch (e) {
      return { agent: null, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },

  async patchAgent(
    id: string,
    body: Partial<{
      name: string;
      model: string;
      emoji: string;
      systemPrompt: string;
      cronEnabled: boolean;
      cronExpr: string;
    }>,
  ): Promise<{ agent: WorkspaceAgent | null; bridge: OperationsBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/agents/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!res.ok) return { agent: null, bridge: PENDING, error: `HTTP ${res.status}` };
      return { agent: (await res.json()) as WorkspaceAgent, bridge: { status: "ready" } };
    } catch (e) {
      return { agent: null, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },

  async deleteAgent(id: string): Promise<{ ok: boolean; bridge: OperationsBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/agents/${encodeURIComponent(id)}`, { method: "DELETE", credentials: "include" });
      if (res.status !== 204) return { ok: false, bridge: PENDING, error: `HTTP ${res.status}` };
      return { ok: true, bridge: { status: "ready" } };
    } catch (e) {
      return { ok: false, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },

  async play(id: string): Promise<{ agent: WorkspaceAgent | null; bridge: OperationsBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/agents/${encodeURIComponent(id)}/play`, { method: "POST", credentials: "include" });
      if (!res.ok) return { agent: null, bridge: PENDING, error: (await res.text()) || `HTTP ${res.status}` };
      return { agent: (await res.json()) as WorkspaceAgent, bridge: { status: "ready" } };
    } catch (e) {
      return { agent: null, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },

  async pause(id: string): Promise<{ agent: WorkspaceAgent | null; bridge: OperationsBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/agents/${encodeURIComponent(id)}/pause`, { method: "POST", credentials: "include" });
      if (!res.ok) return { agent: null, bridge: PENDING, error: (await res.text()) || `HTTP ${res.status}` };
      return { agent: (await res.json()) as WorkspaceAgent, bridge: { status: "ready" } };
    } catch (e) {
      return { agent: null, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },

  async appendMessage(
    id: string,
    message: string,
  ): Promise<{ agent: WorkspaceAgent | null; bridge: OperationsBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/agents/${encodeURIComponent(id)}/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ message }),
      });
      if (!res.ok) return { agent: null, bridge: PENDING, error: (await res.text()) || `HTTP ${res.status}` };
      return { agent: (await res.json()) as WorkspaceAgent, bridge: { status: "ready" } };
    } catch (e) {
      return { agent: null, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },

  async listScheduled(): Promise<{ jobs: ScheduledJob[]; bridge: OperationsBridge }> {
    try {
      const res = await hamApiFetch(`${BASE}/scheduled-jobs`, { credentials: "include" });
      if (!res.ok) return { jobs: [], bridge: PENDING };
      const data = await readJson<{ scheduledJobs?: ScheduledJob[] }>(res);
      return { jobs: Array.isArray(data.scheduledJobs) ? data.scheduledJobs : [], bridge: { status: "ready" } };
    } catch {
      return { jobs: [], bridge: PENDING };
    }
  },

  async createScheduled(
    name: string,
    cronExpr: string,
  ): Promise<{ job: ScheduledJob | null; bridge: OperationsBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/scheduled-jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ name, cronExpr, enabled: true }),
      });
      if (!res.ok) return { job: null, bridge: PENDING, error: `HTTP ${res.status}` };
      return { job: (await res.json()) as ScheduledJob, bridge: { status: "ready" } };
    } catch (e) {
      return { job: null, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },

  async deleteScheduled(id: string): Promise<{ ok: boolean; bridge: OperationsBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/scheduled-jobs/${encodeURIComponent(id)}`, { method: "DELETE", credentials: "include" });
      if (res.status !== 204) return { ok: false, bridge: PENDING, error: `HTTP ${res.status}` };
      return { ok: true, bridge: { status: "ready" } };
    } catch (e) {
      return { ok: false, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },

  async patchScheduled(
    id: string,
    body: Partial<Pick<ScheduledJob, "name" | "cronExpr" | "enabled">>,
  ): Promise<{ job: ScheduledJob | null; bridge: OperationsBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/scheduled-jobs/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!res.ok) return { job: null, bridge: PENDING, error: `HTTP ${res.status}` };
      return { job: (await res.json()) as ScheduledJob, bridge: { status: "ready" } };
    } catch (e) {
      return { job: null, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },

  async getSettings(): Promise<{ settings: OperationsSettings | null; bridge: OperationsBridge }> {
    try {
      const res = await hamApiFetch(`${BASE}/settings`, { credentials: "include" });
      if (!res.ok) return { settings: null, bridge: PENDING };
      const data = await readJson<{ settings?: OperationsSettings }>(res);
      return { settings: data.settings ?? null, bridge: { status: "ready" } };
    } catch {
      return { settings: null, bridge: PENDING };
    }
  },

  async patchSettings(
    body: Partial<Pick<OperationsSettings, "defaultModel" | "outputsRetention" | "notes">>,
  ): Promise<{ settings: OperationsSettings | null; bridge: OperationsBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!res.ok) return { settings: null, bridge: PENDING, error: `HTTP ${res.status}` };
      const data = await readJson<{ settings?: OperationsSettings }>(res);
      return { settings: data.settings ?? null, bridge: { status: "ready" } };
    } catch (e) {
      return { settings: null, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },
} as const;
