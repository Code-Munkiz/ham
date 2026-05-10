/**
 * Strictly local frontend workspace UI bypass for Hermes Workspace visual QA without Clerk.
 * Never weakens production: requires Vite DEV + explicit flag + loopback hostname, and yields
 * to a real Clerk session when the user is signed in.
 */
import type { HamMeResponse, HamWorkspaceSummary } from "./workspaceApi";

/** Stable id — mock only; not a backed workspace row unless API bypass matches. */
export const LOCAL_UI_QA_WORKSPACE_ID = "local-dev-workspace";

const LOOPBACK_HOSTNAMES = new Set([
  "localhost",
  "127.0.0.1",
  "::1",
  // IPv6 URL host parsing (uncommon):
  "[::1]",
]);

function envFlagTruthy(v: string | undefined): boolean {
  const t = (v ?? "").trim().toLowerCase();
  return t === "1" || t === "true" || t === "yes" || t === "on";
}

export function isLocalWorkspaceBypassHostnameAllowed(hostname: string): boolean {
  return LOOPBACK_HOSTNAMES.has(hostname.trim().toLowerCase());
}

/** Pure predicate for unit tests — mirrors packaged `import.meta` guards. */
export function localWorkspaceBypassEligible(args: {
  dev: boolean;
  prod: boolean;
  viteFlag: string | undefined;
  hostname: string;
}): boolean {
  if (!args.dev || args.prod) return false;
  if (!envFlagTruthy(args.viteFlag)) return false;
  const h = args.hostname.trim();
  if (!h) return false;
  return isLocalWorkspaceBypassHostnameAllowed(h);
}

/**
 * Frontend-only gate for unauthenticated Hermes Workspace UI QA.
 * False in production builds and off non-loopback hosts.
 */
export function isLocalWorkspaceBypassEnabled(hostnameOverride?: string): boolean {
  const hostname =
    hostnameOverride ??
    (typeof window !== "undefined" && typeof window.location?.hostname === "string"
      ? window.location.hostname
      : "");
  return localWorkspaceBypassEligible({
    dev: Boolean(import.meta.env.DEV),
    prod: Boolean(import.meta.env.PROD),
    viteFlag: import.meta.env.VITE_HAM_LOCAL_DEV_WORKSPACE_BYPASS as string | undefined,
    hostname,
  });
}

export type HostedAuthBypassInput =
  | {
      clerkConfigured?: boolean;
      isSignedIn?: boolean;
    }
  | null
  | undefined;

/**
 * When true, `HamWorkspaceProvider` should hydrate a mock `/api/me`-shaped workspace and skip Clerk gate.
 * Real Clerk signed-in sessions always win.
 */
export function shouldActivateLocalWorkspaceUiBypass(
  hostedAuth: HostedAuthBypassInput,
  hostnameOverride?: string,
): boolean {
  if (!isLocalWorkspaceBypassEnabled(hostnameOverride)) return false;
  const cc = hostedAuth?.clerkConfigured === true;
  const signed = hostedAuth?.isSignedIn === true;
  if (cc && signed) return false;
  return true;
}

export function buildLocalDevWorkspaceMeResponse(nowIso: string): HamMeResponse {
  const ws: HamWorkspaceSummary = {
    workspace_id: LOCAL_UI_QA_WORKSPACE_ID,
    org_id: null,
    name: "ham repo",
    slug: "ham-repo",
    description: "Local UI QA stub — not provisioned workspace data.",
    status: "active",
    role: "owner",
    perms: ["workspace:read", "workspace:write", "workspace:admin"],
    is_default: true,
    created_at: nowIso,
    updated_at: nowIso,
  };
  return {
    user: {
      user_id: "dev-local-user",
      email: null,
      display_name: "Local dev",
      photo_url: null,
      primary_org_id: null,
    },
    orgs: [],
    workspaces: [ws],
    default_workspace_id: ws.workspace_id,
    auth_mode: "local_dev_bypass",
  };
}
