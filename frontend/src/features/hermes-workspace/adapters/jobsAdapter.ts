/**
 * HAM /api/workspace/jobs — JSON-backed job list with run history (no upstream Hermes calls).
 */

const BASE = "/api/workspace/jobs";

export type JobRun = {
  id: string;
  startedAt: number;
  finishedAt: number;
  status: "ok" | "error" | "cancelled";
  output: string;
};

export type WorkspaceJob = {
  id: string;
  name: string;
  description: string;
  status: "idle" | "running" | "paused" | "failed";
  createdAt: number;
  updatedAt: number;
  runs: JobRun[];
};

export type JobsBridge = { status: "ready" } | { status: "pending"; detail: string };

const PENDING: JobsBridge = { status: "pending", detail: "Runtime bridge pending" };

async function readJson<T>(res: Response): Promise<T> {
  return (await res.json()) as T;
}

export const workspaceJobsAdapter = {
  description: "HAM /api/workspace/jobs — list/create/patch/run/pause/resume/delete",

  async list(q?: string): Promise<{ jobs: WorkspaceJob[]; bridge: JobsBridge }> {
    try {
      const url = q?.trim() ? `${BASE}?q=${encodeURIComponent(q.trim())}` : BASE;
      const res = await fetch(url, { credentials: "include" });
      if (!res.ok) return { jobs: [], bridge: PENDING };
      const data = await readJson<{ jobs?: WorkspaceJob[] }>(res);
      return { jobs: Array.isArray(data.jobs) ? data.jobs : [], bridge: { status: "ready" } };
    } catch {
      return { jobs: [], bridge: PENDING };
    }
  },

  async create(name: string, description: string): Promise<{ job: WorkspaceJob | null; bridge: JobsBridge; error?: string }> {
    try {
      const res = await fetch(BASE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ name, description: description || "" }),
      });
      if (!res.ok) return { job: null, bridge: PENDING, error: `HTTP ${res.status}` };
      const job = (await res.json()) as WorkspaceJob;
      return { job, bridge: { status: "ready" } };
    } catch (e) {
      return { job: null, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },

  async patch(
    id: string,
    body: { name?: string; description?: string },
  ): Promise<{ job: WorkspaceJob | null; bridge: JobsBridge; error?: string }> {
    try {
      const res = await fetch(`${BASE}/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!res.ok) return { job: null, bridge: PENDING, error: `HTTP ${res.status}` };
      return { job: (await res.json()) as WorkspaceJob, bridge: { status: "ready" } };
    } catch (e) {
      return { job: null, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },

  async run(id: string): Promise<{ job: WorkspaceJob | null; bridge: JobsBridge; error?: string }> {
    try {
      const res = await fetch(`${BASE}/${encodeURIComponent(id)}/run`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) return { job: null, bridge: PENDING, error: (await res.text()) || `HTTP ${res.status}` };
      return { job: (await res.json()) as WorkspaceJob, bridge: { status: "ready" } };
    } catch (e) {
      return { job: null, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },

  async pause(id: string): Promise<{ job: WorkspaceJob | null; bridge: JobsBridge; error?: string }> {
    try {
      const res = await fetch(`${BASE}/${encodeURIComponent(id)}/pause`, { method: "POST", credentials: "include" });
      if (!res.ok) return { job: null, bridge: PENDING, error: (await res.text()) || `HTTP ${res.status}` };
      return { job: (await res.json()) as WorkspaceJob, bridge: { status: "ready" } };
    } catch (e) {
      return { job: null, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },

  async resume(id: string): Promise<{ job: WorkspaceJob | null; bridge: JobsBridge; error?: string }> {
    try {
      const res = await fetch(`${BASE}/${encodeURIComponent(id)}/resume`, { method: "POST", credentials: "include" });
      if (!res.ok) return { job: null, bridge: PENDING, error: (await res.text()) || `HTTP ${res.status}` };
      return { job: (await res.json()) as WorkspaceJob, bridge: { status: "ready" } };
    } catch (e) {
      return { job: null, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },

  async delete(id: string): Promise<{ ok: boolean; bridge: JobsBridge; error?: string }> {
    try {
      const res = await fetch(`${BASE}/${encodeURIComponent(id)}`, { method: "DELETE", credentials: "include" });
      if (res.status !== 204) return { ok: false, bridge: PENDING, error: `HTTP ${res.status}` };
      return { ok: true, bridge: { status: "ready" } };
    } catch (e) {
      return { ok: false, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },
} as const;
