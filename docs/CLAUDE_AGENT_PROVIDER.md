# Claude Agent coding provider

## Status

Mission 2 is wired. The `claude_agent` provider can execute one
bounded coding mission against a `managed_workspace` project, emit a
snapshot through the existing GCS + Firestore path, and record a
single `ControlPlaneRun`. It remains **disabled by default**: nothing
runs until every gate in § 10 is satisfied. The HAM product rule
still holds: **HAM recommends. User approves. Provider routes
execute. Operations tracks.**

## Why Claude Agent SDK as the primary integration path

Claude Agent SDK is purpose-built for coding-agent execution: it owns
the tool-call loop, the permissions surface, and the hook points an
orchestrator needs to **supervise** execution rather than just observe
chat output. HAM keeps the SDK runtime inside a HAM-controlled backend
(or HAM-controlled runner) — the only place capability routing, audit,
and the `managed_workspace` snapshot boundary are enforced.

This avoids the failure mode `AGENTS.md` calls out under the
"CLI-first execution surface" pillar: embedding a vendor HTTP stack
inside Ham. The SDK is a Python package, not a CLI, but the principle
still applies — auth and process boundaries stay with the tool; Ham
supplies scoped intent, policy limits, and capture.

## Why Claude Code CLI is local-spike / diagnostic only

Claude Code CLI is fine on a developer workstation for one-off spikes
or local diagnostics. It is **not** a HAM execution surface: HAM
cannot enforce permissions, audit every tool invocation, or emit
`managed_workspace` snapshots through an out-of-process CLI it does
not own. HAM will not launch Claude Code CLI in any server, runner, or
Cloud Run instance.

## Why raw Claude API SDK is NOT the coding-agent path

The raw model SDK is appropriate for non-agent chat and one-shot model
calls (for example, Hermes critique and short completions). It does
not provide tool-call orchestration, permissions, or hooks. Building
those on top of the raw client would reinvent the Claude Agent SDK
badly. Use the raw client for chat / model calls; use Claude Agent SDK
for coding-agent execution.

## Where live execution lives (Mission 2)

Live execution runs **in-process** inside the HAM API container (or a
HAM-controlled runner), never the browser. The mission output is a
`managed_workspace` snapshot via
`src/ham/managed_workspace/workspace_adapter.py::emit_managed_workspace_snapshot`.
The Claude Agent path **does not** route through Factory Droid's
`ManagedWorkspaceAdapter` wrapper — that wrapper is a one-line
passthrough, and grafting onto it would couple two providers with
different blast radii. The runner calls
`emit_managed_workspace_snapshot(common)` directly. GitHub PR is **out
of scope** for Mission 2; the launch route refuses
`output_target == "github_pr"`.

## Permissions and hooks

HAM uses the SDK's permission system to **block unsafe tool calls
before they execute** (not to filter output afterward), and SDK hooks
to **audit every tool invocation** into the existing `ControlPlaneRun`
substrate (`src/persistence/control_plane_run.py`). Audit entries
match the record shape Cursor and Factory Droid already write, so the
dashboard and `GET /api/control-plane-runs` get Claude Agent runs for
free.

Defaults: deny `WebFetch` / `WebSearch` (no network egress); deny
`Bash` / `BashOutput` / `KillShell` (no shell); deny disk writes
outside the project root (re-validated in both `can_use_tool` and the
`PreToolUse` hook); require `confirmed=True` on the launch route
before any tool call is issued.

## Auth and secret handling

Secrets are read by the backend; the frontend never sees a key value.
The Anthropic key (or Bedrock / Vertex equivalents) is consumed by the
backend the same way the existing Connected-Tools surface
(`src/ham/worker_adapters/claude_agent_adapter.py`) consumes it.
Readiness exposes **presence only**: `available: boolean`,
`blockers: string[]` (normie-safe; no env names, URLs, or internal
ids), and an operator-only `auth_kind` coarse label
(`anthropic` / `bedrock` / `vertex`). No secret value ever leaves the
collator, the API response, or a log line.

## GitHub is NOT required

Default and only Mission 2 output target is `managed_workspace`. A
project with no GitHub repo can still use the Claude Agent coding
provider. GitHub PR support is a follow-up mission.

## Mission 1 scaffold (historical)

Mission 1 shipped the registration surface, the readiness shape, and a
refusal stub. Mission 2 promotes the placeholders to live values but
leaves the Mission 1 wiring in place; the files below are still
load-bearing:

- `src/ham/coding_router/claude_agent_provider.py` — readiness builder
  (now backs the Mission 2 readiness gate); refusal shim remains as
  the no-op fallback when `CLAUDE_AGENT_ENABLED` is unset.
- `src/ham/coding_router/{types,readiness,recommend}.py` — provider id,
  collator wiring, `_REASON` / `_SAFETY` / `_BASE_CONFIDENCE` (promoted
  in § 12).
- `src/api/coding_conductor.py` — `_LABEL` / `_OUTPUT_KIND` /
  `_WILL_MODIFY_CODE` / `_APPROVAL_KIND` (promoted in § 12).
- `src/ham/harness_capabilities.py` — row promoted from
  `implemented=False` / `audit_sink=None` /
  `registry_status="planned_candidate"` to the values in § 12.
- `frontend/src/lib/ham/api.ts` and
  `frontend/src/features/hermes-workspace/screens/chat/coding-plan/codingPlanCardCopy.ts`
  — provider id widened, display label + status copy.

Mission 2 introduced no new dashboard surfaces and no new frontend
launch UI; the existing CodingPlanCard / ManagedBuildApprovalPanel
already covers `claude_agent` once the recommender selects it.

## Disabled-by-default contract (Mission 2)

Mission 2 keeps the provider disabled by default and adds gates rather
than removing them. Every gate below must pass before a single SDK
message is issued; verified by `tests/test_claude_agent_build_api.py`.

| # | Gate | Failure mode |
|---|------|--------------|
| 1 | Clerk session present | 401 `CLERK_SESSION_REQUIRED` |
| 2 | `confirmed=True` body field | 422 `CLAUDE_AGENT_LAUNCH_REQUIRES_CONFIRMATION` |
| 3 | `CLAUDE_AGENT_ENABLED` env truthy | 503 `CLAUDE_AGENT_DISABLED` |
| 4 | Project exists + `build_lane_enabled=True` | 404 `PROJECT_NOT_FOUND` / 422 `BUILD_LANE_NOT_ENABLED_FOR_PROJECT` |
| 5 | `output_target == "managed_workspace"` | 422 `CLAUDE_AGENT_REQUIRES_MANAGED_WORKSPACE` |
| 6 | Workspace owner / admin approver | 403 `HAM_PERMISSION_DENIED` / 422 `BUILD_LANE_PROJECT_MISSING_WORKSPACE_ID` |
| 7 | Claude Agent SDK installed | 503 `CLAUDE_AGENT_SDK_UNAVAILABLE` |
| 8 | Anthropic credentials configured | 503 `CLAUDE_AGENT_AUTH_UNAVAILABLE` |
| 9 | Workspace context resolved | folded into gate 6; explicit `workspace_id` validation |
| 10 | Digest + `base_revision == CLAUDE_AGENT_REGISTRY_REVISION` verify | 409 `CLAUDE_AGENT_LAUNCH_PREVIEW_STALE` |
| 11 | `HAM_CLAUDE_AGENT_EXEC_TOKEN` env present | 503 `CLAUDE_AGENT_LANE_UNCONFIGURED` |

Notes:

- Gate 11 is **checked last** so an unauthorized caller cannot probe
  whether the host token is configured by reading error codes.
- Gates 3 and 11 are independent: an operator may set
  `CLAUDE_AGENT_ENABLED=1` to expose readiness while leaving
  `HAM_CLAUDE_AGENT_EXEC_TOKEN` unset to disable execution.
- `is_provider_launchable("claude_agent")` returns `True`; the launch
  token check is what keeps execution off without an operator opt-in.
- `claude_agent` is in `_BASE_CONFIDENCE` for **one** task kind only
  (`single_file_edit`); see § 12.
- The Mission 1 invariant "the launch shim returns `not_implemented`
  without importing the SDK" still holds when `CLAUDE_AGENT_ENABLED` is
  unset (gate 3 short-circuits before any SDK indirection runs).

## Tests

Mission 1 invariants still covered (readiness shape, never-leaks-secrets,
`/api/coding/readiness` shape, frontend label / status copy):

- `test_claude_agent_readiness_disabled_by_default`
- `test_claude_agent_readiness_not_configured_when_enabled_but_no_auth`
- `test_claude_agent_readiness_configured_when_enabled_and_auth_present`
- `test_claude_agent_readiness_does_not_leak_secret_values`
- `test_claude_agent_status_appears_in_coding_readiness_response`
- Frontend `claudeAgentReadiness.test.tsx` + `codingPlanCardCopy.test.ts`

Mission 2 added or updated:

- `test_claude_agent_in_harness_capabilities_registry` — row promoted
  to `implemented=True`, `harness_family="local_subprocess"`,
  `audit_sink="claude_agent_jsonl"`, `registry_status="implemented"`;
  provider in `ControlPlaneProvider` enum.
- `test_claude_agent_provider_launchable` —
  `is_provider_launchable("claude_agent")` returns `True`; launch
  route refuses without `HAM_CLAUDE_AGENT_EXEC_TOKEN`.
- `test_claude_agent_recommended_for_single_file_edit` — preview
  endpoint picks `claude_agent` for `single_file_edit` on a
  `managed_workspace` project.
- `test_claude_agent_build_preview_gate_stack` /
  `test_claude_agent_build_launch_gate_stack` — every gate in § 10
  returns the documented failure code in the documented order; gate
  11 fires last.
- `test_claude_agent_build_launch_emits_snapshot` — happy path: fake
  `ClaudeSDKClient` writes one file;
  `emit_managed_workspace_snapshot` is called once; response carries
  `snapshot_id`, `preview_url`, `changed_paths_count > 0`,
  `neutral_outcome="succeeded"`.
- `test_claude_agent_build_launch_persists_control_plane_run` —
  exactly one row written with the field set in § 12.
- `test_claude_agent_runner_blocks_disallowed_tool` /
  `test_claude_agent_runner_blocks_path_outside_root` — fake SDK
  requests `Bash` / `Write` against `/etc/shadow`; both
  `can_use_tool` and `PreToolUse` deny;
  `status="blocked_by_policy"`, `denied_tool_calls_count >= 1`.
- `test_claude_agent_runner_redacts_diagnostics` — every diagnostic
  passes through `_redact_diagnostic_text`.
- `test_claude_agent_runner_no_sdk_installed` — `_import_client`
  raises `ImportError`; runner → `sdk_error`; route →
  `failed` + `claude_agent:sdk_unavailable`.
- `test_claude_agent_runner_timeout` — wallclock exceeds
  `CLAUDE_AGENT_RUN_TIMEOUT_SEC`; runner → `timeout`; route →
  `failed` + `claude_agent:timeout`.
- `test_claude_agent_runner_audit_sink_order` — `AsyncMock` sink
  receives events in `PreToolUse → tool result → PostToolUse` order.

Run the targeted slice with:

```bash
pytest tests/test_claude_agent_build_api.py \
       tests/test_claude_agent_runner.py \
       tests/test_claude_agent_coding_provider.py -q
```

## Mission 2 implementation — what shipped

### Runner module

New module `src/ham/claude_agent_runner/`:

| File | Purpose |
|---|---|
| `runner.py` | `run_claude_agent_mission(...)` async entrypoint. Uses `claude_agent_sdk.ClaudeSDKClient` (**not** `query()`) — `can_use_tool` only fires under the streaming bidirectional client. |
| `permissions.py` | `ClaudeAgentPermissionPolicy` dataclass + `make_can_use_tool(...)` factory. |
| `hooks.py` | `make_pretooluse_guard(...)` + `make_posttooluse_recorder(...)`. |
| `audit.py` | `AuditEvent`, `AuditSink` Protocol, `noop_audit_sink`, `make_list_audit_sink`. |
| `types.py` | `ClaudeAgentRunResult`, `RunStatus` literal. |
| `paths.py` | `safe_path_in_root` + `PATH_ARG_KEYS` (`file_path`, `path`, `notebook_path`, `target_file`, `destination`). |

All SDK imports happen **inside** function bodies via `_import_client`
/ `_import_options` / `_import_hook_matcher` indirection, so the runner
modules are import-safe without `claude-agent-sdk` installed and trivial
to mock.

`run_claude_agent_mission` returns `ClaudeAgentRunResult` with fields
`status` (`success | failure | blocked_by_policy | timeout | sdk_error
| auth_error`), `changed_paths`, `assistant_summary` (≤ 4 KB, redacted),
`tool_calls_count`, `denied_tool_calls_count`, `error_kind`,
`error_summary` (redacted, capped), `duration_seconds`, `sdk_version`,
`cost_usd`, `usage`.

`changed_paths` is sourced from the `PostToolUse` hook record (every
successful `Edit` / `Write` / `MultiEdit` / `NotebookEdit` appends its
absolute path), restricted to paths inside `project_root`, with an
mtime-snapshot diff over `posix_paths_under(root)` as cross-check.

### HTTP launch route

New router `src/api/claude_agent_build.py`, sibling of
`src/api/droid_build.py`:

- `POST /api/claude-agent/build/preview` — returns `proposal_digest`
  and `base_revision = CLAUDE_AGENT_REGISTRY_REVISION`. Does **not**
  run the agent. Same request shape as `/api/droid/build/preview` so
  the existing `ManagedBuildApprovalPanel` flow can target it.
- `POST /api/claude-agent/build/launch` — runs the agent, emits the
  snapshot, persists the `ControlPlaneRun`. Evaluates the 11-gate
  stack in § 10 order; gate 11 is always last (Factory Droid's launch
  route checks `HAM_DROID_EXEC_TOKEN` last for the same reason — a
  503 to an unauthorized caller would otherwise be a configuration
  oracle).

The route is a **sibling**, not a graft, of `/api/droid/build/*`.
Factory Droid's workflow registry and runner-HTTP seam are unrelated;
the sibling router shares only the helpers it needs
(`_require_build_lane_project`, `_require_build_approver`,
`_effective_runner_cwd`).

### Permission model — three defense-in-depth layers

Mission 2 wires all three SDK permission surfaces so a bug in any
single layer cannot reach a tool execution:

1. **`ClaudeAgentOptions.disallowed_tools`** — hard deny evaluated
   inside the CLI before any allow rule, mode, callback, or hook:
   `Bash`, `BashOutput`, `KillShell`, `WebFetch`, `WebSearch`, `Task`.
2. **`can_use_tool` callback** — allow-list check against
   `ClaudeAgentPermissionPolicy.allowed_tools`; path-argument
   validation via `safe_path_in_root`; returns `PermissionResultDeny`
   on miss. The callback only fires under `ClaudeSDKClient`
   (the SDK silently ignores it under `query()`), which is why
   `run_claude_agent_mission` always uses `ClaudeSDKClient`.
3. **`PreToolUse` hook** — re-validates allow-list **and** every path
   argument. Hooks beat `bypassPermissions`, so a misconfigured
   `permission_mode` still cannot leak a write. The hook also
   forwards an `AuditEvent` to the audit sink.

Default allow-list: `Read`, `Glob`, `Grep`, `Edit`, `MultiEdit`,
`Write`, `NotebookEdit`.

Other invariants:

- `permission_mode` is `"default"` (never `"bypassPermissions"`).
- `mcp_servers={}` (any MCP server would expand the tool surface).
- `Task` (subagents) deliberately denied: subagents get their own
  permission stack, so the parent hook never sees their inner tool
  calls.
- `PermissionResultAllow.updated_input` is rejected by the runner
  (defense in depth against silent argument rewrites).

### Snapshot output

The runner produces a `PostExecCommon` and calls
`emit_managed_workspace_snapshot(common)` **directly** — no adapter
indirection. Factory Droid's `ManagedWorkspaceAdapter.emit` is a
one-line passthrough; the adapter selector exists to choose between
`managed_workspace` and `github_pr`, and Mission 2 supports only the
former.

```python
common = PostExecCommon(
    project_id=rec.id,
    project_root=managed_working_dir(rec.workspace_id, rec.id),
    summary=run.assistant_summary,
    change_id=uuid.uuid4().hex,
    workspace_id=rec.workspace_id,
)
out = emit_managed_workspace_snapshot(common)
```

Side effects (in order): per-changed-file GCS blob → snapshot
`manifest.json` → `head.json` advance → `ProjectSnapshot` Firestore (or
file) row.

Response: `snapshot_id = uuid.uuid4().hex`,
`preview_url = "/api/projects/{project_id}/snapshots/{snapshot_id}"`,
`changed_paths_count` derived from the runner's `PostToolUse` set with a
working-tree mtime-diff cross-check.

### ControlPlaneRun audit

Single-write-at-end pattern, identical in shape to Factory Droid's
build writer. After the runner returns and the snapshot emit finishes
(success or failure), the launch route persists exactly one
`ControlPlaneRun`:

- `provider="claude_agent"`, `action_kind="launch"`,
  `output_target="managed_workspace"`.
- `output_ref={neutral_outcome, snapshot_id, parent_snapshot_id,
  preview_url, changed_paths_count, correlation_id}`.
- `base_revision="claude-agent-v1"` (the
  `CLAUDE_AGENT_REGISTRY_REVISION` constant).
- `workflow_id=None` (no workflow registry).
- `external_id=run.change_id` (runner-issued correlation UUID).
- Success: `status="succeeded"`,
  `status_reason="claude_agent:snapshot_emitted"`.
- Failure: `status="failed"`, `status_reason="claude_agent:<kind>"`
  (`sdk_unavailable`, `auth_unavailable`, `policy_blocked`, `timeout`,
  `runner_error`, `snapshot_failed`, …).
- `summary` and `error_summary` both pass through
  `_redact_diagnostic_text` then the standard `cap_*` helpers.
- `proposal_digest` from the preview request; `project_root` resolves
  to `str(managed_working_dir(wid, pid).resolve())`.

**Redaction is mandatory in-process.** Factory Droid's build path can
trust runner-supplied error text because the runner is a separate HTTP
service that redacts before responding. The Claude Agent runner is
**in-process** inside the HAM API container, so every diagnostic
string passes through `_redact_diagnostic_text(...)` (from
`src/ham/worker_adapters/claude_agent_adapter.py`) before being
assigned to `summary` or `error_summary`. The redaction pattern matches
`sk-ant-`, `sk-or-v1-`, `sk_live_`, `sk_test_`, `ghp_`,
`ANTHROPIC_API_KEY`, and `HAM_CLAUDE_AGENT_SMOKE_TOKEN`.

### Registry + recommender

`HarnessCapabilityRow` (`src/ham/harness_capabilities.py`):
`implemented=True`, `harness_family="local_subprocess"`,
`audit_sink="claude_agent_jsonl"`, `registry_status="implemented"`.
Control-plane enum (`src/persistence/control_plane_run.py`) gains
`ControlPlaneProvider.claude_agent = "claude_agent"`.

Recommender (`src/ham/coding_router/recommend.py`):

```python
_BASE_CONFIDENCE["single_file_edit"] = {
    "claude_code": 0.7, "claude_agent": 0.6, "cursor_cloud": 0.5,
}
_REASON["claude_agent"] = (
    "Single-file edit handled by Claude Agent against the managed workspace."
)
_SAFETY["claude_agent"] = {
    "requires_operator": False,
    "requires_confirmation": True,
    "will_open_pull_request": False,
}
```

Conductor (`src/api/coding_conductor.py`):

```python
_LABEL["claude_agent"] = "Managed workspace edit (Claude Agent)"
_OUTPUT_KIND["claude_agent"] = "mission"
_WILL_MODIFY_CODE["claude_agent"] = True
_APPROVAL_KIND["claude_agent"] = "confirm"
```

`_APPROVAL_KIND` is `"confirm"`, not `"confirm_and_accept_pr"` — the
Claude Agent path never opens a PR.

### Required env / secrets

| Env var | Required | Purpose |
|---|---|---|
| `CLAUDE_AGENT_ENABLED` | yes (master flag) | Readiness builder short-circuits when unset; launch route returns 503 `CLAUDE_AGENT_DISABLED`. |
| `ANTHROPIC_API_KEY` | direct Anthropic auth | Read by the adapter; injected per-call via `ClaudeAgentOptions.env={"ANTHROPIC_API_KEY": ...}`. Frontend never sees this. |
| `CLAUDE_CODE_USE_BEDROCK=1` + `AWS_REGION` / `AWS_DEFAULT_REGION` | Bedrock path | Inherited from host env. |
| `CLAUDE_CODE_USE_VERTEX=1` + project id env (`ANTHROPIC_VERTEX_PROJECT_ID`, `GCLOUD_PROJECT`, or `GOOGLE_CLOUD_PROJECT`) | Vertex path | Inherited from host env. |
| `HAM_CLAUDE_AGENT_EXEC_TOKEN` | yes (launch route) | Separate from `HAM_DROID_EXEC_TOKEN` so each provider can be enabled independently. Checked last. |
| `CLAUDE_AGENT_RUN_TIMEOUT_SEC` | optional | Per-mission wallclock cap; default 600. |
| `CLAUDE_AGENT_MAX_TURNS` | optional | Agent loop cap; default 25. |

No env values appear in this document. Operators bind values via
Secret Manager or the Cloud Run env-yaml flow in
`docs/DEPLOY_CLOUD_RUN.md`.

### Deployment notes

- **Cloud Run image** already includes `claude-agent-sdk` (pinned at
  `>=0.1.70,<0.2.0` in `requirements.txt`; the Connected-Tools surface
  noted in `AGENTS.md` already required it).
- **GCS bucket credentials** must be mounted via the same
  `HAM_MANAGED_WORKSPACE_SNAPSHOT_BUCKET` config Factory Droid uses;
  otherwise `emit_managed_workspace_snapshot` returns
  `MANAGED_SNAPSHOT_STORAGE_REQUIRED`.
- **Working tree writable**: `HAM_MANAGED_WORKSPACE_ROOT` must point at
  a writable directory on Cloud Run; the agent edits files in-place
  under `managed_working_dir(wid, pid)`.
- **Firestore credentials**: same `ProjectSnapshotStore` configuration
  as Factory Droid. `ControlPlaneRunStore` backend is independently
  selected via `HAM_CONTROL_PLANE_RUN_STORE_BACKEND`.
- **No Vercel changes** required (frontend gains no new launch UI).
- **No PR / no GitHub** required (`github_pr` refused by gate 5).

### What is NOT in Mission 2

- `github_pr` output target (refused by gate 5).
- Multi-file `refactor` / `feature` / `multi_file_edit` confidence
  entries (only `single_file_edit`).
- Subagents (`Task` tool) — hard-denied.
- MCP servers (`mcp_servers={}`).
- New dashboard surface (existing CodingPlanCard +
  ManagedBuildApprovalPanel suffices).
- Reuse of `safe_edit_low` (Factory Droid internal workflow id; the
  Claude Agent path has no workflow registry — `workflow_id=None` on
  every Claude Agent `ControlPlaneRun`).

## First live smoke plan

Operator-facing checklist for the **first** live invocation. Execute
strictly in this order; stop at the first failure.

1. **Deployment preflight.** Run the four-gate preflight in
   `docs/HAM_SMOKE_PREFLIGHT.md`: `/api/status` returns 200,
   `content-type: application/json`, `x-cloud-trace-context` header
   present, body carries `version` / `run_count` /
   `capabilities.project_agent_profiles_read=true`.
2. **SDK presence on Cloud Run.** Authenticated
   `GET /api/workspace/tools` includes `claude_agent_sdk` with
   `sdk_available: true`.
3. **Env binding.** Operator confirms via Secret Manager / Cloud Run
   bindings that `CLAUDE_AGENT_ENABLED`, `ANTHROPIC_API_KEY`, and
   `HAM_CLAUDE_AGENT_EXEC_TOKEN` are all bound. Values are never
   echoed through any HAM surface.
4. **Readiness route.** Authenticated workspace owner:
   `GET /api/coding/readiness` returns a `claude_agent` entry with
   `available: true` and an empty `blockers` array.
5. **Pilot project.** Pick a `managed_workspace` project on a
   non-production workspace, with a small, well-understood codebase.
   The Factory Droid pilot project (and its siblings on the same
   workspace) is the safest starting point: rollback via the existing
   `head.json` mechanism.
6. **Smoke prompt.** Choose a narrow `single_file_edit` the conductor
   will route to `claude_agent`. Keep the change ≤ 50 lines of diff.
7. **Preview.** `POST /api/claude-agent/build/preview`; record the
   returned `proposal_digest`.
8. **Launch.** `POST /api/claude-agent/build/launch` with
   `confirmed=true`, `proposal_digest=<from step 7>`,
   `base_revision="claude-agent-v1"`.
9. **Response shape.** `status="success"`, `output_ref` includes
   `snapshot_id`, `preview_url`, `changed_paths_count > 0`,
   `neutral_outcome="succeeded"`.
10. **GCS verification.**
    `gs://<bucket>/<wid>/<pid>/snapshots/<snapshot_id>/manifest.json`
    exists, per-file blobs under `snapshots/<snapshot_id>/files/...`
    exist, `head.json` advanced to the new `snapshot_id`.
11. **Firestore verification.** One new `ProjectSnapshot` row for the
    pilot project, with the new `snapshot_id`.
12. **ControlPlaneRun verification.**
    `GET /api/control-plane-runs/<ham_run_id>` returns
    `provider="claude_agent"`, `status="succeeded"`,
    `status_reason="claude_agent:snapshot_emitted"`,
    `output_target="managed_workspace"`,
    `base_revision="claude-agent-v1"`, `output_ref.snapshot_id`
    matching step 9.

If any step fails: read the redacted `error_summary` (never the raw
stack), check `status_reason` against the `claude_agent:<kind>`
taxonomy in § 12, and STOP. Do not retry without operator review.

### Risks / blockers before first live smoke

- **Image must be redeployed.** Mission 2 introduces new code paths
  (`src/ham/claude_agent_runner/`, `src/api/claude_agent_build.py`,
  recommender / conductor entries). Rebuild and roll out via
  `docs/DEPLOY_CLOUD_RUN.md` before any live smoke.
- **Exec token must exist.** Without `HAM_CLAUDE_AGENT_EXEC_TOKEN`
  the launch route returns 503 `CLAUDE_AGENT_LANE_UNCONFIGURED` —
  the operator-controlled off switch.
- **Pilot project must not be production.** Use the Factory Droid
  pilot project or a sibling on the same non-production workspace;
  snapshot history is recoverable via `head.json` rollback.
- **First smoke ≤ 50 lines.** Do not run multi-file refactors until
  at least three single-file smokes have succeeded end-to-end.
- **In-process risk surface.** The runner edits the working tree
  inside the HAM API container. Misconfiguration of
  `HAM_MANAGED_WORKSPACE_ROOT` is caught by
  `MANAGED_WORKSPACE_CWD_MISMATCH`, but operators should still
  verify the mounted path before enabling the exec token.

## References

SDK docs:

- https://code.claude.com/docs/en/agent-sdk/overview
- https://code.claude.com/docs/en/agent-sdk/permissions
- https://code.claude.com/docs/en/agent-sdk/hooks
- https://github.com/anthropics/claude-agent-sdk-python
- https://pypi.org/project/claude-agent-sdk/

HAM docs: `AGENTS.md`, `docs/HAM_SMOKE_PREFLIGHT.md`,
`docs/DEPLOY_CLOUD_RUN.md`,
`docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`,
`docs/CONTROL_PLANE_RUN.md`.

Mission 2 internals: `src/ham/claude_agent_runner/` (runner, permissions,
hooks, audit, types, paths), `src/api/claude_agent_build.py` (launch
route).

Reused surfaces: `src/ham/worker_adapters/claude_agent_adapter.py`
(readiness + redaction), `src/ham/coding_router/claude_agent_provider.py`
(Mission 1 readiness builder),
`src/ham/managed_workspace/workspace_adapter.py`
(`emit_managed_workspace_snapshot`),
`src/persistence/control_plane_run.py` (`ControlPlaneProvider`,
`ControlPlaneRun`, `ControlPlaneRunStore`).
