# 0008 — Sentry SDK is scaffolded; DSN is provisioned by the owner

Tier 1 #9 calls for Sentry SDK + request-ID middleware. Creating a Sentry project is a human action (signup, email confirmation, ToS acceptance, project creation in Sentry's UI) that no agent can perform on the owner's behalf. We choose to **scaffold the full SDK wiring with the DSN read from `SENTRY_DSN`** and ship Phase 1 with the env var unset — the SDK init is a no-op until the owner provisions the DSN.

## What ships in Phase 1

- `sentry-sdk` (Python) initialized in the FastAPI app factory, reading `SENTRY_DSN` from the environment
- `@sentry/react` / `@sentry/browser` initialized in the frontend entry point, reading `VITE_SENTRY_DSN`
- Request-ID middleware (Python): generates a UUID per request, attaches to Sentry scope, surfaces in response headers (`X-Request-ID`)
- Breadcrumb hooks on the chat, Builder mutation router, and Worker dispatch paths
- `traces_sample_rate=0.0` by default (no perf overhead until the owner opts in)

## Behavior when `SENTRY_DSN` is unset

`sentry_sdk.init(dsn=None)` is a no-op natively — the SDK records no events, sends no network traffic, attaches no scope. Same for the JS SDK. The wiring is dormant but present; flipping a Cloud Run secret activates it.

## Why deferred DSN instead of "do not wire until DSN exists"

The wiring is the load-bearing work. Adding `init(...)`, middleware, breadcrumbs, and error decorators is multi-file and touches hot paths. Splitting it across "wire now / activate later" PRs is cleaner than rushing both into the same PR the day the owner signs up for Sentry.

## Why Sentry instead of a different tool

The roadmap names Sentry specifically. Alternatives considered:
- **Cloud Logging only** — already in place; structured but not error-shaped (no fingerprinting, no release tracking, no source maps)
- **GlitchTip** (open-source Sentry-API-compatible) — viable if the owner doesn't want a paid Sentry tier; the SDK wiring works against either with no code change (DSN points at a different host)
- **BugSnag / Rollbar / Highlight** — different SDKs, different code; defer

If the owner picks GlitchTip later, this ADR remains accurate — the DSN just points at the self-hosted instance.

## Consequences

- The Phase 1 PR that closes Tier 1 #9 ships without runtime error tracking active
- The Cloud Run deploy doc (`docs/DEPLOY_CLOUD_RUN.md`) gains `SENTRY_DSN` as an optional secret with documentation pointing here
- Frontend builds need `VITE_SENTRY_DSN` injected at build time; Vercel's env var UI is the activation point on the frontend side
- The owner is responsible for: creating a Sentry/GlitchTip project, pasting the DSN into Cloud Run secrets and Vercel env, and (optionally) raising `traces_sample_rate` when ready for perf monitoring
- Until activated, errors continue to go to Cloud Logging only (the existing baseline) — no regression
