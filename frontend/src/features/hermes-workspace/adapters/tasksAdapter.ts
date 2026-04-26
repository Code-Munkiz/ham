/**
 * HAM /api/workspace/tasks + /summary — Kanban-friendly task store (no upstream Hermes calls).
 */

import { hamApiFetch } from "@/lib/ham/api";

const BASE = "/api/workspace/tasks";

export type TaskStatus = "todo" | "in_progress" | "done";

export type WorkspaceTask = {
  id: string;
  title: string;
  body: string;
  status: TaskStatus;
  dueAt: string | null;
  createdAt: number;
  updatedAt: number;
};

export type TaskSummary = {
  total: number;
  inProgress: number;
  overdue: number;
  done: number;
  donePercent: number;
};

export type TasksBridge = { status: "ready" } | { status: "pending"; detail: string };

const PENDING: TasksBridge = { status: "pending", detail: "Runtime bridge pending" };

async function readJson<T>(res: Response): Promise<T> {
  return (await res.json()) as T;
}

function qs(p: Record<string, string | boolean | undefined>): string {
  const u = new URLSearchParams();
  Object.entries(p).forEach(([k, v]) => {
    if (v === undefined || v === "") return;
    u.set(k, String(v));
  });
  const s = u.toString();
  return s ? `?${s}` : "";
}

export const workspaceTasksAdapter = {
  description: "HAM /api/workspace/tasks — summary, list, create, patch, delete",

  async summary(): Promise<{ summary: TaskSummary | null; bridge: TasksBridge }> {
    try {
      const res = await hamApiFetch(`${BASE}/summary`, { credentials: "include" });
      if (!res.ok) return { summary: null, bridge: PENDING };
      return { summary: (await res.json()) as TaskSummary, bridge: { status: "ready" } };
    } catch {
      return { summary: null, bridge: PENDING };
    }
  },

  async list(options: {
    q?: string;
    status?: TaskStatus;
    includeDone?: boolean;
  } = {}): Promise<{ tasks: WorkspaceTask[]; bridge: TasksBridge }> {
    try {
      const res = await hamApiFetch(
        `${BASE}${qs({
          q: options.q,
          status: options.status,
          includeDone: options.includeDone,
        })}`,
        { credentials: "include" },
      );
      if (!res.ok) return { tasks: [], bridge: PENDING };
      const data = await readJson<{ tasks?: WorkspaceTask[] }>(res);
      return { tasks: Array.isArray(data.tasks) ? data.tasks : [], bridge: { status: "ready" } };
    } catch {
      return { tasks: [], bridge: PENDING };
    }
  },

  async create(
    title: string,
    body: string,
    status: TaskStatus,
    dueAt?: string | null,
  ): Promise<{ task: WorkspaceTask | null; bridge: TasksBridge; error?: string }> {
    try {
      const res = await hamApiFetch(BASE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          title,
          body: body || "",
          status,
          dueAt: dueAt || null,
        }),
      });
      if (!res.ok) return { task: null, bridge: PENDING, error: `HTTP ${res.status}` };
      return { task: (await res.json()) as WorkspaceTask, bridge: { status: "ready" } };
    } catch (e) {
      return { task: null, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },

  async patch(
    id: string,
    body: { title?: string; body?: string; status?: TaskStatus; dueAt?: string | null },
  ): Promise<{ task: WorkspaceTask | null; bridge: TasksBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/${encodeURIComponent(id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!res.ok) return { task: null, bridge: PENDING, error: `HTTP ${res.status}` };
      return { task: (await res.json()) as WorkspaceTask, bridge: { status: "ready" } };
    } catch (e) {
      return { task: null, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },

  async delete(id: string): Promise<{ ok: boolean; bridge: TasksBridge; error?: string }> {
    try {
      const res = await hamApiFetch(`${BASE}/${encodeURIComponent(id)}`, { method: "DELETE", credentials: "include" });
      if (res.status !== 204) return { ok: false, bridge: PENDING, error: `HTTP ${res.status}` };
      return { ok: true, bridge: { status: "ready" } };
    } catch (e) {
      return { ok: false, bridge: PENDING, error: e instanceof Error ? e.message : String(e) };
    }
  },
} as const;
