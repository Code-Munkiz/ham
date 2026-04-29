/**
 * Snapshot Cloud Agent preview card state so session restore / history load can rehydrate the interactive card.
 *
 * Manual QA (same Ham project + API as local dev):
 *
 * 1. Preview persistence — Manual “Preview Agent”: mission card appears → full browser refresh → card still appears
 *    (sessionStorage key `ham_pending_cursor_agent:{session_id}`; session id from active chat).
 *
 * 2. Dismiss persistence — Cloud Agent handoff phrase: card appears → Dismiss → refresh → card stays gone
 *    (snapshot removed; rehydrate finds nothing).
 *
 * 3. Launch + new chat — Successful launch clears pending card and snapshot → New chat → no stale mission card
 *    (startNewChat clears prior session snapshot and `pendingCursorAgent`).
 */

const KEY_PREFIX = "ham_pending_cursor_agent:";

function keyForSession(sessionId: string): string {
  return `${KEY_PREFIX}${sessionId.trim()}`;
}

export function savePendingCursorAgentSessionSnapshot(
  sessionId: string,
  payload: Record<string, unknown> | null,
): void {
  const k = keyForSession(sessionId);
  try {
    if (!payload) {
      sessionStorage.removeItem(k);
      return;
    }
    sessionStorage.setItem(k, JSON.stringify(payload));
  } catch {
    /* ignore quota / private mode */
  }
}

export function loadPendingCursorAgentSessionSnapshot(sessionId: string): Record<string, unknown> | null {
  try {
    const raw = sessionStorage.getItem(keyForSession(sessionId));
    if (!raw?.trim()) return null;
    const v = JSON.parse(raw) as unknown;
    if (typeof v !== "object" || v === null || Array.isArray(v)) return null;
    return v as Record<string, unknown>;
  } catch {
    return null;
  }
}
