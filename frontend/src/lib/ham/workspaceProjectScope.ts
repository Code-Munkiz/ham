import type { ProjectRecord } from "@/lib/ham/types";

export function workspaceIdFromProjectRecord(rec: ProjectRecord): string | null {
  const top = rec.workspace_id;
  if (typeof top === "string" && top.trim()) return top.trim();
  const meta = rec.metadata ?? {};
  const metaDirect =
    typeof meta.workspace_id === "string"
      ? meta.workspace_id.trim()
      : typeof meta.workspaceId === "string"
        ? meta.workspaceId.trim()
        : "";
  if (metaDirect) return metaDirect;
  return null;
}

export function projectRecordsHaveWorkspaceBinding(projects: ProjectRecord[]): boolean {
  return projects.some((p) => Boolean(workspaceIdFromProjectRecord(p)));
}

/**
 * Picks exactly one project for the workspace: preferred id if scoped, otherwise a
 * deterministic default when multiple or single scope match.
 */
export function pickWorkspaceScopedProjectId(
  workspaceId: string,
  projects: ProjectRecord[],
  preferredId: string | null | undefined,
): string | null {
  const ws = workspaceId.trim();
  if (!ws) return null;

  const scoped = projects.filter((p) => workspaceIdFromProjectRecord(p) === ws);
  const scopedIds = new Set(scoped.map((p) => p.id));
  const pid = preferredId?.trim();

  if (!scoped.length) return null;

  if (pid && scopedIds.has(pid)) return pid;
  if (scoped.length === 1) return scoped[0]!.id;
  const sorted = [...scoped].sort((a, b) => a.id.localeCompare(b.id));
  return sorted[0]!.id;
}

/** Stable `{ workspace_id, project_id }` pairing for cancelling stale polling. */
export function workspaceProjectScope(workspaceId?: string | null, projectId?: string | null): string {
  return `${(workspaceId ?? "").trim()}|${(projectId ?? "").trim()}`;
}

export function workspaceProjectScopesMatch(a: string, b: string): boolean {
  return a === b;
}

/**
 * Abort applying async results when hooks still point at a **different**
 * `{ workspaceId, projectId }` than when the operation started.
 */
export function ignoreStaleWorkbenchScope(params: {
  started: string;
  currentWorkspaceId?: string | null;
  currentProjectId?: string | null;
}): boolean {
  return workspaceProjectScope(params.currentWorkspaceId, params.currentProjectId) !== params.started;
}
