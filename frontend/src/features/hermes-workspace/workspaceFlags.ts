/**
 * Feature flag: namespaced Hermes Workspace lift (`/workspace/*`).
 * - **Production (`vite build`)**: when unset, workspace is **on** so `/chat` can redirect
 *   to `/workspace` without Vercel env. Set `VITE_ENABLE_HERMES_WORKSPACE=false` to use legacy `/chat`.
 * - **Local dev**: default **off**; set `VITE_ENABLE_HERMES_WORKSPACE=true` in `.env.local`.
 */
export function isHermesWorkspaceEnabled(): boolean {
  const v = import.meta.env.VITE_ENABLE_HERMES_WORKSPACE;
  if (v === undefined || v === "") {
    return import.meta.env.PROD;
  }
  const s = String(v).toLowerCase().trim();
  if (s === "0" || s === "false" || s === "no" || s === "off") {
    return false;
  }
  return s === "1" || s === "true" || s === "yes" || s === "on";
}
