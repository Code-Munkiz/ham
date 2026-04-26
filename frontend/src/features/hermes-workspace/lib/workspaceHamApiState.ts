/**
 * HAM “advanced” workspace surfaces (Memory, Skills, Profiles, Operations, Conductor, Jobs, Tasks)
 * call the **main HAM API** via `hamApiFetch` / `VITE_HAM_API_BASE` — not the local Files/Terminal
 * runtime. User-facing copy here must not say “runtime bridge” or imply loopback `127.0.0.1` Files.
 */

export type WorkspaceHamApiSurface =
  | "memory"
  | "skills"
  | "profiles"
  | "operations"
  | "conductor"
  | "jobs"
  | "tasks";

const INTRO: Record<WorkspaceHamApiSurface, string> = {
  memory:
    "Workspace Memory is served from the HAM API at /api/workspace/memory (JSON on the server). It does not use the local Files/Terminal connection.",
  skills: "Skills are served from the HAM API at /api/workspace/skills.",
  profiles: "Profiles are served from the HAM API at /api/workspace/profiles.",
  operations: "Operations (agents) are served from the HAM API at /api/workspace/operations.",
  conductor: "Conductor (missions) is served from the HAM API at /api/workspace/conductor.",
  jobs: "Jobs are served from the HAM API at /api/workspace/jobs.",
  tasks: "Tasks are served from the HAM API at /api/workspace/tasks.",
};

function httpSuffix(status: number): string {
  if (status === 401 || status === 403) {
    return `The HAM server returned HTTP ${status}. You may need to sign in, or the session may have expired.`;
  }
  if (status === 404) {
    return "The HAM server returned HTTP 404 — this route is missing on the deployment you are calling, or the request URL is wrong.";
  }
  if (status >= 500) {
    return `The HAM server returned HTTP ${status}. Check your API deployment and logs.`;
  }
  return `The HAM server returned HTTP ${status}.`;
}

function networkSuffix(err: unknown): string {
  const m = err instanceof Error ? err.message : String(err);
  if (m.includes("VITE_HAM_API_BASE")) {
    return m;
  }
  return `Could not reach the HAM API (${m}). In production, set VITE_HAM_API_BASE to your HAM API origin in Vercel and redeploy; in local dev, ensure the Vite dev server proxies /api to FastAPI.`;
}

/**
 * User-facing `bridge.detail` when a `hamApiFetch` list/load fails or a mutation cannot reach
 * a healthy response.
 */
export function workspaceHamApiUnavailableDetail(
  surface: WorkspaceHamApiSurface,
  res: Response | null,
  err?: unknown,
): string {
  const intro = INTRO[surface];
  if (err != null) {
    return `${intro} ${networkSuffix(err)}`;
  }
  if (res != null) {
    return `${intro} ${httpSuffix(res.status)}`;
  }
  return `${intro} Request failed.`;
}

export function workspaceApiPending(
  surface: WorkspaceHamApiSurface,
  res: Response | null,
  err?: unknown,
): { status: "pending"; detail: string } {
  return { status: "pending", detail: workspaceHamApiUnavailableDetail(surface, res, err) };
}
