# Build Registry v2 Current State

This is the quick-read source for the current HAM build-system posture after
the first legacy/deprecation audit. Historical checkpoint docs remain useful
for context, but this file should be treated as the current operator-facing
summary.

## Builder selection model (product law)

**HAM/Hermes is always the agent the user talks to. External builder selection
chooses only the execution harness HAM routes work through.**

- **Settings → Builders shows external execution harnesses only:** **Cursor,
  Claude, OpenCode, Factory Droid**.
- **No external builder selected means native HAM/Hermes mode.** The UI should
  say HAM builds natively and, until the backend path is fully live everywhere,
  that native HAM build support is being wired. Do not present Hermes as
  optional, disabled, or "coming soon" in the builder selector.
- **OpenCode is an optional free external builder, not the conceptual default.**
  It may be auto-selected only in deployments that explicitly configure
  `HAM_DEFAULT_BUILDER=opencode`; otherwise no external selection means native
  HAM/Hermes.
- **The old internal scaffold is not a product builder.** Normal build turns do
  not use it, and Quick Preview must route through HAM Native/Hermes unless an
  internal development flag deliberately exercises the legacy preview path.

### Honest current state (do not overstate)

- **Shipped:** the chat builder hook no longer silently falls back to the old
  internal scaffold for normal user build turns. With no selected external
  harness and no deployment override, HAM routes to HAM Native Builder through
  Hermes; if that path is not ready on the host, it says
  "HAM Native Builder is not ready yet."
- **Shipped:** selected-builder persistence exists in workspace coding-agent
  settings (`selected_builder`), and OpenCode / Factory Droid can hand off to
  the managed approval surface when ready.
- **Deployment caveat:** staging currently uses `HAM_DEFAULT_BUILDER=opencode`,
  so a workspace with no selected external builder can still route to OpenCode.
  That conflicts with the corrected native-default product model unless this is
  an intentional deployment override for OpenCode-first testing. Production
  should remove that env default when native HAM/Hermes mode is intended.
- **Partially wired:** HAM Native Builder has a bounded Hermes gateway
  new-build entry point that writes Workbench-compatible source snapshots when
  the gateway is live. Hosts without a live gateway return the honest
  unavailable message above; the old scaffold is not used as a substitute.

Selectable-builder preference is expected to live in the workspace coding-agent
settings (`WorkspaceAgentPolicy` + `/api/workspaces/{id}/coding-agent-access-settings`).

## Current UX

- **Chat** is for asking, guiding, revising, and summarizing.
- **The right pane** owns preview, status, approval, and result actions.
- **Internals stay hidden** from normal users. Do not expose recipe ids,
  registry details, routing confidence, digest values, YAML paths, gate
  reports, or repair-loop details in user-facing copy.

Do not reintroduce Builder Studio as a task-launch surface without an explicit
product decision.

## Current Build System

> Scope note: this section describes the internal playbook context available to
> HAM Native Builder and external harness launch prompts. It is not exposed to
> users as build-kit internals.

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
