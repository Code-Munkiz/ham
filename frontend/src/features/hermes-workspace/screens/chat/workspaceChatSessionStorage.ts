const LEGACY_LAST_SESSION_KEY = "hww.chat.lastSessionId";
const WORKSPACE_LAST_SESSION_KEY_PREFIX = "hww.chat.lastSessionId.";

function normalizedWorkspaceId(workspaceId: string | null | undefined): string | null {
  const wid = workspaceId?.trim();
  return wid ? wid : null;
}

export function workspaceLastSessionStorageKey(workspaceId: string | null | undefined): string {
  const wid = normalizedWorkspaceId(workspaceId);
  return wid ? `${WORKSPACE_LAST_SESSION_KEY_PREFIX}${wid}` : LEGACY_LAST_SESSION_KEY;
}

export function readWorkspaceLastChatSessionId(workspaceId: string | null | undefined): string | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(workspaceLastSessionStorageKey(workspaceId));
    return raw?.trim() ? raw.trim() : null;
  } catch {
    return null;
  }
}

export function writeWorkspaceLastChatSessionId(
  workspaceId: string | null | undefined,
  sessionId: string | null,
): void {
  if (typeof window === "undefined") return;
  try {
    const key = workspaceLastSessionStorageKey(workspaceId);
    if (sessionId?.trim()) {
      window.localStorage.setItem(key, sessionId.trim());
    } else {
      window.localStorage.removeItem(key);
    }
  } catch {
    /* ignore */
  }
}
