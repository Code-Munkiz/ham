import type { BuilderSourceSnapshotRecord } from "@/lib/ham/api";
import { sanitizeWorkbenchProjectAccessMessage } from "@/lib/ham/workbenchProjectMessages";

/**
 * Lane A saved versions use builder `source_snapshots` only (Workbench/Code tab source of truth).
 * Managed project snapshots and other versioning stores are out of scope for this UI.
 */

const FORBIDDEN_SAVED_VERSIONS_COPY =
  /\bssnp_[\w-]+\b|builder-artifact|controlplanerun|safe_edit_low|runner url|digest_sha256|artifact_uri/i;

export function sortSavedVersionsNewestFirst(
  rows: BuilderSourceSnapshotRecord[],
): BuilderSourceSnapshotRecord[] {
  return [...rows].sort((a, b) => {
    const aMs = Date.parse(a.created_at || "");
    const bMs = Date.parse(b.created_at || "");
    if (Number.isFinite(aMs) && Number.isFinite(bMs)) return bMs - aMs;
    if (Number.isFinite(bMs)) return 1;
    if (Number.isFinite(aMs)) return -1;
    return 0;
  });
}

export function savedVersionFileCount(snapshot: BuilderSourceSnapshotRecord): number | null {
  const manifest = snapshot.manifest || {};
  const fileCount = manifest.file_count;
  if (typeof fileCount === "number" && Number.isFinite(fileCount) && fileCount >= 0) {
    return fileCount;
  }
  const entries = manifest.entries;
  if (Array.isArray(entries)) {
    const fileRows = entries.filter(
      (entry) =>
        entry &&
        typeof entry === "object" &&
        typeof (entry as { path?: unknown }).path === "string" &&
        (entry as { path: string }).path.trim().length > 0,
    );
    return fileRows.length > 0 ? fileRows.length : null;
  }
  return null;
}

export function savedVersionLabel(
  snapshot: BuilderSourceSnapshotRecord,
  options: { isCurrent?: boolean; sequence: number },
): string {
  if (options.isCurrent) return "Current saved version";
  const metadata = snapshot.metadata || {};
  const operation =
    typeof metadata.chat_scaffold_operation === "string"
      ? metadata.chat_scaffold_operation.trim().toLowerCase()
      : "";
  if (operation === "edit") return "Edited saved version";
  if (options.sequence === 1) return "Latest saved version";
  return "Saved version";
}

export function formatSavedVersionCreatedAt(iso: string): string {
  const ms = Date.parse(iso || "");
  if (!Number.isFinite(ms)) return "Created date unavailable";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(ms));
}

export function savedVersionFilesChangedCopy(count: number | null): string | null {
  if (count == null) return null;
  return count === 1 ? "1 file" : `${count} files`;
}

export function sanitizeSavedVersionsErrorMessage(raw: string | null | undefined): string {
  const sanitized = sanitizeWorkbenchProjectAccessMessage(String(raw || "").trim());
  if (!sanitized || FORBIDDEN_SAVED_VERSIONS_COPY.test(sanitized)) {
    return "Could not load saved versions right now. Try again in a moment.";
  }
  return sanitized;
}

export function savedVersionsCopyLooksSafe(text: string): boolean {
  return !FORBIDDEN_SAVED_VERSIONS_COPY.test(text);
}
