# OpenCode coding-provider lane

Mission 1 (this PR) scaffolds the OpenCode lane in HAM's coding-provider
stack. **No live execution lands here.** This document is the canonical
reference for the disambiguation, the integration-mode plan, the
credential strategy, and the multi-mission roadmap.

## 1. Which OpenCode

Use **`github.com/anomalyco/opencode`** (formerly `sst/opencode`),
published at <https://opencode.ai>. Anomaly is the company spun out of
SST; the docs site's "Edit page" / "GitHub" buttons link directly at
`anomalyco/opencode`.

Do **not** confuse with:

- The `opencode-ai/opencode` Go repo, which was renamed to **Crush**
  after a development split. Treat as legacy/abandoned for HAM
  integration purposes.
- Any other tool that happens to share the name in unrelated ecosystems.

When HAM users say "opencode" in 2026, they almost always mean
`anomalyco/opencode`. The integration must pin a specific version tag
once Mission 2 lands and re-verify the surface against `/doc` at build
time.

## 2. Why OpenCode in HAM

OpenCode fills a gap none of HAM's existing coding lanes covers cleanly:

- **Open / BYOM-friendly.** First-class support for OpenRouter,
  llama.cpp, LM Studio, Ollama, and any OpenAI-compatible endpoint
  (including a HAM gateway).
- **Custom builder profiles.** OpenCode "agents" are JSON or
  Markdown-frontmatter definitions of a model + tool set + permission
  block. This maps directly onto the HAM agent-builder UX that Mission 3
  will expose ("create your own coding agent").
- **Multi-vendor protocol.** Mode B (ACP, JSON-RPC) is the same protocol
  Zed, JetBrains, and other editors are converging on; an ACP-Client
  adapter in HAM would be reusable across future ACP-speaking backends.

OpenCode is **not** going to be another big user-facing button. HAM
remains the conductor; OpenCode is one of several CLIs HAM can supervise
behind a uniform Hermes-shaped envelope vocabulary.

## 3. Three integration modes (Mission 2 plan)

| Mode | HAM recommendation | Why |
|---|---|---|
| **A. `opencode serve` (HTTP / OpenAPI)** | **PRIMARY for Mission 2** | Per-run credential injection via `PUT /auth/:id`; SSE permission interception via `POST /session/:id/permissions/:permissionID`; OpenAPI 3.1 schema at `/doc`; clean abort via `POST /session/:id/abort`; no TTY required; localhost-bound by default; HTTP Basic auth via `OPENCODE_SERVER_PASSWORD`. Mission 3.1's deletion guard maps to upstream `permission.bash` rules AND HAM-enforced policy at the snapshot boundary. |
| **B. `opencode acp` (NDJSON / JSON-RPC stdio)** | **FAST-FOLLOW for Mission 2** | Standard Agent Client Protocol; same protocol Zed and JetBrains use. Loses per-run credential isolation (inherits env / shared `auth.json`). |
| **C. Plain CLI / TUI (`opencode run`)** | **DIAGNOSTIC ONLY** | Limited permission interception (TTY-only or `--dangerously-skip-permissions` to avoid blocking). Live JSON event stream is still maturing upstream (`oh-my-opencode#1115`). Not a production target. |

The capability row in `src/ham/harness_capabilities.py` pins these as
`integration_modes = {serve: planned_primary, acp: planned_fast_follow,
cli: diagnostic_only}`.

## 4. Mission 1 scope (this PR)

This PR adds **only**:

1. `src/ham/worker_adapters/opencode_adapter.py` — presence-only
   readiness probe with five states (`disabled`, `not_configured`,
   `cli_missing`, `provider_auth_missing`, `configured`). No subprocess,
   no network, no env value reads.
2. `src/ham/coding_router/opencode_provider.py` — disabled launch shim
   facade. Always returns
   `OpenCodeLaunchResult(status="disabled"|"not_implemented",
   ham_run_id=None)`. No `ControlPlaneRun` row is minted; no GCS,
   Firestore, or audit JSONL writes.
3. `src/api/opencode_build.py` — `POST /api/opencode/build/launch` route
   that always raises HTTP 503 with
   `detail.reason="opencode:not_implemented"`.
4. Conductor wiring: `readiness.py`, `recommend.py`, `coding_conductor.py`
   tables, the Connected Tools surface, and the `ControlPlaneProvider`
   enum. The recommender hard-excludes `opencode_cli` from candidate
   lists while disabled or unconfigured.
5. Capability row promoted from `planned_candidate` to `scaffolded`
   with the `capabilities` + `integration_modes` sub-dicts.
6. Tests + this document.

There is **no** OpenCode CLI invocation, **no** model call, **no** PR
opening, **no** frontend UX change in Mission 1.

## 5. Credential strategy

Mission 2 will inject credentials into a sandboxed runner; Mission 1
just makes sure the readiness adapter sees them only as presence
booleans. The plan:

- **HAM never depends on a shared `~/.local/share/opencode/auth.json`.**
  Each Mission 2 run gets `XDG_DATA_HOME=<per-run tempdir>` so any
  `auth.json` writes during the session live and die with the tmpdir.
  No `OPENCODE_AUTH_FILE` env var exists upstream; `XDG_DATA_HOME`
  redirection is the supported relocation path.
- **BYOK via Connected Tools.** Provider keys are stored Fernet-encrypted
  per Clerk user in HAM's Connected Tools store
  (`src/persistence/connected_tool_credentials.py`). The Mission 2
  runner reads the plaintext only at runner startup and injects it into
  the OpenCode subprocess env (or into `PUT /auth/:id` when using
  `serve` mode). HAM never decrypts a key on the readiness path.
- **Provider keys NEVER on the frontend.** The HTTP surface returns only
  boolean presence hints — `{"OPENROUTER_API_KEY": true, ...}` — and a
  masked `credential_preview` when a Connected Tools record exists.
- **HAM gateway as an optional OpenAI-compatible BYOK seam (Mission 3).**
  OpenCode's `provider` config supports any OpenAI-compatible base URL,
  so HAM can plant a `ham-gateway/ham-default` model that terminates
  BYOK at the HAM gateway instead of letting OpenCode see a raw
  Anthropic / OpenRouter / OpenAI key.

The readiness adapter exposes the auth hint slot
`"byok_via_connected_tools": False` for Mission 1; Mission 2 turns it
into a real boolean by consulting `has_connected_tool_credential_record`
for a per-user record.

## 6. Permission model and Mission 3.1 alignment

OpenCode ships a granular permission system (see `opencode.ai/docs/permissions/`):

| key | gates |
|---|---|
| `read` | the `read` tool (path-matched; `.env*` denied by default) |
| `edit` | `write` / `edit` / `apply_patch` |
| `bash` | the `bash` tool, matched on the parsed command string |
| `task` | subagent invocation by id |
| `external_directory` | any tool touching a path outside the project worktree |
| `doom_loop` | safety guard — same tool call repeated 3× with identical input |

Values are `"allow"` / `"ask"` / `"deny"`, or an object pattern map
(last matching rule wins).

**HAM's Mission 3.1 deletion guard maps to two complementary layers:**

1. **Upstream `permission.bash` denylist** as the first line of defence.
   Recommended baseline for HAM-managed runs:

   ```jsonc
   {
     "permission": {
       "bash": {
         "*": "ask",
         "git status*": "allow",
         "git diff*": "allow",
         "grep *": "allow",
         "rm *": "deny",
         "rm -rf *": "deny",
         "find * -delete": "deny"
       },
       "edit": {
         "**/.env*": "deny",
         "**/secrets/**": "deny",
         "*": "allow"
       }
     }
   }
   ```

   These are pushed via `OPENCODE_CONFIG_CONTENT` or `OPENCODE_PERMISSION`
   (inline JSON, immutable for the duration of the run) so the agent
   cannot relax them at runtime.

2. **HAM-enforced deletion guard at the snapshot-promotion boundary.**
   Even if upstream lets a delete through, HAM's Mission 3.1 logic
   (`compute_deleted_paths_against_parent` in
   `src/ham/managed_workspace/workspace_adapter.py`) compares the
   current working tree against the parent snapshot and refuses to
   promote a snapshot that would delete files unless
   `HAM_OPENCODE_ALLOW_DELETIONS` is truthy. This mirrors
   `HAM_CLAUDE_AGENT_ALLOW_DELETIONS` exactly.

## 7. Managed-workspace output contract

OpenCode runs in Mission 2 will emit a managed-workspace snapshot using
the same `emit_managed_workspace_snapshot` + `PostExecCommon` shape as
Claude Agent. The `ControlPlaneRun.status_reason` taxonomy will be
`opencode:*`, mirroring `claude_agent:*`:

- `opencode:snapshot_emitted` — terminal success.
- `opencode:nothing_to_change` — terminal success, no diff.
- `opencode:snapshot_failed` — runner succeeded but emit failed.
- `opencode:blocked_by_policy` — upstream permission `deny` fired.
- `opencode:timeout`
- `opencode:cli_missing`
- `opencode:auth_missing`
- `opencode:disabled`
- `opencode:output_requires_review` — deletions detected and the
  override env is unset.
- `opencode:workspace_setup_failed`

## 8. No GitHub required by default

PR mode is an opt-in advanced lane just like Claude Agent. The default
`output_target` for OpenCode-managed projects is `managed_workspace`,
which emits a HAM-side preview snapshot and never opens a PR. The
`capabilities.github_pr` slot in the capability row is `"later"`.

## 9. Custom builder UX (Mission 3)

Once Mission 2 has a working live runner, Mission 3 lets HAM users
compose reusable "create your own coding agent" profiles:

- Each HAM agent profile points at OpenCode + a model + a tool /
  permission set (the OpenCode `agent` definition shape).
- Profiles are stored under a HAM-namespaced key in `.ham/agents/` (or
  per-user config when not project-scoped) and referenced by the HAM
  agent builder.
- The frontend exposes the "create / edit profile" UX **without** ever
  surfacing the raw provider key: HAM holds the key in Connected
  Tools, OpenCode reads it from `{env:HAM_GATEWAY_API_KEY}` at runtime.

## 10. Mission 2 plan (live execution)

In order of milestones:

1. **`opencode serve` adapter** (`src/ham/opencode_runner/`):
   spawn one `opencode serve --hostname 127.0.0.1 --port <ephemeral>`
   per Mission run with `OPENCODE_SERVER_PASSWORD=<per-run-secret>`,
   per-run `XDG_DATA_HOME=<tmpdir>`, and `OPENCODE_PERMISSION` carrying
   the HAM-baseline deny rules.
2. **Per-run credential injection** via `PUT /auth/:id` after server
   startup; the plaintext key never touches disk thanks to the
   ephemeral XDG redirection.
3. **SSE permission interception**: HAM consumes `GET /event` and
   answers `session.permission.requested` events itself, routing the
   decision through Hermes policy.
4. **HAM-enforced deletion guard at the snapshot boundary**:
   `compute_deleted_paths_against_parent(common)` runs before
   `emit_managed_workspace_snapshot(common)`; deletions are rejected
   unless `HAM_OPENCODE_ALLOW_DELETIONS` is truthy.
5. **Gated** behind `HAM_OPENCODE_EXECUTION_ENABLED`; the existing
   `HAM_OPENCODE_ENABLED` keeps gating the readiness/conductor lane.
6. **ACP adapter** fast-follow once `serve` is stable, reusing the same
   permission-broker and policy code paths.

## 11. Mission 3 plan (custom HAM builder profiles)

- HAM agent profiles reference an `opencode_agent_id` and a model id
  (via the HAM gateway by default).
- Profiles are stored as Markdown frontmatter (mirroring OpenCode's own
  `.opencode/agents/` shape) so a user can copy a profile out of HAM
  and into a local OpenCode install with no translation.
- The frontend "agent builder" UX adds a new card type for OpenCode-
  backed agents; only presence booleans for credentials cross the
  wire.

## 12. Open risks / blockers

- Upstream issues **`sst/opencode#5423`** (env-var creds, filed
  2025-12-12) and **`#4318`** (OS keychain, filed 2025-11-14) were
  still open at the 2026-05 research snapshot. The Mission 2 plan
  works around both by using ephemeral `XDG_DATA_HOME` redirection and
  the `{env:...}` substitution in `OPENCODE_CONFIG_CONTENT`.
- OpenCode is a fast-moving project. The Mission 2 adapter must
  re-verify `/doc` and the ACP spec at build time and pin a specific
  binary tag.
- The legacy `opencode-ai/opencode` URL still resolves; document the
  Anomaly fork as canonical at install time so a long-running pinned
  install doesn't end up wired to the Crush rename by accident.
- ACP spec churn (`session-modes` deprecation) — if HAM commits to ACP,
  it must keep its Client up to date with the spec.

## 13. Why the disabled shim mints no `ControlPlaneRun`

Following the Claude Agent precedent at the `_require_claude_agent_enabled()`
gate: a 503 from a disabled route is **not** a control-plane event.
Minting a row would just add audit-trail noise that always says
"disabled". Once Mission 2 ships a real executor, the shim's HTTP path
will mint a `ham_run_id`, build a `PostExecCommon`, persist a
`ControlPlaneRun` with `provider="opencode_cli"`,
`output_target="managed_workspace"`, and a redacted `status_reason`
from the taxonomy in §7.

## 14. Mission 2 architecture (live execution)

Mission 2 lands the gated `opencode serve` runner adapter, the live
preview + launch routes, and a mocked-end-to-end test suite. The lane
stays dormant at runtime until **both** `HAM_OPENCODE_ENABLED` and
`HAM_OPENCODE_EXECUTION_ENABLED` are truthy. No CLI invocation, no
model call, no GCS / Firestore / Cloud Run write happens in test runs.
The Factory Droid and Claude Agent lanes are unaffected; Mission 3.1's
deletion guard is mirrored bit-for-bit for the OpenCode path.

### Server lifecycle

```text
1. ensure_managed_working_tree(workspace_id, project_id)     # Mission 2.x
2. mint ham_run_id + change_id
3. spawn opencode serve --hostname 127.0.0.1 --port <ephemeral>
   with XDG_DATA_HOME / XDG_CONFIG_HOME pointing at per-run tempdirs
   and OPENCODE_SERVER_PASSWORD set to a per-run random token
4. poll GET /global/health for up to 30 s (500 ms intervals)
5. PUT /auth/<provider> with HAM-resolved creds for each present env key
6. POST /session  -> session_id
7. POST /session/<id>/prompt_async with the user's prompt
8. consume GET /event SSE; broker each session.permission.requested
   through the deny-by-default policy below
9. on session.idle (or HAM-side deadline), POST /session/<id>/abort
   then POST /instance/dispose, then SIGTERM → SIGKILL the process
10. reap orphan children; remove XDG tempdirs; return OpenCodeRunResult
```

All credential resolution happens inside `build_isolated_env`. Env
values flow only through the spawned process's env mapping and the
optional `PUT /auth/:id` HTTP call; HAM never logs or echoes a secret
value, including in test runs.

### HTTP client + Basic auth

`OpenCodeServeClient` wraps `httpx.Client` with a Basic-auth tuple
(`opencode:<per-run-password>`). All endpoints used by the runner are
explicitly enumerated: `GET /global/health`, `PUT /auth/:id`,
`POST /session`, `POST /session/:id/prompt_async`, `POST
/session/:id/permissions/:permissionID`, `POST /session/:id/abort`,
`POST /instance/dispose`. `POST /session/:id/init` is **not** used —
the upstream API table no longer lists it.

### SSE event consumer

Event payloads are parsed by Pydantic models with
`model_config = ConfigDict(extra="allow")` so unknown fields and unknown
event types do not crash the consumer. Known event-type discriminators
today:

| `type` | Pydantic class | What HAM does |
|---|---|---|
| `server.connected` | `ServerConnected` | log only |
| `message.part.updated` | `AssistantMessageChunk` | accumulate text |
| `message.tool.start` | `ToolCallStart` | log only |
| `file.changed` | `FileChange` | record changed / deleted path |
| `session.permission.requested` | `PermissionRequest` | broker → allow/deny |
| `session.idle` | `SessionComplete` | mark mission done |
| `session.error` | `SessionError` | capture diagnostics |
| anything else | `UnknownEvent` | log warning, continue |

The SSE event JSON schemas are **not** published on the OpenCode docs
page; HAM must regenerate types from `/doc` at the pinned binary tag
during the first integration smoke. Pydantic `extra="allow"` is the
forward-compat hedge against drift.

### Permission broker policy

Pure logic in `src/ham/opencode_runner/permission_broker.py`. Default
deny-by-default categories:

| Category | Default | Notes |
|---|---|---|
| `read`, `glob`, `grep`, `list`, `lsp`, `todowrite` | allow | safe metadata reads |
| `edit`, `skill` | allow only inside project root | escapes denied |
| `bash`, `external_directory`, `task` | deny | beta posture |
| `webfetch`, `websearch` | deny | shorthand-only categories |
| anything else | deny | fail-closed default |

Bash denylist (applied even if `bash` is ever loosened):
`rm *`, `rm -rf *`, `find * -delete`, `git push *`, `git push --force*`,
`gcloud *`, `kubectl *`, `aws *`, `ssh *`, `scp *`, `curl *`, `wget *`.

A 30 s HAM-side permission-request deadline auto-denies a request that
sits unanswered — upstream OpenCode does not document a server-side
timeout for unanswered permission events.

### ControlPlaneRun status_reason map

Every terminal launch branch writes one `ControlPlaneRun` with
`provider="opencode_cli"`, `audit_ref=None`, and one of:

| `status_reason` | When |
|---|---|
| `opencode:snapshot_emitted` | snapshot succeeded |
| `opencode:nothing_to_change` | runner returned no `changed_paths` |
| `opencode:output_requires_review` | deletion guard tripped |
| `opencode:provider_not_configured` | readiness check failed at launch entry |
| `opencode:execution_disabled` | `HAM_OPENCODE_EXECUTION_ENABLED` off |
| `opencode:serve_unavailable` | spawned `opencode serve` failed health-poll |
| `opencode:permission_denied` | runner aborted because policy denied tool |
| `opencode:workspace_setup_failed` | `ensure_managed_working_tree` raised |
| `opencode:runner_error` | any other runner failure |

`provider_not_configured` and `execution_disabled` may be returned as a
plain 503 envelope without persisting a row (matches Claude Agent's
pattern of not persisting purely-disabled gate hits).

### Mission 3.1 alignment

The deletion guard at the snapshot boundary
(`compute_deleted_paths_against_parent`) is reused verbatim for the
OpenCode path. If any path would be deleted and
`HAM_OPENCODE_ALLOW_DELETIONS` is not truthy, HAM persists one terminal
`ControlPlaneRun` with `status_reason="opencode:output_requires_review"`
and **does not** call `emit_managed_workspace_snapshot`. This invariant
is locked by `tests/test_opencode_build_api.py::test_launch_persists_output_requires_review_on_deletion`
and the corresponding guard-bypass test.

### Env / gate matrix

| Env | Required for | Default |
|---|---|---|
| `HAM_OPENCODE_ENABLED` | provider visible in readiness / conductor | unset (lane disabled) |
| `HAM_OPENCODE_EXECUTION_ENABLED` | live execution (Mission 2) | unset (execution disabled) |
| `HAM_OPENCODE_EXEC_TOKEN` | `Authorization: Bearer …` on launch route | unset (launch returns `OPENCODE_LANE_UNCONFIGURED`) |
| `HAM_OPENCODE_ALLOW_DELETIONS` | bypass deletion guard | unset (guard active) |

### First-smoke plan

Out of scope for this commit. When the first live smoke is authorized:

1. Deploy the API image (with the `opencode` binary installed at a
   pinned tag) to a staging Cloud Run revision.
2. Set `HAM_OPENCODE_ENABLED=1`, `HAM_OPENCODE_EXECUTION_ENABLED=1`,
   and an `HAM_OPENCODE_EXEC_TOKEN` issued via Secret Manager.
3. Issue a preview against a sandbox managed-workspace project; confirm
   the response carries a 64-char digest and no host-path leakage.
4. Issue a launch with the digest; confirm a `ControlPlaneRun` row
   with `status="succeeded"` and `status_reason="opencode:snapshot_emitted"`
   or `opencode:nothing_to_change`.
5. Capture the first-run SSE event payloads from `/doc` against the
   Pydantic models in `event_consumer.py`; lock any drift in a
   follow-up PR.

### Risks before first live smoke

- SSE event JSON schemas remain integration-time risk. Pydantic
  `extra="allow"` is defensive but the discriminator names themselves
  could change.
- Permission-request timeout is currently 30 s; needs operational
  tuning after the first real run.
- `opencode serve` binary version pinning: HAM must document the
  minimum supported version once the first smoke succeeds.
- Containerized child-process reaping (`bash` / MCP subprocesses)
  needs OS-level verification under Cloud Run.

### Mission 3 forward pointer

Mission 3 lifts OpenCode into the HAM agent-builder UX (custom builder
profiles backed by OpenCode agent definitions). The runner package is
shaped so a future caller can pass a custom permission policy and a
custom config blob without touching the gated build route surface.

## 15. Runtime prerequisites (Mission 2.x)

Mission 2.x installs the OpenCode binary in the ham-api Cloud Run image
so the Mission 2 runner has a real `opencode` on `PATH`. The image
change is dormant at runtime: all four env gates in the matrix below
remain unset, so the lane stays disabled until an operator explicitly
authorizes a deploy.

### Pinned version

- Tag: [`v1.14.49`](https://github.com/anomalyco/opencode/releases/tag/v1.14.49) (2026-05-13).
- Single source of truth: `OPENCODE_PINNED_VERSION` in
  `src/ham/opencode_runner/version_pin.py`. Bump the Python constant
  and the Dockerfile `ARG OPENCODE_VERSION` together;
  `tests/test_opencode_version_pin.py` fails CI fast on drift.

### Install method

- Direct GitHub release tarball
  (`opencode-linux-x64.tar.gz`, glibc x86_64) downloaded inside the
  Dockerfile.
- SHA-256 verified with `sha256sum -c` before extraction
  (`OPENCODE_PINNED_LINUX_X64_SHA256` mirrored from the Python pin).
- A build-time `opencode --version` gate fails the image build if the
  installed binary's version string does not contain the pinned triple
  (permissive regex tolerant of `1.14.49`, `v1.14.49`, or
  `opencode 1.14.49` output formats).
- No npm / Bun / Homebrew toolchain on the image; the Bun-compiled
  binary is self-contained.

### Install location

`/usr/local/bin/opencode` — matches `shutil.which("opencode")` in
`src/ham/worker_adapters/opencode_adapter.py` and the default `$PATH`
for the Cloud Run runtime user.

### Deterministic ENV set by the image

| Env | Value | Why |
|---|---|---|
| `OPENCODE_DISABLE_AUTOUPDATE` | `1` | Keep the pinned binary pinned; no silent in-place upgrades. |
| `OPENCODE_DISABLE_MODELS_FETCH` | `1` | Skip the models.dev catalog fetch on startup; mission runs supply provider config explicitly. |
| `OPENCODE_DISABLE_CLAUDE_CODE` | `1` | Don't auto-detect the bundled Claude Code CLI; HAM owns the Claude Agent lane separately. |

These names are documented assumptions from upstream research; the
first authorized smoke must verify they actually disable the behaviors
named, and if upstream renames any of them the Dockerfile + this doc
must be updated together.

### Why `opencode serve` is still the primary integration

The image change only puts the binary on `PATH`; live execution still
goes through the `opencode serve` runner described in §14 of this
document. There is no separate "OpenCode sidecar" container, and the
adapter never invokes `opencode run` or the TUI.

### Runtime prerequisites for future deploy

- **`tini` / `dumb-init` reaper**: not wired in this commit. The
  Dockerfile's `ENTRYPOINT` is unchanged. `opencode serve` spawns
  bash/MCP children, so a reaper as PID 1 is required before any live
  Cloud Run revision is exposed to real traffic. Tracked as a separate
  authorized mission.
- **Cloud Run env**: a future revision must set
  `HAM_OPENCODE_ENABLED=1`, `HAM_OPENCODE_EXECUTION_ENABLED=1`, and
  `HAM_OPENCODE_EXEC_TOKEN=<secret>` (issued via Secret Manager). All
  three remain unset on the live revision today.
- **BYOK / backend provider keys**: Connected Tools BYOK records or
  HAM-managed provider keys (e.g. `OPENROUTER_API_KEY`) must be
  present for the runner to inject them via `PUT /auth/:id`. The image
  itself ships no keys.
- **Outbound network**: model-provider egress is already in place for
  the Claude Agent lane; OpenCode reuses the same posture.

### Env gates still required before execution

| Env | Required for | Default |
|---|---|---|
| `HAM_OPENCODE_ENABLED` | provider visible in readiness / conductor | unset |
| `HAM_OPENCODE_EXECUTION_ENABLED` | live execution (Mission 2) | unset |
| `HAM_OPENCODE_EXEC_TOKEN` | `Authorization: Bearer …` on launch route | unset |
| `HAM_OPENCODE_ALLOW_DELETIONS` | bypass Mission 3.1 deletion guard | unset |

### First-smoke checklist

1. Deploy a new Cloud Run revision built from this Dockerfile; verify
   `/api/status` returns 200.
2. Confirm `POST /api/opencode/build/preview` returns 503 with
   `detail.reason="opencode:execution_disabled"` while
   `HAM_OPENCODE_EXECUTION_ENABLED` is unset.
3. Operator authorizes the three gate env vars
   (`HAM_OPENCODE_ENABLED`, `HAM_OPENCODE_EXECUTION_ENABLED`,
   `HAM_OPENCODE_EXEC_TOKEN`) on the revision; redeploy.
4. Re-issue preview; confirm a digest-bearing response and no host-path
   leakage.
5. Issue a launch against a sandbox managed-workspace project.
6. Confirm a `ControlPlaneRun` row with
   `status_reason="opencode:snapshot_emitted"` (or
   `opencode:nothing_to_change`) and a clean Mission 3.1 deletion-guard
   record.
7. Capture and compare the first-run SSE event payloads against the
   Pydantic models in `event_consumer.py`; pin any drift in a follow-up.

### Risks not yet retired

- The `opencode --version` output format is assumed to contain the
  pinned semver triple; the permissive regex hedges against minor
  format changes but a major format change will fail the build by
  design.
- SSE event JSON schemas remain integration-time risk (Mission 2 doc,
  unchanged here).
- `OPENCODE_DISABLE_*` env names are documented assumptions; the first
  smoke must verify upstream still honors each name and behavior.

## 16. PID-1 reaper (Mission 2.y)

Mission 2.y wires a small PID-1 reaper into the ham-api Cloud Run
image so `opencode serve` subprocess fan-out (bash, MCP servers, tool
children) is reaped instead of accumulating as zombies. Like Mission
2.x, the image change is dormant at runtime: no env gates are flipped,
no Cloud Run deploy is in this commit.

### Why a reaper is required

`opencode serve` launches subprocess tools as direct children of the
process group it owns. When those children exit, their entries linger
in the kernel process table until a parent calls `wait()` on them.
The default `uvicorn` master under HAM does not, and Cloud Run does
not provide an init process for the container. Over the life of a
long-running revision that fans out hundreds of bash/MCP child
processes per session, this exhausts the per-container PID budget and
eventually wedges the runtime. The fix is to run a tiny dedicated
reaper as PID 1 that `wait(2)`s on any orphaned children.

### Choice of `tini`

Mission 2.y installs **`tini`** (Debian-packaged at
`/usr/bin/tini` in `bookworm`). Reasons:

- Available as a stable Debian apt package; pinned by the bookworm
  release HAM already builds against, no manual checksum to maintain.
- Small (≈10 KB binary, few hundred LOC of audited C); much lighter
  than `dumb-init`.
- Well-known reaper used by the upstream Docker docs ("Adding tini")
  and Kubernetes' shareProcessNamespace examples.
- Single-purpose: forward signals to the child and `wait(2)` on
  orphaned grandchildren — no extra behavior to reason about.

### ENTRYPOINT pattern

The Dockerfile keeps the existing `CMD` byte-for-byte and adds an
exec-form ENTRYPOINT immediately above it:

```dockerfile
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD exec uvicorn src.api.server:app --host 0.0.0.0 --port "${PORT:-8080}"
```

At runtime Docker exec's `tini` as PID 1, which in turn exec's the
existing CMD as its only child. CMD semantics (including Cloud Run's
`PORT` substitution and the existing `exec` keyword) are unchanged.

The pin lives in `src/ham/opencode_runner/version_pin.py` as
`TINI_INSTALL_PATH = "/usr/bin/tini"`, re-exported from
`src/ham/opencode_runner/__init__.py` for symmetry with
`OPENCODE_PINNED_VERSION`. Drift between the constant and the
Dockerfile ENTRYPOINT is caught by
`tests/test_dockerfile_entrypoint.py`.

### Runtime smoke checklist (first managed-workspace smoke)

The image change is dormant; live execution still requires an explicit
operator-authorized deploy with the gate envs set. When that deploy
happens, the first smoke must confirm:

1. `GET /api/status` returns 200 with `application/json`.
2. `POST /api/opencode/build/preview` returns 401 when unauthenticated
   (no operator session, no exec token).
3. `POST /api/opencode/build/launch` returns 401 when unauthenticated.
4. `POST /api/claude-agent/build/preview` returns 401 when
   unauthenticated (Mission 3.1 regression sentinel — the Claude Agent
   lane is unaffected by this commit and must keep its auth posture).
5. One preview-only invocation through the dashboard Clerk-auth flow,
   targeting `managed_workspace`.
6. If preview succeeds, exactly one corresponding launch.
7. Verify the resulting `ControlPlaneRun` row carries
   `status_reason="opencode:snapshot_emitted"` or
   `opencode:nothing_to_change` — never an unexpected reason code.
8. Verify the Mission 3.1 deletion guard still blocks deletions
   (no `HAM_OPENCODE_ALLOW_DELETIONS` override on the live revision,
   no deletion bypass logged in the audit JSONL).

### Env gates and secret requirements (unchanged by this commit)

Mission 2.y does not flip any env. Before any live execution, an
operator-authorized deploy must set:

- `HAM_OPENCODE_ENABLED=1` — provider visible in readiness / conductor.
- `HAM_OPENCODE_EXECUTION_ENABLED=1` — live execution allowed.
- `HAM_OPENCODE_EXEC_TOKEN` — bound from a Cloud Run Secret Manager
  secret (the secret name is chosen at deploy time and is **not**
  documented here; do not hard-code it). Used as the
  `Authorization: Bearer …` value on the launch route.
- Provider auth path: at least one of the existing credential surfaces
  must be configured (Connected Tools BYOK records, OpenRouter, the
  Anthropic backend key path used by the Claude Agent lane, or a HAM
  gateway). No new key name is introduced by Mission 2.y; the choice
  of which existing surface to bind is made at deploy time.
