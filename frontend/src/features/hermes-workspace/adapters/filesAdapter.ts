/**
 * `workspaceFileAdapter` — single surface for Files IA. Runtime bridge gaps stay here
 * (no scattered "blocked" copy in feature UI).
 * Upstream reference: `src/components/file-explorer/file-explorer-sidebar.tsx` (`/api/files`).
 */

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
    "Workspace files; Hermes used GET/POST /api/files — HAM may wire later without changing call sites here.",

  /**
   * Lists workspace file tree. On missing endpoint or error, returns empty entries
   * and `bridge: pending` so the UI can keep the full control surface.
   */
  async list(): Promise<{ entries: WorkspaceFileEntry[]; bridge: FileBridgeState }> {
    try {
      const res = await fetch("/api/files?action=list", { credentials: "include" });
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
      const res = await fetch("/api/files", {
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

  async postFormData(form: FormData): Promise<{ ok: boolean; bridge: FileBridgeState; error?: string }> {
    try {
      const res = await fetch("/api/files", {
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
    return `/api/files?action=download&path=${encodeURIComponent(path)}`;
  },

  /** Optional text read for editor/preview. */
  async readText(
    path: string,
  ): Promise<{ text: string | null; bridge: FileBridgeState; error?: string }> {
    try {
      const res = await fetch(
        `/api/files?action=read&path=${encodeURIComponent(path)}`,
        { credentials: "include" },
      );
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
