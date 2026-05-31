# Build Registry v2 Current State

This is the quick-read source for the current HAM build-system posture after
the first legacy/deprecation audit. Historical checkpoint docs remain useful
for context, but this file should be treated as the current operator-facing
summary.

## Current UX

- **Chat** is for asking, guiding, revising, and summarizing.
- **The right pane** owns preview, status, approval, and result actions.
- **Internals stay hidden** from normal users. Do not expose recipe ids,
  registry details, routing confidence, digest values, YAML paths, gate
  reports, or repair-loop details in user-facing copy.

Do not reintroduce Builder Studio as a task-launch surface without an explicit
product decision.

## Current Build System

Build Registry v2 is the current intended routed playbook system. It supplies
internal scaffold context for narrowly matched lanes and is gated by
`HAM_BUILD_REGISTRY_V2_ENABLED`.

The v1 Builder Kit JSON files remain required fallback context. They are used
when v2 is disabled, prompt routing does not produce a supported app type,
metadata is missing, or v2 resolution fails. Do not delete v1 until replacement
fallback coverage exists and the owner approves the behavior change.

Completed routed website/app lanes:

- `site.landing-page-core`
- `site.dashboard-ui-core`
- `app.saas-dashboard-core`
- `app.admin-dashboard-core`
- `app.sales-ops-dashboard-core`

## Provider Posture

Droid and OpenCode share the managed approval flow in the right pane. Preserve
the existing proposal digest, base revision, confirmation, launch, and polling
mechanics.

Claude and Cursor are separate flows unless and until a dedicated lifecycle
design is approved. Do not collapse them into the Droid/OpenCode managed lane
as part of cleanup work.

## Deployment Truth

Vercel deploys the frontend. Cloud Run `ham-api` deploys the backend.

Enabling an environment flag does not update stale backend code. If backend
code changes, rebuild and redeploy the Cloud Run image. Use image-only Cloud
Run updates when preserving existing environment variables and Secret Manager
bindings.

## Cleanup Posture

- Do not remove v1 fallback context yet.
- Do not remove Builder Studio or Coding Agents remnants until the owner makes
  the product-surface decision.
- Do not expose build-kit internals to users.
- Do not reintroduce Builder Studio as a task-launch surface.
- Do not delete local untracked artifacts without owner approval.

See [HAM_LEGACY_DEPRECATION_AUDIT.md](HAM_LEGACY_DEPRECATION_AUDIT.md) for the
full audit and staged cleanup recommendations.
