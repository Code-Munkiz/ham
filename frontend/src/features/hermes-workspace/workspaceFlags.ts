/**
 * Feature flag: namespaced Hermes Workspace lift (`/workspace/*`).
 * Set in `frontend/.env.local` for dev: VITE_ENABLE_HERMES_WORKSPACE=true
 */
export function isHermesWorkspaceEnabled(): boolean {
  const v = import.meta.env.VITE_ENABLE_HERMES_WORKSPACE;
  if (v === undefined || v === "") return false;
  const s = String(v).toLowerCase().trim();
  return s === "1" || s === "true" || s === "yes";
}
