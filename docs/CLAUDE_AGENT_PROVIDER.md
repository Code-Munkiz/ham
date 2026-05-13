# Claude Agent coding provider

## Status

Mission 1 scaffold only. The `claude_agent` provider is **disabled by default**
on every host and performs **no live execution**. The HAM product rule still
holds: **HAM recommends. User approves. Provider routes execute. Operations
tracks.** Nothing in this scaffold reaches a model, a CLI, or a remote runner.
It registers a provider id, a readiness shape, and a refusal stub so the rest
of the system can see the slot without anyone being able to use it.

## Why Claude Agent SDK as primary integration path

Claude Agent SDK is purpose-built for coding-agent execution: it owns the
tool-call loop, the permissions surface, and the hook points that an
orchestrator needs in order to supervise execution rather than just observe
chat output.

HAM keeps the SDK runtime inside a HAM-controlled backend (or a HAM-controlled
runner). That is where capability routing, the audit log, and the
`managed_workspace` snapshot boundary are enforced today, and it is the only
place where HAM can reason about what a tool call is doing before it happens.

This avoids the failure mode `AGENTS.md` calls out under the "CLI-first
execution surface" pillar: embedding a vendor's HTTP stack inside Ham. The
Claude Agent SDK is a Python package, not a CLI, but the principle still
applies — auth and process boundaries stay with the tool, and Ham supplies
scoped intent, policy limits, and capture.

## Why Claude Code CLI is local-spike / diagnostic only

Claude Code CLI is fine on a developer workstation for one-off spikes or local
diagnostics. It is **not** a HAM execution surface.

HAM cannot enforce permissions, audit every tool invocation, or emit
`managed_workspace` snapshots through an out-of-process CLI it does not own.
HAM will not launch Claude Code CLI in any server, runner, or Cloud Run
instance.

## Why raw Claude API SDK (anthropic Python client) is NOT the coding-agent path

The raw model SDK is appropriate for non-agent chat and one-shot model calls
(for example, Hermes critique and short completions). It does not provide
tool-call orchestration, permissions, or hooks.

Building those primitives on top of the raw client would reinvent the Claude
Agent SDK — badly, and without the upstream maintenance. The split stays
clean: use the raw client for chat/model calls; use Claude Agent SDK for
coding-agent execution.

## Where live execution will live (future, not Mission 1)

When live execution lands in a later mission it will run inside a
HAM-controlled backend or runner, never the browser. The mission output is a
`managed_workspace` snapshot through the existing GCS + Firestore path —
`src/ham/managed_workspace/workspace_adapter.py::emit_managed_workspace_snapshot`
fed by the post-exec pattern in
`src/ham/droid_runner/build_lane_output.py::ManagedWorkspaceAdapter`. GitHub
PR remains an optional advanced mode, not the default.

Mission 2 will add:

- `claude_agent` to the `ControlPlaneProvider` enum.
- A real `HarnessCapabilityRow` with `implemented=True`.
- A launch path that wraps Claude Agent SDK execution into a `PostExecCommon`
  and feeds the existing `ManagedWorkspaceAdapter`.

## Permissions and hooks

HAM will use Claude Agent SDK's permission system to **block unsafe tool
calls before they execute** (deny, allow, or require operator confirmation),
not to filter their output afterward.

HAM will use Claude Agent SDK hooks to **audit every tool invocation** into
the existing `ControlPlaneRun` substrate
(`src/persistence/control_plane_run.py`). Audit entries are the same record
shape the Cursor and Factory Droid lanes already write, so the dashboard and
the read API (`GET /api/control-plane-runs`) get Claude Agent runs for free
once Mission 2 ships.

Default policy when execution lands:

- Deny network egress except to allow-listed mission endpoints.
- Deny disk writes outside the registered project root.
- Deny shell tools by default.
- Require explicit operator confirmation for any mutating tool.

See the official Claude Agent SDK references at the bottom of this file.

## Auth and secret handling

Secrets are read by the backend. The frontend never sees a key value.

The Anthropic key (or Bedrock / Vertex equivalents) is consumed by the
backend exactly the way the existing Connected-Tools surface
(`src/ham/worker_adapters/claude_agent_adapter.py`) already consumes it.
Readiness exposes **presence only**:

- `available: boolean`
- `blockers: string[]`  (normie-safe; no env names, no URLs, no internal ids)
- operator-only `auth_kind` coarse label: `anthropic` / `bedrock` / `vertex`

No value of any secret ever leaves the collator, the API response, or a log
line. The redaction conventions used by `claude_agent_adapter.py` apply to
anything new this provider emits.

## GitHub is NOT required

Default output target is `managed_workspace`. GitHub PR is opt-in and
advanced. A project with no GitHub repo can still use the Claude Agent
coding provider once Mission 2 lands.

## Current scaffold (Mission 1) — exactly what shipped

Backend:

- New: `src/ham/coding_router/claude_agent_provider.py` — readiness builder
  plus a disabled launch shim that returns `not_implemented` and never
  imports or invokes the SDK.
- Modified: `src/ham/coding_router/types.py` — added `"claude_agent"` to the
  `ProviderKind` Literal.
- Modified: `src/ham/coding_router/readiness.py` — wired the new builder into
  the providers tuple returned by `collate_readiness`.
- Modified: `src/ham/coding_router/recommend.py` — defensive `_REASON` and
  `_SAFETY` entries for `claude_agent`. Intentionally **not** added to
  `_BASE_CONFIDENCE`, so the recommender will never select it.
- Modified: `src/api/coding_conductor.py` — defensive entries in the four
  dispatch tables (label / output-kind / will-modify-code / approval-kind)
  so candidate rendering cannot `KeyError` if a future code path constructs
  a `claude_agent` candidate.
- Modified: `src/ham/harness_capabilities.py` — planned-candidate row with
  `implemented=False` and `registry_status="planned_candidate"`.
- Modified: `tests/test_harness_capabilities.py` — extended the
  `PLANNED_CANDIDATE_PROVIDERS` set.
- New: `tests/test_claude_agent_coding_provider.py`.
- New: `docs/CLAUDE_AGENT_PROVIDER.md` (this file).

Frontend:

- Modified: `frontend/src/lib/ham/api.ts` — widened
  `CodingConductorProviderKind` to include `"claude_agent"`.
- Modified: `frontend/src/features/hermes-workspace/screens/chat/coding-plan/codingPlanCardCopy.ts`
  — display label, status-copy record, and helper.
- New: `frontend/src/features/hermes-workspace/screens/chat/coding-plan/__tests__/claudeAgentReadiness.test.tsx`.
- Modified: `frontend/src/features/hermes-workspace/screens/chat/coding-plan/__tests__/codingPlanCardCopy.test.ts`.

No new HTTP routes. No new credential storage. No new dashboard surfaces.

## Disabled-by-default contract

- Env gate: `CLAUDE_AGENT_ENABLED` (boolean, default off). When unset, the
  readiness builder short-circuits and returns
  `available=False` with a single normie-safe blocker before any auth probe
  runs.
- `is_provider_launchable("claude_agent")` returns `False` automatically
  because the `HarnessCapabilityRow` has `implemented=False`.
- `claude_agent` is intentionally **not** in the `ControlPlaneProvider`
  enum. Mission 2 will add it.
- `claude_agent` is intentionally **not** in `_BASE_CONFIDENCE`. The
  conductor's recommender will never pick it.
- `launch_claude_agent_coding(...)` returns
  `ClaudeAgentLaunchResult(status="not_implemented", reason=...)` and does
  not import or invoke the SDK.

Result: even with the env flag flipped on and a valid Anthropic key in the
environment, the provider still cannot run. Three independent gates
(`implemented=False`, missing enum membership, recommender omission) all
have to be flipped in code before live execution is reachable.

## Tests

- `test_claude_agent_readiness_disabled_by_default` — env unset →
  `available=False` with a single normie-safe blocker.
- `test_claude_agent_readiness_not_configured_when_enabled_but_no_auth` —
  env on, no auth channel → `available=False`, normie-safe blocker.
- `test_claude_agent_readiness_configured_when_enabled_and_auth_present` —
  env on, SDK + auth detected → `available=True`, no blockers.
- `test_claude_agent_readiness_does_not_leak_secret_values` — `public_dict()`
  contains none of the forbidden tokens (env names, secret prefixes, URLs).
- `test_claude_agent_provider_refuses_to_execute` —
  `is_provider_launchable("claude_agent")` returns `False` even when env on
  and auth present, because `implemented=False`.
- `test_claude_agent_launch_shim_returns_not_implemented` — the launch shim
  returns `status="not_implemented"` and never imports the SDK.
- `test_claude_agent_status_appears_in_coding_readiness_response` —
  `GET /api/coding/readiness` includes a `provider == "claude_agent"` entry.
- `test_claude_agent_in_harness_capabilities_registry` — row present with
  `registry_status="planned_candidate"`, `implemented=False`,
  `audit_sink=None`; absent from the control-plane enum.
- `test_claude_agent_never_recommended_by_conductor` — `POST
  /api/coding/conductor/preview` with any prompt never selects
  `claude_agent` (absent from `_BASE_CONFIDENCE`).
- Frontend `claudeAgentReadiness.test.tsx` — renders the new display label,
  renders the readiness status copy, and asserts no active
  Approve/Preview/Launch button is rendered for `claude_agent`.
- Frontend `codingPlanCardCopy.test.ts` — extended `PROVIDERS` loop covers
  the new `claude_agent` label and status copy.

## Mission 2 plan (live runner execution into managed_workspace)

1. Add `claude_agent = "claude_agent"` to `ControlPlaneProvider` in
   `src/persistence/control_plane_run.py` and move `claude_agent` from
   `PLANNED_CANDIDATE_PROVIDERS` to `IMPLEMENTED_PROVIDERS` in
   `tests/test_harness_capabilities.py`.
2. Implement a HAM-side backend runner adapter that wraps Claude Agent SDK
   in-process. Wire its permission allow-list (network, disk, shell) and
   its hooks into the existing `ControlPlaneRun` audit log.
3. Wire `launch_claude_agent_coding(...)` to produce a `PostExecCommon` and
   call `emit_managed_workspace_snapshot(common)` for the
   `managed_workspace` path. Reuse the existing `ManagedWorkspaceAdapter`
   surface so the snapshot, preview URL, and changed-paths count are
   identical to the Factory Droid build lane.
4. Add narrow `_BASE_CONFIDENCE` entries — start with one or two task kinds
   where Claude Agent is the preferred option, not a global default.
5. Gate the smoke verification behind the same `/api/status` 4-gate
   preflight pattern landed in Mission 0 (`docs/HAM_SMOKE_PREFLIGHT.md`).
6. GitHub-PR advanced mode as an optional follow-up, modeled after the
   existing build-lane GitHub PR path.

## References

- https://code.claude.com/docs/en/agent-sdk/overview
- https://code.claude.com/docs/en/agent-sdk/permissions
- https://code.claude.com/docs/en/agent-sdk/hooks
- https://code.claude.com/docs/en/permissions
- https://code.claude.com/docs/en/cli-reference (secondary context only)
- `AGENTS.md`
- `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`
- `docs/HAM_SMOKE_PREFLIGHT.md`
- `src/ham/worker_adapters/claude_agent_adapter.py` (existing Connected-Tools surface)
- `src/ham/coding_router/claude_agent_provider.py` (this scaffold)
