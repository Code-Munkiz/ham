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
