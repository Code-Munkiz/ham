/**
 * Managed-workspace build smoke preflight gate.
 *
 * Guards the chat → CodingPlanCard → ManagedBuildApprovalPanel → Preview → Approve and build flow
 * against the very narrow but recurring failure where someone (a human, a droid, an automation harness)
 * drives a smoke against a *non-canonical* HAM frontend deployment — typically a stale Vercel preview
 * URL under a different team scope, e.g. `ham-grvil614b-team-clarity.vercel.app`. Such hosts either
 * (a) are gated by Vercel deployment protection, or (b) lack the `/api/*` rewrite to Cloud Run, or
 * both. The user lands on a SPA that *looks* like HAM but cannot reach the backend; the smoke either
 * silently fails or produces misleading state.
 *
 * The preflight enforces, in order:
 *
 *   1. **Host check** — when running on a `*.vercel.app` host, `location.host` must be exactly the
 *      canonical alias (default: `ham-nine-mu.vercel.app`). Any other `*.vercel.app` host fails.
 *      Localhost / loopback / `*.vercel.app` exemption for desktop is handled by the explicit
 *      `mode` argument — see {@link DEFAULT_CANONICAL_HOST}.
 *   2. **Proxy MIME check** — same-origin `GET /api/status` must return HTTP 200 with
 *      `Content-Type: application/json`. A `text/html` response means the Vercel rewrite is missing
 *      and the SPA fallback served `index.html`.
 *   3. **Backend identity check** — the JSON body must contain a string `version`, a non-negative
 *      integer `run_count`, and `capabilities.project_agent_profiles_read === true`. This catches
 *      stubbed `/api/status` responses (e.g., a Vercel edge function returning hand-rolled JSON).
 *   4. **Trace anchor check** — the response must carry the `x-cloud-trace-context` header, which
 *      Google Cloud Run / Google Frontend always emits. Its absence signals the request never
 *      reached Cloud Run.
 *
 * All four checks must pass. The function returns the validated snapshot on success; on failure it
 * throws a {@link SmokePreflightError} whose `code` is one of {@link SmokePreflightFailureCode}, so
 * automation can branch on the structured reason without parsing text.
 *
 * This module performs **no** mutations and **no** writes. Calling it twice is safe; the second call
 * simply re-issues `GET /api/status`.
 *
 * See `docs/HAM_SMOKE_PREFLIGHT.md` for the operator-facing runbook.
 */

/** The single canonical production frontend host. */
export const DEFAULT_CANONICAL_HOST = "ham-nine-mu.vercel.app";

/** Structured failure codes. Stable contract — automation greps for these. */
export type SmokePreflightFailureCode =
  | "SMOKE_PREFLIGHT_STALE_FRONTEND_HOST"
  | "SMOKE_PREFLIGHT_API_PROXY_NOT_ROUTED"
  | "SMOKE_PREFLIGHT_BACKEND_SHAPE_DRIFT"
  | "SMOKE_PREFLIGHT_NO_BACKEND_TRACE"
  | "SMOKE_PREFLIGHT_NETWORK_ERROR";

export class SmokePreflightError extends Error {
  readonly code: SmokePreflightFailureCode;
  constructor(code: SmokePreflightFailureCode, message: string) {
    super(message);
    this.name = "SmokePreflightError";
    this.code = code;
  }
}

export interface SmokePreflightSnapshot {
  readonly host: string;
  readonly statusUrl: string;
  readonly version: string;
  readonly runCount: number;
  readonly traceContext: string;
}

export interface SmokePreflightOptions {
  /**
   * Override the canonical host. Tests pass a custom value; production callers should leave undefined.
   */
  readonly canonicalHost?: string;
  /**
   * Override `window.location` lookup. Tests pass `{ host, origin }`; production callers leave undefined.
   */
  readonly locationOverride?: { host: string; origin: string };
  /**
   * Override `fetch`. Tests pass a stub. Production callers leave undefined.
   */
  readonly fetchImpl?: typeof fetch;
}

function readLocation(opts: SmokePreflightOptions): { host: string; origin: string } | null {
  if (opts.locationOverride) return opts.locationOverride;
  if (typeof window === "undefined" || !window.location) return null;
  return { host: window.location.host, origin: window.location.origin };
}

/**
 * Returns `true` when the host is exempt from the canonical-host equality check.
 *
 * Exemptions:
 *   - localhost / 127.0.0.1 / ::1 (with or without port) — dev / desktop bridge
 *   - empty (non-browser context; the caller already had to opt in)
 *
 * Any other `*.vercel.app` host is NOT exempt — that's the whole point of the gate.
 */
export function isHostExemptFromSmokeCanonicalCheck(host: string): boolean {
  if (!host) return true;
  const lower = host.toLowerCase();
  if (lower.startsWith("[")) {
    const end = lower.indexOf("]");
    if (end < 0) return false;
    const ipv6 = lower.slice(1, end);
    return ipv6 === "::1";
  }
  if (lower === "::1") return true;
  const bare = lower.split(":")[0];
  if (bare === "localhost") return true;
  if (bare === "127.0.0.1") return true;
  return false;
}

interface HamStatusBodyShape {
  version?: unknown;
  run_count?: unknown;
  capabilities?: { project_agent_profiles_read?: unknown } | unknown;
}

function isStringNonEmpty(v: unknown): v is string {
  return typeof v === "string" && v.length > 0;
}

function isNonNegativeInteger(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v) && Number.isInteger(v) && v >= 0;
}

/**
 * Run the four-gate preflight. Resolves with the validated snapshot or throws SmokePreflightError.
 *
 * Idempotent + side-effect-free. Safe to call from any user-initiated action that is about to
 * fire `POST /api/droid/build/preview` or `POST /api/droid/build/launch`.
 */
export async function assertManagedBuildSmokePreflight(
  opts: SmokePreflightOptions = {},
): Promise<SmokePreflightSnapshot> {
  const canonical = (opts.canonicalHost ?? DEFAULT_CANONICAL_HOST).toLowerCase();
  const loc = readLocation(opts);
  const host = (loc?.host ?? "").toLowerCase();

  // 1. host check
  if (host && !isHostExemptFromSmokeCanonicalCheck(host) && host !== canonical) {
    throw new SmokePreflightError(
      "SMOKE_PREFLIGHT_STALE_FRONTEND_HOST",
      `Managed-build smoke must be driven from ${canonical}. Current host is ${host}. ` +
        `Generated Vercel preview URLs (any non-canonical *.vercel.app) are not valid smoke targets.`,
    );
  }

  const fetcher: typeof fetch =
    opts.fetchImpl ?? (typeof fetch === "function" ? fetch.bind(globalThis) : (null as never));
  if (!fetcher) {
    throw new SmokePreflightError(
      "SMOKE_PREFLIGHT_NETWORK_ERROR",
      "No fetch implementation is available in this context.",
    );
  }

  const statusUrl = loc?.origin ? `${loc.origin.replace(/\/+$/, "")}/api/status` : "/api/status";

  let response: Response;
  try {
    response = await fetcher(statusUrl, { method: "GET", credentials: "same-origin" });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new SmokePreflightError(
      "SMOKE_PREFLIGHT_NETWORK_ERROR",
      `GET ${statusUrl} failed before an HTTP response: ${msg}`,
    );
  }

  // 2. proxy MIME check
  const contentType = (response.headers.get("content-type") || "").toLowerCase();
  if (!response.ok || !contentType.includes("application/json")) {
    throw new SmokePreflightError(
      "SMOKE_PREFLIGHT_API_PROXY_NOT_ROUTED",
      `GET ${statusUrl} returned HTTP ${response.status} with content-type "${contentType || "(none)"}". ` +
        `Expected 200 application/json. The Vercel rewrite to Cloud Run is likely missing on this deployment.`,
    );
  }

  // 3. backend identity check
  let body: HamStatusBodyShape;
  try {
    body = (await response.json()) as HamStatusBodyShape;
  } catch {
    throw new SmokePreflightError(
      "SMOKE_PREFLIGHT_BACKEND_SHAPE_DRIFT",
      `GET ${statusUrl} did not return valid JSON.`,
    );
  }
  if (!isStringNonEmpty(body.version)) {
    throw new SmokePreflightError(
      "SMOKE_PREFLIGHT_BACKEND_SHAPE_DRIFT",
      `${statusUrl}: missing or non-string \`version\`.`,
    );
  }
  if (!isNonNegativeInteger(body.run_count)) {
    throw new SmokePreflightError(
      "SMOKE_PREFLIGHT_BACKEND_SHAPE_DRIFT",
      `${statusUrl}: missing or non-integer \`run_count\`.`,
    );
  }
  const caps =
    body.capabilities && typeof body.capabilities === "object"
      ? (body.capabilities as { project_agent_profiles_read?: unknown })
      : null;
  if (!caps || caps.project_agent_profiles_read !== true) {
    throw new SmokePreflightError(
      "SMOKE_PREFLIGHT_BACKEND_SHAPE_DRIFT",
      `${statusUrl}: missing \`capabilities.project_agent_profiles_read === true\`. ` +
        `Cloud Run image is older than required.`,
    );
  }

  // 4. trace anchor check
  const trace = response.headers.get("x-cloud-trace-context");
  if (!isStringNonEmpty(trace)) {
    throw new SmokePreflightError(
      "SMOKE_PREFLIGHT_NO_BACKEND_TRACE",
      `${statusUrl}: response did not carry an x-cloud-trace-context header. ` +
        `That header is set by Google Frontend / Cloud Run; its absence means the request did not reach the backend.`,
    );
  }

  return {
    host,
    statusUrl,
    version: body.version,
    runCount: body.run_count,
    traceContext: trace,
  };
}
