/**
 * Phase 1c: per-user localStorage selection for the active workspace.
 *
 * Pure helpers — no React, no fetch. Tested in isolation.
 *
 * Storage key shape: ``ham.activeWorkspaceId.<userId>``. Per-user keys mean
 * switching Clerk identities (or local-dev → real Clerk in the same browser)
 * does not leak workspace selections across users.
 */

const PREFIX = "ham.activeWorkspaceId.";
const LEGACY_PREFIX = ""; // reserved for future migrations; intentionally empty.

function safeStorage(): Storage | null {
  try {
    if (typeof window === "undefined") return null;
    if (typeof window.localStorage === "undefined") return null;
    return window.localStorage;
  } catch {
    return null;
  }
}

export function activeWorkspaceStorageKey(userId: string): string {
  return `${PREFIX}${userId}`;
}

export function readActiveWorkspaceId(userId: string): string | null {
  if (!userId) return null;
  const ls = safeStorage();
  if (!ls) return null;
  try {
    const raw = ls.getItem(activeWorkspaceStorageKey(userId));
    if (!raw) return null;
    const trimmed = raw.trim();
    return trimmed || null;
  } catch {
    return null;
  }
}

export function writeActiveWorkspaceId(userId: string, workspaceId: string | null): void {
  if (!userId) return;
  const ls = safeStorage();
  if (!ls) return;
  try {
    const key = activeWorkspaceStorageKey(userId);
    if (!workspaceId) {
      ls.removeItem(key);
      return;
    }
    ls.setItem(key, workspaceId);
  } catch {
    /* swallow quota / SecurityError; selection is not critical */
  }
}

export function clearActiveWorkspaceId(userId: string): void {
  writeActiveWorkspaceId(userId, null);
}

// Internal — exported for tests; do not import from feature code.
export const __TEST__ = { PREFIX, LEGACY_PREFIX };
