/**
 * Feature flag: namespaced Hermes Workspace lift (`/workspace/*`).
 *
 * **Workspace is off unless explicitly enabled** (any environment). Set
 * `VITE_ENABLE_HERMES_WORKSPACE=true` in `.env.local` (dev) or your host env (Vercel) and rebuild.
 *
 * When disabled, `/chat` stays the legacy `Chat` workbench; `/workspace/*` redirects to `/chat`.
 * When enabled, `App` routes `/chat` and `/chat?session=…` → `/workspace/chat` (same search); `primaryChatPath()` is `/workspace/chat`.
 */
export function isHermesWorkspaceEnabled(): boolean {
  const v = import.meta.env.VITE_ENABLE_HERMES_WORKSPACE;
  const s = String(v ?? "").toLowerCase().trim();
  return s === "1" || s === "true" || s === "yes" || s === "on";
}

/** In-app “open chat” target: Workspace chat when the lift is on, else legacy `/chat`. */
export function primaryChatPath(): string {
  return isHermesWorkspaceEnabled() ? "/workspace/chat" : "/chat";
}
