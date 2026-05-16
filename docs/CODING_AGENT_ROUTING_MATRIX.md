# HAM Coding-Agent Routing Matrix

_Last updated: 2026-05-16_

---

## Purpose

This document describes how HAM's conductor (`POST /api/coding/conductor/preview`) selects and
ranks coding-agent candidates for a given user request. It is the canonical reference for product
intent, routing policy, and scoring rationale.

---

## Design principles

1. **HAM is the conductor.** No coding agent is exposed directly to the browser. Every
   agent harness (Factory Droid, Claude Agent, OpenCode, Cursor, Claude Code) is orchestrated
   through HAM's routing layer.

2. **Providers are overlapping harnesses, not rigid roles.** Each provider is a CLI-first
   execution surface. They differ in project prerequisites, model access model, and cost posture —
   not in some hard "only tool X does Y" partition. The conductor picks the best fit.

3. **Blockers demote, not eliminate.** A candidate with unresolved blockers stays visible in
   the response so the chat card can render "blocked because…" copy rather than silently hiding
   an option.

4. **Preferences boost, never bypass.** Workspace preference modes adjust confidence of
   approve-able candidates only. A blocked candidate cannot be force-unblocked by a preference.

5. **Normie labels in the UI, provider ids in the API.** The internal provider id
   (`opencode_cli`, `claude_agent`, etc.) never appears in user-facing copy. The conductor maps
   each to a normie-safe label (see §Labels).

---

## Providers

| Internal id | Normie label | Project type | Key prerequisite |
|---|---|---|---|
| `no_agent` | Conversational answer | any | none |
| `factory_droid_audit` | Controlled audit | any | Droid runner + audit workflow |
| `factory_droid_build` | Controlled managed builder | both | Droid runner + build token + build lane |
| `opencode_cli` | Open builder | `managed_workspace` | HAM_OPENCODE_ENABLED + model creds + workspace policy |
| `claude_agent` | Premium reasoning builder | `managed_workspace` | Claude Agent SDK + auth |
| `cursor_cloud` | Connected repo builder | `github_pr` | Cursor team key + GitHub repo |
| `claude_code` | Local single-file edit | any | Claude Code local SDK |

---

## Decision factors (evaluated in order)

### 1. Platform readiness (hard gate)

Each provider has a platform-level readiness probe in `readiness.py`. If the required
infrastructure is absent (runner not configured, SDK not installed, auth not present), the
candidate is present but marked `available: false` with a normie-safe blocker.

| Provider | Platform gate |
|---|---|
| `factory_droid_audit` | Droid runner reachable + audit workflow registered |
| `factory_droid_build` | Droid runner + `HAM_DROID_EXEC_TOKEN` + build workflow |
| `opencode_cli` | `HAM_OPENCODE_ENABLED=1` + `HAM_OPENCODE_EXECUTION_ENABLED=1` + one of `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `GROQ_API_KEY` |
| `claude_agent` | `claude-agent-sdk` installed + auth channel (Anthropic/Bedrock/Vertex) |
| `cursor_cloud` | Cursor team key configured (UI or env) |
| `claude_code` | Claude Code SDK installed + auth configured |
| `no_agent` | Always available |

### 2. Workspace policy (workspace-level permission)

After platform readiness, `WorkspaceAgentPolicy` applies workspace-level allow/deny flags.
Disabled providers are marked `available: false` with a policy blocker appended to their
blockers list. Policy never removes a provider from the response.

| Flag | Default | Controls |
|---|---|---|
| `allow_factory_droid` | `true` | `factory_droid_audit` + `factory_droid_build` |
| `allow_opencode` | **`false`** | `opencode_cli` (opt-in: requires explicit workspace model access) |
| `allow_claude_agent` | `true` | `claude_agent` |
| `allow_cursor` | `true` | `cursor_cloud` |

### 3. Project state (project-level blockers)

Project configuration adds task-specific blockers on top of platform readiness:

| Provider | Project blocker conditions |
|---|---|
| `factory_droid_build` | project not found; build lane disabled; managed_workspace target lacks `workspace_id`; github_pr target lacks GitHub repo |
| `opencode_cli` | project not found; output_target ≠ `managed_workspace`; build lane disabled; `workspace_id` not set |
| `cursor_cloud` | project not found; project has no GitHub repo |
| `factory_droid_audit` | project not found (optional; audit can run project-less) |

### 4. Task-kind fit (base confidence table)

The recommender maps `(task_kind, provider)` → base confidence (0.0–1.0). Cells absent from the
table mean the provider is not offered for that task kind.

#### Conversational / read-only

| task_kind | no_agent | factory_droid_audit |
|---|---|---|
| `explain` | **0.90** | — |
| `audit` | — | **0.85** |
| `security_review` | — | **0.85** |
| `architecture_report` | — | **0.85** |

#### Controlled / deterministic (Factory Droid strong)

| task_kind | factory_droid_build | cursor_cloud | opencode_cli |
|---|---|---|---|
| `doc_fix` | **0.80** | 0.55 | 0.45 |
| `comments_only` | **0.80** | 0.55 | 0.45 |
| `format_only` | **0.80** | — | 0.45 |
| `typo_only` | **0.85** | — | 0.45 |

Factory Droid is operator-governed and deterministic for these tasks. OpenCode is present but
scored below Factory Droid so it surfaces only when Factory Droid is blocked or unavailable.

#### Build / code-mutation (Cursor + OpenCode + Claude Agent compete)

| task_kind | cursor_cloud | opencode_cli | claude_agent | claude_code |
|---|---|---|---|---|
| `feature` | **0.80** | 0.65 | 0.60 | — |
| `fix` | **0.70** | 0.60 | 0.55 | 0.50 |
| `refactor` | **0.80** | 0.65 | 0.55 | — |
| `multi_file_edit` | **0.85** | 0.65 | 0.50 | — |
| `single_file_edit` | 0.50 | 0.50 | 0.60 | **0.70** |

**Managed-workspace effective ordering (cursor_cloud blocked by project type):**

For `managed_workspace` projects (no GitHub repo), `cursor_cloud` carries a project blocker and
is demoted below all approve-able candidates. Effective ordering for eligible providers:

| task_kind | 1st | 2nd |
|---|---|---|
| `feature` | opencode_cli (0.65) | claude_agent (0.60) |
| `fix` | opencode_cli (0.60) | claude_agent (0.55) |
| `refactor` | opencode_cli (0.65) | claude_agent (0.55) |
| `multi_file_edit` | opencode_cli (0.65) | claude_agent (0.50) |
| `single_file_edit` | claude_agent (0.60) | opencode_cli (0.50) |

**OpenCode is therefore the default open builder for managed-workspace tasks when eligible.**

### 5. Preference mode boost (+0.15 to approve-able candidate only)

| `preference_mode` | Boosted provider | Effect on managed-workspace feature task |
|---|---|---|
| `recommended` | none | opencode_cli wins (0.65) |
| `prefer_open_custom` | `opencode_cli` | opencode_cli → 0.80, wins strongly |
| `prefer_premium_reasoning` | `claude_agent` | claude_agent → 0.75, wins over opencode_cli |
| `prefer_connected_repo` | `cursor_cloud` | cursor_cloud boosted; only wins if unblocked |

The boost is applied **only to approve-able (unblocked) candidates.** A blocked candidate is
never boosted.

---

## Normie labels in chat UI

The conductor maps internal provider ids to user-facing copy before returning the response.
Raw ids (`opencode_cli`, `factory_droid_build`, etc.) must never appear in the chat card.

| Internal id | Chat card label | Approval kind |
|---|---|---|
| `no_agent` | Conversational answer | none |
| `factory_droid_audit` | Read-only audit | confirm |
| `factory_droid_build` (github_pr) | Low-risk pull request | confirm and accept PR |
| `factory_droid_build` (managed) | Managed workspace build | confirm |
| `opencode_cli` | Managed workspace edit (OpenCode) | confirm |
| `claude_agent` | Managed workspace edit (Claude Agent) | confirm |
| `cursor_cloud` | Cursor pull request | confirm |
| `claude_code` | Local single-file edit | confirm |

Workspace settings UI uses preference-mode labels (not provider ids):

| preference_mode | Settings label |
|---|---|
| `recommended` | Let HAM choose |
| `prefer_open_custom` | Open builder |
| `prefer_premium_reasoning` | Premium reasoning builder |
| `prefer_connected_repo` | Connected repo builder |

---

## Safety invariants (locked by tests)

- A candidate with `blockers` is **never** marked `available: true`.
- A blocked candidate's confidence is **never** boosted by preference mode.
- `unknown` task kinds **never** pick a mutating provider; the conductor falls back to
  `no_agent` or returns `chosen: null`.
- The `managed_workspace` deletion guard is enforced at launch time, not routing time; routing
  never weakens it.
- Provider ids, env-var names (`HAM_DROID_EXEC_TOKEN`, `CURSOR_API_KEY`, `ANTHROPIC_API_KEY`),
  runner URLs, and internal workflow ids (`safe_edit_low`, `readonly_repo_audit`) must never
  appear in any routing response (conductor, readiness, settings).
- `no_agent` is always present and always approve-able regardless of workspace policy.

---

## Adding a new provider

1. Add the provider id to `ProviderKind` in `types.py`.
2. Add normie-safe `_REASON`, `_SAFETY`, and `_LABEL` / `_OUTPUT_KIND` entries.
3. Add a platform readiness probe in `readiness.py`.
4. Add base confidence cells to `_BASE_CONFIDENCE` in `recommend.py`.
5. Add a `_POLICY_ALLOW_FLAG` entry in `readiness.py` if workspace policy should gate it.
6. Add project blocker logic in `_project_blockers_for` in `recommend.py`.
7. Write tests covering all four decision factors.

---

## Key source files

| File | Role |
|---|---|
| `src/ham/coding_router/types.py` | Shared types, enums, policy model |
| `src/ham/coding_router/recommend.py` | Base confidence table, scoring, preference boost |
| `src/ham/coding_router/readiness.py` | Platform readiness probes, policy application |
| `src/ham/coding_router/classify.py` | Task kind classifier |
| `src/api/coding_conductor.py` | HTTP route, label mapping, normie-safe response |
| `src/api/coding_agent_access_settings.py` | Workspace settings GET/PATCH |
| `src/persistence/coding_agent_access_settings_store.py` | Settings persistence |
| `tests/test_coding_recommend.py` | Routing matrix unit tests |
| `tests/test_coding_conductor_api.py` | Conductor HTTP tests |
| `tests/test_coding_agent_access_settings.py` | Policy + conductor integration tests |
