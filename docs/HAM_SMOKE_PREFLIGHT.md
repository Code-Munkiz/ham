# HAM managed-workspace smoke preflight

## Canonical production frontend

```
https://ham-nine-mu.vercel.app/
```

This is the only frontend host valid for managed-workspace build smokes (the
chat -> CodingPlanCard -> ManagedBuildApprovalPanel -> Preview this build ->
approval checkbox -> Approve and build path).

The Vercel project that owns it is the one linked at the repo root via
`.vercel/project.json` (project id `prj_a1RTNyQAqlBaWGqWIrBlFrwiOYN9`, project
name `ham`). Its `vercel.json` (both `./vercel.json` and `./frontend/vercel.json`)
proxies `/api/*` to Cloud Run at `https://ham-api-vlryahjzwa-uc.a.run.app`.

## Stale URL: what it was, why it kept reappearing

Until 2026-05-13 the gitignored local file `.gcloud/ham-api-env.yaml` listed

```yaml
HAM_CORS_ORIGINS: "https://ham-grvil614b-team-clarity.vercel.app,..."
```

as the first allowed origin. That URL is a Vercel-generated preview host on a
**different team scope** (display slug `team-clarity`). It is not the canonical
HAM frontend. Two things hide the mistake at runtime:

1. The line immediately below it is
   `HAM_CORS_ORIGIN_REGEX: "https://.*\\.vercel\\.app"`, which already covers
   every `*.vercel.app` origin, so CORS does not fail when traffic comes from
   the canonical URL.
2. The stale URL itself is gated by Vercel deployment protection (team SSO)
   and serves a different SPA bundle that does **not** carry the `/api/*`
   rewrite to Cloud Run, so anyone who lands there gets `GET /api/status`
   returning `text/html` (the SPA fallback) and concludes "the API is offline."

Because the wrong URL still produced a working canonical site at runtime, the
mistake was never visible during normal operation -- it was only visible when
an operator (or droid) **read the env file** and treated the first listed
origin as production. The audit trail is preserved in
`.gcloud/_quarantine_stale_url/` (gitignored).

## Why old generated Vercel URLs must not be used for smoke

* Their `vercel.json` is whichever was bundled with that older deployment.
  After we landed the `/api/*` -> Cloud Run rewrite, **only the canonical
  alias** definitely carries the current rewrite config; team-scoped or
  per-deployment generated URLs may not.
* Vercel deployment protection (team SSO) intercepts the request before the
  SPA ever loads on team-scoped URLs, which means any smoke from such a host
  is silently against a fresh Vercel-issued nonce session, not against the
  HAM-authenticated user the operator believes they are testing.
* The chat UI on a non-canonical host shows `FACTORY_AI . AGENT -
  GATEWAY_OFFLINE` and `REGISTERED HAM PROJECTS: No projects registered on
  this API.` -- diagnostic signals that look like product bugs but are
  really "the SPA cannot reach its backend".

## Preflight checklist (the four-gate)

The browser-side preflight is implemented in
`frontend/src/lib/ham/managedBuildSmokePreflight.ts` and is invoked by
`ManagedBuildApprovalPanel.handlePreview` and `.handleLaunch`. Both
**Preview this build** and **Approve and build** call it before any
`POST /api/droid/build/preview` or `POST /api/droid/build/launch`.

| # | Check | Failure code | Notes |
|---|---|---|---|
| 1 | `location.host === "ham-nine-mu.vercel.app"` (or an exempt host: `localhost`, `127.0.0.1`, `::1`, with or without port). | `SMOKE_PREFLIGHT_STALE_FRONTEND_HOST` | Any other `*.vercel.app` fails. |
| 2 | Same-origin `GET /api/status` returns HTTP 200 with `Content-Type: application/json`. A `text/html` body means the Vercel rewrite is missing on this deployment. | `SMOKE_PREFLIGHT_API_PROXY_NOT_ROUTED` | -- |
| 3 | The JSON body contains a string `version`, a non-negative integer `run_count`, and `capabilities.project_agent_profiles_read === true`. | `SMOKE_PREFLIGHT_BACKEND_SHAPE_DRIFT` | Guards against a hand-rolled edge function pretending to be `/api/status`. |
| 4 | The response carries an `x-cloud-trace-context` header (set by Google Frontend / Cloud Run). | `SMOKE_PREFLIGHT_NO_BACKEND_TRACE` | Confirms the request actually reached Cloud Run. |

Network failure before any HTTP response (DNS failure, CORS preflight
rejected, offline browser) surfaces as `SMOKE_PREFLIGHT_NETWORK_ERROR`.

All five codes are stable strings, intended for automation that greps
console output or surfaces error toasts.

## Manual smoke preflight (operator)

If you need to verify the canonical frontend by hand before triggering a
smoke (no auth required for these probes):

```bash
# host check (must be canonical)
curl -sSI https://ham-nine-mu.vercel.app/ | head -1   # HTTP/2 200

# proxy MIME check (must be application/json, not text/html)
curl -sS -D - https://ham-nine-mu.vercel.app/api/status \
  | sed -n '1p;/^content-type:/Ip;/^x-cloud-trace-context:/Ip;$p'

# response shape (must contain version + capabilities.project_agent_profiles_read=true)
curl -sS https://ham-nine-mu.vercel.app/api/status
# expect: {"version":"0.1.0","run_count":N,"capabilities":{"project_agent_profiles_read":true}}
```

If `content-type` is not `application/json` or `x-cloud-trace-context` is
missing, **do not run the managed-workspace smoke**. Inspect the Vercel
project's `vercel.json` rewrites (canonical config lives at the repo root
`./vercel.json` and `./frontend/vercel.json`).

## Out of scope

* The preflight does not verify Clerk auth. Authenticated calls
  (`/api/droid/build/preview`, `/api/droid/build/launch`, `/api/coding/readiness`)
  legitimately return `401 CLERK_SESSION_REQUIRED` when probed unauthenticated;
  that is not a deployment defect.
* The preflight is browser-side only. The `scripts/verify_ham_api_deploy.sh`
  script remains the authoritative *backend* readiness probe.
