/**
 * `VITE_ENABLE_HERMES_WORKSPACE` — optional; reserved for non-routing toggles (nav defaults, experiments).
 * **Product chat route is always `/workspace/chat`.** `/chat` redirects there; legacy full workbench: `/legacy-chat`.
 */
export function isHermesWorkspaceEnabled(): boolean {
  const v = import.meta.env.VITE_ENABLE_HERMES_WORKSPACE;
  const s = String(v ?? "").toLowerCase().trim();
  return s === "1" || s === "true" || s === "yes" || s === "on";
}

/** In-app “open chat” — always the Workspace chat surface. */
export function primaryChatPath(): string {
  return "/workspace/chat";
}
