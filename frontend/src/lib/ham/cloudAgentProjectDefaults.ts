/**
 * Server-aligned defaults for Cloud Agent preview: project metadata uses the same
 * `cursor_cloud_repository` key as `resolve_cursor_repository_url` in the API.
 * @see src/ham/cursor_agent_workflow.py (_METADATA_REPO_KEY)
 */
import type { ProjectRecord } from "./types";

const CURSOR_CLOUD_REPOSITORY_KEY = "cursor_cloud_repository";

export function getCursorCloudRepository(
  metadata: Record<string, unknown> | undefined,
): string | null {
  if (!metadata) return null;
  const raw = metadata[CURSOR_CLOUD_REPOSITORY_KEY];
  if (typeof raw !== "string") return null;
  const t = raw.trim();
  return t || null;
}

export function getActiveProjectName(
  projects: ProjectRecord[],
  projectId: string | null,
): string | null {
  if (!projectId?.trim()) return null;
  const p = projects.find((x) => x.id === projectId);
  const n = p?.name?.trim();
  return n || null;
}

export function shortDigest(digest: string | undefined, keep = 12): string {
  const d = (digest ?? "").trim();
  if (!d) return "";
  if (d.length <= keep) return d;
  return `${d.slice(0, keep)}…`;
}
