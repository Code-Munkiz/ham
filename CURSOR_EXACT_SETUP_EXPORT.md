# Cursor setup — exact export

Generated snapshot of `.cursor/` rules and skills, plus first-class context documents from the handoff source-of-truth list.

## File counts (this document)

| Category | Count |
|----------|-------|
| Rules (`.mdc`) | 16 |
| Skills (`SKILL.md`) | 8 |
| First-class context | 4 |
| **Total embedded files** | **28** |

**Subagents** (4): `subagent-*.mdc`. **Commands**: embedded in `commands.mdc`.

**Not embedded**: `README.md`, `SWARM.md`, `main.py`, pillar modules under `src/`, directory `tests/`, optional `.ham.json` / `.ham/settings.json`.

**Ambiguity / drift**: Rules and skills may describe behaviors (e.g. `MAX_DIFF_CHARS`, `ProjectContext.render` budget args) not yet present in `src/memory_heist.py`; verify against current code.

---

## `.cursor/rules/code-quality.mdc`

```
---
description: Code quality standards for the Ham codebase.
globs: "**/*.py"
alwaysApply: false
---

# Ham Code Quality

- Prefer public APIs over private-method access across module boundaries.
- Any growth-prone data path (summaries, diffs, timelines) must have an explicit hard cap.
- Keep filesystem and path logic cross-platform (Windows, Linux, macOS).
  - Do not assume `/` as separator in string matching.
  - Use `pathlib.Path` for all path construction.
  - Test with both forward and backslash separators when parsing message content.
- Prefer config-driven budgets and dependency injection over long-term hardcoded context budget values. Load per-agent limits from `.ham.json` / merged project config where possible; use code constants only as safe fallbacks.
- Add or update tests for any behavioral change.
- Follow the conventions in `SWARM.md`.
```

---

## `.cursor/rules/commands.mdc`

```
---
description: Custom slash commands for Ham project workflows. Apply always.
alwaysApply: true
---

# Ham Commands

## /audit-context-engine

Run the Context Engine Auditor checklist against `src/memory_heist.py`.

1. Read `src/memory_heist.py`.
2. Walk the Context Engine Hardening skill checklist (`.cursor/skills/context-engine-hardening/SKILL.md`), including continuation/parser marker coupling.
3. Report findings as a table: item, status (pass/fail), detail.
4. Do not auto-fix. Present findings for review.

## /wire-agent-context

Wire shared repo context into Hermes-supervised role prompts in `src/swarm_agency.py` (context assembly only; no CrewAI).

1. Read the Agent Context Wiring skill (`.cursor/skills/agent-context-wiring/SKILL.md`).
2. Read `src/swarm_agency.py` and `src/memory_heist.py`.
3. Add `from src.memory_heist import ContextBuilder` (or equivalent) if missing.
4. **Single discovery pass**: build **one** `ProjectContext` (or one `ContextBuilder` that shares a single discovered context) and vary **only render budgets** per agent. Do not create multiple `ContextBuilder()` instances that each run a full `ProjectContext.discover()` (duplicate scans and git calls).
5. Prefer loading per-agent budgets from `.ham.json` / config (`discover_config`) over long-term hardcoded magic numbers; use code defaults only as fallback.
6. Inject per-role rendered context strings into each active role backstory/prompt surface.
7. Run lints. Present diff for review. Update `VISION.md` status if wiring completes a milestone.

## /review-role-boundaries

Audit all agent definitions for role boundary violations.

1. Read the Role Boundaries rule (`.cursor/rules/role-boundaries.mdc`).
2. Read `src/swarm_agency.py`.
3. For each agent, check: does its `goal`, `tools`, and task assignments stay within its charter?
4. Report violations as a table: agent, field, violation, suggested fix.

## /test-context-regressions

Generate or run regression tests for `src/memory_heist.py`.

1. Read the Repo Context Regression Testing skill (`.cursor/skills/repo-context-regression-testing/SKILL.md`).
2. If `tests/test_memory_heist.py` exists, read it and check coverage against the skill's test categories.
3. If it does not exist, generate it with `pytest` + `tmp_path` fixtures covering all 6 categories.
4. Run `pytest tests/test_memory_heist.py -v` and report results.

## /rebrand-memory-heist

Scan `src/memory_heist.py` for any remaining Claude/Claw references and replace with Ham equivalents.

1. Read `src/memory_heist.py`.
2. Grep for `claude`, `Claude`, `CLAUDE`, `claw`, `Claw`, `stolen`, `Stolen` (case-insensitive).
3. If matches found, apply replacements per the memory-heist-conventions rule.
4. If no matches, report clean.

## /refresh-swarm-contract

Re-validate the entire swarm against `VISION.md`.

1. Read `VISION.md`.
2. Read all pillar modules: `src/swarm_agency.py`, `src/tools/droid_executor.py`, `src/hermes_feedback.py`, `src/memory_heist.py`, `src/llm_client.py`.
3. For each pillar, check: does the module's current code match the role described in `VISION.md`?
4. Check: is `memory_heist.py` imported and used by the active orchestration path (currently `swarm_agency.py`)?
5. Check: do current role definitions respect supervisory-vs-execution boundaries?
6. Report as a table: pillar, module, vision role, actual status, gaps.
7. If the table fixes factual drift, apply updates to `VISION.md` (status table and next milestone) per the vision-sync rule.
```

---

## `.cursor/rules/ham-architecture.mdc`

```
---
description: Enforces the Ham core architecture contract. Apply always.
alwaysApply: true
---

# Ham Architecture Contract

The architecture is fixed unless the user explicitly approves a change.

## Core Pillars

| Pillar | Module | Role |
|--------|--------|------|
| Supervisory Core | Hermes (`src/hermes_feedback.py`) | Supervisory orchestration, critique, and learning signals |
| Execution Engine | Factory Droid CLI (`src/tools/droid_executor.py`) | Implementation-heavy execution with bounded local self-orchestration |
| Context Engine | `src/memory_heist.py` | Repo scanning, git state, config, session memory |
| LLM Routing | LiteLLM / OpenRouter (`src/llm_client.py`) | Model-agnostic API layer, BYOK |

## Rules

- **Hermes is the sole supervisory orchestrator.** Do not add CrewAI, LangGraph,
  AutoGen, or other third-party *orchestration* frameworks. (LLM calls via
  LiteLLM/OpenRouter are fine; orchestration policy lives in Hermes.)
- Do not merge, split, or reassign pillar responsibilities.
- Hermes is not a monolith and not a second execution engine.
- Hermes may self-handle only tiny, bounded, critic-native tasks.
- Droid retains execution ownership; do not collapse execution into Hermes.
- Ambiguous execution work defaults to Droid.
- Do not bypass memory_heist for repo context -- agents must consume `ContextBuilder.build()`.
- Do not hardcode model names outside `llm_client.py`.
- Reference `VISION.md` for the canonical architecture diagram.
```

---

## `.cursor/rules/ham-direct-main-workflow.mdc`

```
---
description: Owner-local HAM workflow — direct-main, no automatic PRs. Does not restrict owner local main pushes; Cloud/HAM VM/Git lives in AGENTS + cloud-agent-starter only.
alwaysApply: true
---

# HAM git workflow (testing / direct-main)

## Scope (owner-local canonical only)

**Everything below applies only** when you are the **human owner** working from a **trusted local canonical repo**. It does **not** apply to Cloud Agents, **HAM VM**, or other ephemeral workspaces.

**HAM VM / Cloud Agent / ephemeral remotes:** do **not** use this workflow for lands. Follow **`AGENTS.md`** (**Cloud Agent / HAM VM Git policy**) and **`cloud-agent-starter`**: **branch → push branch → PR**; **never** **`git push origin main`** or **force-push `main`**.

## Standing rule (owner-local)

- Do **not** create draft PRs by default.
- Do **not** run unless the user **explicitly** asks for a PR:
  - `gh pr create`
  - `gh pr ready`
  - `gh pr edit`
  - Suggestions to “open a PR”, “create draft PR”, or “push feature branch for review”

## Default: work on `main`

1. `git status --short --branch` and `git branch --show-current`.
2. If not on `main`: `git checkout main` then `git pull origin main`.
3. Make the change; **stage only intended files**.
4. **Never stage**: `.cursor/settings.json`, `desktop/live-smoke/`, repomix outputs, build artifacts, temp scripts, unrelated dirty files.
5. Run **scoped** tests for the change.
6. Commit on `main`: `git commit -m "<clear message>"`.
7. Push: `git push origin main`.

Report after push: commit hash, files changed, tests run, pushed yes/no, deploy/smoke if applicable.

## If `git push origin main` is blocked

Do **not** open a PR automatically. Stop and report:

- `DIRECT_MAIN_PUSH_BLOCKED`
- `reason:`
- `required action:`

## PR exception — only when the user says one of

- “open a PR” / “make a draft PR” / “use feature branch” / “do this as PR review”

## Draft PR clutter

- Do **not** create more draft PRs for routine work.
- Before large or messy work, optionally **list** draft PRs (`gh pr list --draft` if available) and **classify** (merged/superseded, docs-only safe to close, contains useful unmerged work, unknown) — **do not close or merge** until the user approves a batch plan.
```

---

## `.cursor/rules/ham-local-control-boundary.mdc`

```
---
description: HAM local control must target the user’s local Windows runtime with a mandatory desktop lane; escalation chat → browser-real → machine; cloud browser is ancillary. Agents must verify before patching and preserve Linux behavior.
alwaysApply: true
---

# HAM Local Control Boundary Rule

HAM local browser/machine control must target the end user’s local Windows runtime, not a hosted VM/browser as the primary product path.

## Required product lanes

HAM must support both:

1. **Web app lane**
   - HAM Web App acts as the command UI.
   - It must pair with a trusted local Windows runtime/bridge.
   - The local runtime performs browser and machine control.
   - The web app must not pretend it can directly control the user’s machine without the local bridge.

2. **Desktop / IDE lane**
   - HAM Desktop/IDE app must include, launch, or connect to the same local Windows control runtime.
   - This lane is mandatory, not optional.

## Control sequence

Escalation model:

`chat → local browser-real → local machine control`

- **Browser-real** is the first control rung for web/navigation tasks.
- **Machine control** is an escalation path when browser-real is blocked, partial, or insufficient.

## Cloud/hosted browser runtime

Cloud Run or VM browser runtime may be used for hosted web-task support, API metadata validation, or non-local automation, but **it is not the primary end-user control plane**.

Do not optimize Phase 3 around Cloud Run controlling a browser unless explicitly requested.

## Safety invariants

Never weaken:

- Kill switch.
- Armed Local Control requirement.
- Browser-real permission requirement.
- URL policy from `desktop/local_control_browser_url.cjs`.
- Dedicated HAM browser profile.
- localhost-only CDP.
- Bounded screenshots.
- IPC channel compatibility.
- Deny-by-default behavior.

Never use the user’s default browser profile.

Never expose raw profile paths to renderer payloads.

Never add broad inbound network listeners for local control.

## Implementation rule

Verify first; patch only confirmed gaps; preserve Windows/shared Electron local-control parity; keep changes minimal-diff. (Linux desktop **installer** artifacts are not shipped from the repo; workspace **GoHAM chat/browser execution** was removed—see `VISION.md`.)
```

---

## `.cursor/rules/hermes-workspace-repomix-ssot.mdc`

```
---
description: Hermes Workspace UI/UX parity — repomix SSOT must exist before parity implementation.
globs: frontend/src/features/hermes-workspace/**/*, docs/**/*
alwaysApply: false
---

# Hermes Workspace repomix (UI/UX SSOT)

**Required reference file (exact name):**

`repomix-output-outsourc-e-hermes-workspace.git.txt`

**Expected locations (in order):**

1. Repository root: `repomix-output-outsourc-e-hermes-workspace.git.txt`
2. Or under `docs/` if your team stores it there (note: `docs/repomix-*` is gitignored — keep a local copy or team-approved tracked path)

## Rule

For **Workspace UI/UX parity** work (Inspector, workspace shell, Hermes-lifted screens, IA/layout/tone vs upstream Hermes Workspace):

1. **Confirm the repomix file is present** (search the repo and parent workspace folders if needed).
2. **If missing:** **stop and report** — do not implement parity from in-repo screens alone. Locate the file from the team, or regenerate via repomix from the upstream Hermes Workspace export, then proceed.
3. **Do not** silently fall back to “use existing HAM components as SSOT” for **UI/UX parity** slices. Runtime wiring may still use HAM APIs/adapters after UX intent is taken from the repomix.
4. **Do not commit** the repomix unless the user explicitly approves (large file / vendor dump). `.gitignore` may already exclude `docs/repomix-*`.

## Exception (narrow)

Purely **runtime/data** slices that do not change layout/IA/tone (e.g. read-only summaries using existing HAM APIs only) may proceed **only when the user explicitly scopes the task that way** — and the report must state that repomix was not used and why.
```

---

## `.cursor/rules/memory-heist-conventions.mdc`

```
---
description: Conventions specific to the Context Engine module.
globs: src/memory_heist.py
alwaysApply: false
---

# memory_heist.py Conventions

- If you encounter Claude-specific wording, config paths, or file references, replace them with Ham equivalents:
  - `CLAUDE.md` -> `SWARM.md`
  - `.claude` dir -> `.ham` dir
  - `.claude.json` -> `.ham.json`
  - "Stolen" / "Claw Code" -> neutral language
- Instruction constants: `INSTRUCTION_FILENAMES`, `INSTRUCTION_DOT_DIR`, `INSTRUCTION_DOT_FILES` must reference Ham names only.
- Config paths in `discover_config()` must reference `.ham.json` / `.ham/` only. No Claude fallbacks.
- `IGNORE_DIRS` must include `.sessions` and `.hermes`.
- Token budget constants (`MAX_*`) must remain configurable via `ContextBuilder` constructor params.
- Session compaction output must have hard character caps to prevent unbounded growth.

## Continuation / parser coupling (critical)

`_format_continuation()` and `_extract_prior_summary()` are coupled: the latter uses substring markers to slice prior summaries out of the first system message.

- If you change the closing lines of `_format_continuation()`, you **must** update `end_markers` in `_extract_prior_summary()` to match.
- Preserve **backward compatibility**: keep markers for both the previous phrasing and the new phrasing until old `.sessions` JSON files are no longer loaded, or document a one-time migration.
- After any change here, add or extend tests that parse a sample continuation string built with the new format (and optionally the legacy format).
```

---

## `.cursor/rules/minimal-diffs.mdc`

```
---
description: Enforces minimal, scoped diffs. Apply always.
alwaysApply: true
---

# Minimal Diff Policy

- Change only what the task requires. Do not redesign unrelated modules.
- Do not refactor stable code unless the task explicitly calls for it.
- Do not add speculative features, utilities, or abstractions beyond the ask.
- If a change spans more than 3 files, provide an impact map and justification before editing.
- Preserve existing public API signatures unless breakage is the stated goal.
```

---

## `.cursor/rules/no-hallucinated-state.mdc`

```
---
description: Prevents hallucinated repo state. Apply always.
alwaysApply: true
---

# No Hallucinated Repo State

- Read the actual file before proposing or applying changes. Never assume contents.
- Run `git status` / `git diff` before claiming what is staged, modified, or clean.
- Do not invent filenames, function signatures, or import paths from memory.
- If a file does not exist, say so. Do not silently create a replacement.
- When referencing constants, configs, or module-level values, quote the real value from the file.
- Do not claim tests passed unless they were actually run and the output is shown.
- Do not claim files were updated unless the diff shows the change.
```

---

## `.cursor/rules/registry-record-conventions.mdc`

```
---
description: "Registry record conventions for src/registry/*.py — stable IDs, version fields, pure-data records, derived metrics live outside."
globs: src/registry/*.py
alwaysApply: false
---

# Registry Record Conventions

Keep registry-layer record types small, serializable, and free of derived state so they stay portable and honest.

## Scope

Applies to record types and registry classes under `src/registry/`. Shipped examples: `IntentProfile` in `profiles.py`, `BackendRecord` in `backends.py`. Run JSON written under `.ham/runs/` from `main.py` is related in spirit—pure persisted facts, no derived metrics on the blob—but it is not a dedicated class and does not share the same field layout as those BaseModels.

## Do This

- Define record types as plain Pydantic `BaseModel` subclasses with no custom methods beyond what Pydantic provides.
- Give every registry record a stable string `id` field.
- Give every registry record a `version: str` field with a sensible default (currently `"1.0.0"`).
- Add `metadata: dict[str, Any] = Field(default_factory=dict)` for untyped UX or display data that must not pollute the core contract.
- Expose registry records through public accessors (e.g. `ProfileRegistry.get`, `BackendRegistry.get_record`); do not read `_profiles`, `_backends`, or other private attributes outside the defining module.
- Keep derived metrics (progression, reliability, latency aggregates) out of registry records; compute them from run history under `.ham/runs/` when needed.

## Do NOT

- Do not add business logic methods to registry record types.
- Do not add fields for computed or derived state on registry records.
- Do not reach into `_backends`, `_profiles`, or other private registry internals from outside that registry module.
- Do not introduce new registry record types outside `src/registry/` without strong cause; if another module needs one, define it in `src/registry/` and import from there.
- Do not store gamification concepts (level, XP, rank, badges, aggregate stats) on registry records; treat those as views over run history, not record fields.

## Rationale

Registry records are pure data; derived metrics and rollups live elsewhere. That separation keeps artifacts portable (export/import, future marketplace) and avoids baking computed state into types that should round-trip cleanly. It also keeps honest progression and future provenance work tractable by confining derived views to run history and consumers—not to the registry record shapes themselves. Do not assume every persisted artifact uses the same field schema as those BaseModels.
```

---

## `.cursor/rules/role-boundaries.mdc`

```
---
description: Enforces strict agent role boundaries in the swarm.
alwaysApply: true
---

# Agent Role Boundaries

Each agent has a fixed charter. Do not blur roles.

| Agent | Does | Does NOT |
|-------|------|----------|
| **Architect** | Plan, design interfaces, set constraints, choose patterns | Write implementation code, invoke tools, execute commands |
| **Hermes (sole supervisory orchestrator)** | Route jobs, coordinate execution handoffs to Droid, run critique / learning; self-handle only tiny bounded critic-native tasks | Become a second execution engine, own broad code/test/build execution, absorb the Architect planning charter |
| **Droid Executor** | Execute implementation-heavy code/shell work; may self-orchestrate locally while executing | Own global supervisory policy, critique governance, or architecture planning |

- When adding a new agent, define its charter before writing code.
- Ambiguous execution work defaults to Droid.
- When modifying `swarm_agency.py` (Hermes-supervised **context assembly** only), verify backstories and budgets stay aligned with these boundaries—there is no CrewAI or second orchestrator.
```

---

## `.cursor/rules/subagent-architect-auditor.mdc`

```
---
description: "Subagent charter: Architect Auditor. Applies when reviewing swarm_agency.py agent definitions."
globs: src/swarm_agency.py
alwaysApply: false
---

# Subagent: Architect Auditor

## Charter

Audit the Architect agent's definition in `src/swarm_agency.py` for alignment with the Ham vision.

## Scope -- Do This

- Verify the Architect agent's `role`, `goal`, and `backstory` match its charter: planning, interfaces, constraints.
- Verify the Architect does NOT have execution tools in its `tools` list.
- Verify the Architect receives full instruction context via grounded repo context (shared `ProjectContext` + appropriate budgets — not N independent full discovers).
- Check that tasks assigned to the Architect are planning/design tasks, not implementation.

## Out of Scope -- Do NOT

- Redesign the Hermes-supervised routing/critic backstory surfaces or the active run graph.
- Introduce CrewAI or another third-party orchestration framework.
- Modify `memory_heist.py` or `llm_client.py`.
```

---

## `.cursor/rules/subagent-context-engine-auditor.mdc`

```
---
description: "Subagent charter: Context Engine Auditor. Applies when reviewing memory_heist.py."
globs: src/memory_heist.py
alwaysApply: false
---

# Subagent: Context Engine Auditor

## Charter

Audit `src/memory_heist.py` for safety, correctness, and alignment with the Ham architecture.

## Scope -- Do This

- Verify all naming references Ham terminology (no Claude/Claw residue).
- Verify `IGNORE_DIRS` covers `.sessions`, `.hermes`, and standard noise directories.
- Verify all `MAX_*` constants have sane defaults and are overridable.
- Verify `git_diff()` output is capped.
- Verify `_summarize()` Timeline and `_merge_summaries()` have hard caps.
- Verify `_extract_key_files()` works cross-platform (no separator-only guard).
- Verify `_format_continuation()` uses agent-appropriate language.
- Verify `ContextBuilder.with_memory()` uses public API only.
- Verify `_format_continuation()` and `_extract_prior_summary()` end markers stay in sync; legacy markers present if old session JSON must still load.

## Out of Scope -- Do NOT

- Redesign the session compaction algorithm.
- Add LLM-backed summarization (separate task).
- Modify agent definitions in `swarm_agency.py`.
```

---

## `.cursor/rules/subagent-execution-safety-auditor.mdc`

```
---
description: "Subagent charter: Execution Safety Auditor. Applies when reviewing droid_executor.py."
globs: src/tools/droid_executor.py
alwaysApply: false
---

# Subagent: Execution Safety Auditor

## Charter

Audit the Droid executor for safety and correct execution ownership boundaries.

## Scope -- Do This

- Verify `droid_executor` has a clear, typed invocation surface and docstring.
- Verify subprocess calls use `capture_output=True`, `text=True`, and a `timeout`.
- Verify stdout/stderr output is capped before returning to the agent.
- Verify execution-heavy work remains delegated to Droid (not absorbed by Hermes supervisory logic).
- Check that the tool does not allow arbitrary shell injection beyond its intended scope.

## Out of Scope -- Do NOT

- Modify agent role definitions.
- Change the Context Engine.
- Alter LLM routing.
```

---

## `.cursor/rules/subagent-reviewer-loop-auditor.mdc`

```
---
description: "Subagent charter: Reviewer Loop Auditor. Applies when reviewing hermes_feedback.py."
globs: src/hermes_feedback.py
alwaysApply: false
---

# Subagent: Reviewer Loop Auditor

## Charter

Audit the Hermes review loop for correctness and alignment with the learning pipeline.

## Scope -- Do This

- Verify `HermesReviewer.evaluate()` has a stable public signature: `(code: str, context: str | None) -> dict`.
- Verify the return dict includes at minimum: `ok`, `notes`, `code`, `context`.
- Verify Hermes-supervised role context in `swarm_agency.py` does not absorb Droid execution responsibilities.
- Verify `.hermes/` is in `IGNORE_DIRS` in `memory_heist.py`.
- When real hermes-agent integration lands, verify it writes to `.hermes/` and the FTS5 DB path is configurable.

## Out of Scope -- Do NOT

- Redesign the orchestration graph to use a non-Hermes framework (e.g. CrewAI).
- Change the Context Engine's compaction logic.
- Modify the Droid executor.
```

---

## `.cursor/rules/vision-sync.mdc`

```
---
description: Keep VISION.md aligned with actual repo state after milestone work.
alwaysApply: true
---

# VISION.md Synchronization

After completing any milestone that changes repo reality (Context Engine wired, Droid/Hermes integrated, tests added, major hardening merged), update `VISION.md` so it stays accurate.

- **Current State table** (pillar module status): each row must reflect the real implementation state (scaffold, stub, hardened, wired, etc.).
- **Next milestone** section: replace completed items with the next concrete goal.
- **Architecture text and diagrams**: if a pillar's role, wiring, or data flow changed, update the prose description and the ASCII diagram to match. Do not leave diagrams that show connections that don't exist yet as if they are live.
- Do not leave stale text like "needs rebranding" if rebranding is already done.

When in doubt, run `/refresh-swarm-contract` and apply the gap findings to `VISION.md`.
```

---

## `.cursor/skills/agent-context-wiring/SKILL.md`

```
---
name: agent-context-wiring
description: >-
  Wire memory_heist ContextBuilder into Hermes-supervised role prompts in swarm_agency.py
  using a single shared ProjectContext and per-role render budgets. Use when connecting
  Hermes-led flows to repo context, adjusting budgets, or integrating SessionMemory. (No CrewAI.)
---

# Agent Context Wiring

## When to Use

- Integrating `ContextBuilder` into `src/swarm_agency.py`
- Setting per-role token / instruction / diff budgets
- Wiring `SessionMemory` into the active Hermes-supervised flow

## Anti-pattern: N full scans

**Do not** create one `ContextBuilder()` per agent if each constructor calls `ProjectContext.discover()` independently. That repeats `scan_workspace`, instruction discovery, config merge, and multiple git subprocess calls.

## Preferred pattern: one discovery, vary render only

1. Call `ProjectContext.discover()` **once** (or construct one `ContextBuilder` that owns a single `project` snapshot).
2. For each role, render context with **different budgets** (instruction caps, diff caps) by passing parameters into render helpers — or add a small API on `ContextBuilder` / `ProjectContext` such as `render_for_role(budgets=...)`.
3. Concatenate each role's static instruction line + that rendered string into the active prompt/backstory surface.

Example shape (adapt to actual `memory_heist` API after hardening):

```python
from src.memory_heist import ProjectContext
from src.swarm_agency import HamRunAssembly

def assemble_ham_run(user_prompt: str) -> HamRunAssembly:
    project = ProjectContext.discover()

    arch_text = project.render(
        max_total_instruction_chars=16_000,
        max_diff_chars=8_000,
    )
    cmd_text = project.render(
        max_total_instruction_chars=4_000,
        max_diff_chars=2_000,
    )
    # ... critic with its own budgets; attach llm + droid per production wiring ...

    return HamRunAssembly(
        user_prompt=user_prompt,
        architect_backstory=f"You plan structure and interfaces.\n\n{arch_text}",
        commander_backstory=(
            "You are the Hermes-supervised routing surface: delegate execution to Droid.\n\n"
            f"{cmd_text}"
        ),
        critic_backstory="...",
        llm_client=None,
        droid_executor=lambda cmd: "...",
    )
```

Until `ProjectContext.render()` accepts budget overrides, implement the minimal change in `memory_heist.py` to support this pattern rather than constructing multiple discoverers.

## Config-driven budgets

Prefer reading per-role budgets from merged project config (`discover_config` / `.ham.json`) with sane code defaults. Avoid leaving magic numbers only in `swarm_agency.py` long-term.

## Budget guidelines (defaults until config exists)

| Role surface | Instruction budget (total) | Diff budget | Rationale |
|-------|---------------------------|-------------|-----------|
| Architect | Higher (e.g. 16,000) | Full (e.g. 8,000) | Planning / interfaces |
| Hermes routing (`commander_*` config keys) | Lower (e.g. 4,000) | Tighter (e.g. 2,000) | Delegation & sequencing |
| Hermes review / critic | Medium (e.g. 8,000) | Default | Critique & learning context |

## Verification

1. Every Hermes-supervised role surface receives repo-grounded context in its prompt/backstory.
2. Repo scan + git capture runs **once** per `assemble_ham_run` build (unless explicitly refreshing after Droid).
3. Budgets are tunable via config when available.
```

---

## `.cursor/skills/cloud-agent-starter/SKILL.md`

```
---
name: cloud-agent-starter
description: >-
  Minimal starter runbook for Cloud agents to install, run, and test Ham quickly.
  Covers backend/frontend startup, chat gateway modes, Cursor key setup, browser
  runtime checks, and how to keep this skill current as new runbook knowledge is found.
---

# Cloud Agent Starter — run + test Ham fast

## When to use

- First run in a fresh Cloud workspace
- Any task that needs local app startup and quick health checks
- Any task that touches chat/gateway modes, browser runtime, or Cursor API wiring

## Cloud Agent / HAM VM Git policy

HAM VM **and** Cursor Cloud / ephemeral workspaces are **not** the owner’s canonical checkout. **`main` is read-only here for pushes** — but you **are expected to push feature branches** and **open PRs** when landing work.

You **may**:

- create a branch, commit scoped changes, `git push -u origin <branch>`, **`gh pr create`** into **`main`** for code/product changes.
- skip `gh pr create` only when the mission is **report-only/read-only**, or when the operator said **no PR** / dry run only.

You **must not**:

- **`git push origin main`** (`upstream main` included).
- `--force`, `--force-with-lease`, or any rewrite of **`refs/heads/main`** on the remote.
- treat this clone as **SSOT for `main`** or “repair **`main`**” from here.

If asked to **`push main`**, return **`MAIN_PUSH_REQUIRES_OWNER_LOCAL_CONTEXT`**, **`I can push this to a branch and open a PR instead.`**, then **create branch + PR** per **`AGENTS.md`** → **Cloud Agent / HAM VM Git policy**.

Never use **`git push --force*`** targeting remote **`main`**.

## 1) Fast setup (do this first)

From repo root:

1. Install backend deps:
   - `python3 -m pip install -r requirements.txt`
2. Install pytest (not in `requirements.txt`):
   - `python3 -m pip install pytest`
3. Install frontend deps:
   - `npm install --prefix frontend`
4. Create local env file:
   - `cp .env.example .env`

## 2) Authentication + mode defaults (practical)

### Chat mode (feature flag you usually set first)

- `HERMES_GATEWAY_MODE=mock` (default safe local mode; no external key needed)
- Real model calls:
  - Set `HERMES_GATEWAY_MODE=openrouter`
  - Set `OPENROUTER_API_KEY=...`
- External OpenAI-compatible gateway:
  - Set `HERMES_GATEWAY_MODE=http`
  - Set `HERMES_GATEWAY_BASE_URL=...`
  - Optional: `HERMES_GATEWAY_API_KEY=...`

### Cursor Cloud API key ("login")

- Option A (env): set `CURSOR_API_KEY` in `.env`.
- Option B (API, persists server-side):
  - `POST /api/cursor/credentials` with `{ "api_key": "..." }`
- Verify key identity:
  - `GET /api/cursor/credentials-status`

### Write-protected routes (set only when needed)

- `HAM_SETTINGS_WRITE_TOKEN` for project settings apply/rollback
- `HAM_RUN_LAUNCH_TOKEN` for operator launch_run turns
- `HAM_SKILLS_WRITE_TOKEN` for Hermes skills install apply

## 3) Start the app (backend + frontend)

Use two terminals/tmux panes:

- Backend (repo root), **recommended for dashboard + Vite smoke:**
  - `python3 scripts/run_local_api.py` — loads optional `.env`, defaults `HERMES_GATEWAY_MODE=mock`, keeps API-side Clerk enforcement off via `HAM_LOCAL_DEV_LOOSE_CLERK` (default `1`; set `HAM_LOCAL_DEV_LOOSE_CLERK=0` to tighten).
- Backend (alternate, bare uvicorn):
  - `python3 -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000` — set gateway + Clerk variables yourself when hitting authenticated workspace routes with a strict policy.
- Frontend (`frontend/`):
  - `npm run dev`

Quick smoke checks:

- `curl -sS http://127.0.0.1:8000/api/status`
- `curl -sS -I http://127.0.0.1:3000`
- Open `http://127.0.0.1:8000/docs`

## 4) Testing workflows by codebase area

## A) Context Engine (`src/memory_heist.py`)

- Run focused suite:
  - `python3 -m pytest tests/test_memory_heist.py -q`
- Use when touching repo scan, config discovery, git diff capture, or session compaction.

## B) Hermes reviewer/supervision (`src/hermes_feedback.py`)

- Run focused suite:
  - `python3 -m pytest tests/test_hermes_feedback.py -q`
- Use when touching review loop, critique prompts, or learning-signal shaping.

## C) Droid registry/execution metadata (`src/registry`, `src/tools`)

- Run focused suite:
  - `python3 -m pytest tests/test_droid_registry.py -q`
- Use when changing droid records, defaults, or registry behavior.

## D) API surface (`src/api/*`)

Run backend, then smoke test key routes:

- `curl -sS http://127.0.0.1:8000/api/status`
- `curl -sS -X POST http://127.0.0.1:8000/api/chat -H 'content-type: application/json' -d '{"messages":[{"role":"user","content":"hello"}]}'`
- `curl -sS http://127.0.0.1:8000/api/context-engine`

Mode-specific check:

- In mock mode, `/api/chat` should return a "Mock assistant reply..." response.

## E) Frontend (`frontend/`)

- Type/lint gate:
  - `npm run lint --prefix frontend`
- Manual check:
  - Open `http://127.0.0.1:3000`
  - Confirm dashboard loads and can call backend (`/api/status`, chat UI flows)

## F) Browser runtime (`src/api/browser_runtime.py`)

Prereq for full runtime behavior:

- `python3 -m playwright install chromium`

Minimal checks:

- `curl -sS http://127.0.0.1:8000/api/browser/policy`
- Create a session:
  - `curl -sS -X POST http://127.0.0.1:8000/api/browser/sessions -H 'content-type: application/json' -d '{"owner_key":"local-dev"}'`

Useful env flags:

- `HAM_BROWSER_ALLOW_PRIVATE_NETWORK=true|false`
- `HAM_BROWSER_ALLOWED_DOMAINS=...`
- `HAM_BROWSER_BLOCKED_DOMAINS=...`
- `HAM_BROWSER_SESSION_TTL_SECONDS=...`

## G) Managed Cursor missions (Cloud Agent feed)

Use when you need **managed mission** APIs or the **mission feed** path (not the same as Bridge `RunStore` or `ControlPlaneRun`).

- **Roadmap + shipped vs partial:** `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`
- **Workspace chat → operator launch routing (smoke):** `docs/HAM_CLOUD_AGENT_ROUTING_SMOKE.md`
- **Feed projection (SDK bridge vs REST):** env `HAM_CURSOR_SDK_BRIDGE_ENABLED` (`true` / `1` / `yes` → live bridge in `src/integrations/cursor_sdk_bridge_client.py` + `bridge.mjs`; otherwise REST projection). Rollback in prod: set to `false` without changing launch URLs — see roadmap § "Rollback control".
- **Launch token (deploy / browser):** `HAM_CURSOR_AGENT_LAUNCH_TOKEN` — see `docs/DEPLOY_CLOUD_RUN.md` § "Cloud Agent launch token".
- **List missions (read):** `curl -sS http://127.0.0.1:8000/api/cursor/managed/missions` (requires working Cursor credentials when exercising live Cursor-backed rows).

### PR / docs checklist (prevent duplicate Cloud Agent PR churn)

HAM launch prompts inject **cursor-agent-v2** PR hygiene; match it in Cursor Cloud agent behavior.

**Ephemeral / VM:** default to **branch + PR** (see **Git writes** above). **Owner-local** workflows in `AGENTS.md` may still avoid PRs when the **owner** is driving from a known canonical path.

1. **Plan/report first.** For **code/product** landings from Cloud/VM, **open a PR** when work is complete. **Do not** avoid `gh pr create` just to stay on `main` remotely.
2. **No unsolicited docs-only PRs** — edit canonical Markdown in-place where possible (`AGENTS.md`, `README.md`, roadmap/mission-aware docs).
3. **Before a docs PR:** `gh pr list --repo OWNER/REPO --state open --limit 50` — if overlaps exist → report `OVERLAPPING_DOCS_PR_FOUND` instead of spawning another duplicate.
4. **One mission ⇒ at most one PR** when PRs were explicitly authorized.
5. Regenerate **`CURSOR_EXACT_SETUP_EXPORT.md`** only via `python scripts/build_cursor_export.py`; do not hand-edit as a prose duplicate.
6. Deeper governance: **`AGENTS.md`** → *Cloud Agent PR hygiene* section.

## 5) Common quick fixes

- `python3 -m pytest ...` fails with `No module named pytest`:
  - Run `python3 -m pip install pytest`
- `uvicorn` not found in PATH:
  - Use `python3 -m uvicorn ...` instead of bare `uvicorn`.
- Chat endpoint errors in non-mock mode:
  - Re-check `HERMES_GATEWAY_MODE` and matching credentials in `.env`.

## 6) Keep this skill updated

When you discover a new reliable runbook trick:

1. Add it under the correct codebase area above (do not add a generic dump section).
2. Include one concrete command and one expected result.
3. Prefer focused tests (`tests/test_*.py`) over full-suite runs.
4. Remove stale steps immediately when routes/env names change.
5. Keep this file minimal; move deep architecture details to `AGENTS.md`/`VISION.md`.
```

---

## `.cursor/skills/context-engine-hardening/SKILL.md`

```
---
name: context-engine-hardening
description: >-
  Harden memory_heist.py against token blowouts, unbounded growth, cross-platform
  path bugs, stale Claude references, and continuation/parser marker drift. Use when
  modifying memory_heist.py, fixing compaction logic, capping diffs, or adding safety
  limits to the Context Engine.
---

# Context Engine Hardening

## When to Use

- Modifying `src/memory_heist.py`
- Fixing token budget issues, diff size blowouts, or summary growth
- Ensuring cross-platform path handling (Windows/Linux/macOS)
- Removing residual Claude-specific naming
- Changing `_format_continuation()` or `_extract_prior_summary()`

## Checklist

1. Read `src/memory_heist.py` before making changes.
2. Verify `IGNORE_DIRS` includes `.sessions` and `.hermes`.
3. Verify all instruction constants reference Ham names (`SWARM.md`, `.ham`).
4. Verify `discover_config()` uses `.ham.json` / `.ham/` paths only.
5. Check that `git_diff()` output is capped by `MAX_DIFF_CHARS` (when implemented).
6. Check that `_summarize()` caps the Timeline to the last N messages (e.g. 20).
7. Check that `_merge_summaries()` truncates the previous summary to prevent nesting growth.
8. Check that `_extract_key_files()` does NOT gate on `"/" in token` only — extension-based detection for cross-platform paths.
9. Check that `_format_continuation()` uses agent-appropriate language, not chatbot phrasing.
10. **Continuation / parser coupling**: If `_format_continuation()` text changes, update `_extract_prior_summary()` `end_markers` to match; keep legacy markers for backward compatibility with existing session JSON until migrated.
11. Run lints on `src/memory_heist.py` after changes.
12. Add or update tests for any behavioral change (see Repo Context Regression Testing skill).

## Key Constants to Audit

| Constant | Default | Purpose |
|----------|---------|---------|
| `MAX_INSTRUCTION_FILE_CHARS` | 4,000 | Per-file instruction cap |
| `MAX_TOTAL_INSTRUCTION_CHARS` | 12,000 | Total instruction budget |
| `MAX_DIFF_CHARS` | 8,000 | Git diff output cap |
| `MAX_SUMMARY_CHARS` | 4,000 | Compaction summary cap |

All of these should be overridable via `ContextBuilder` constructor params once wiring is complete.
```

---

## `.cursor/skills/factory-droid-workflows/SKILL.md`

```
---
name: factory-droid-workflows
description: How Ham previews and launches allowlisted Factory droid exec workflows from chat (readonly audit vs low-risk edit), runner assumptions, and hard security limits. Instructional only — policy lives in code.
---

# Factory Droid workflows (Ham chat)

## What this is

Ham can drive **two allowlisted** Factory **`droid exec`** workflows from the **server-side chat operator**, using **preview → confirm → launch**. This skill explains vocabulary and process for humans and agents. **It is not the policy source of truth** — see `src/ham/droid_workflows/registry.py` and `docs/FACTORY_DROID_CONTRACT.md`.

## Workflows (Phase 1)

| `workflow_id` | Tier | Mutates | Launch token |
|-----------------|------|---------|--------------|
| `readonly_repo_audit` | `readonly` | No | Not required |
| `safe_edit_low` | `low_edit` | Yes (`--auto low`) | **`HAM_DROID_EXEC_TOKEN`** bearer required |

## How to use from chat

1. **Preview** (natural language example):

   `preview factory droid readonly_repo_audit: focus on API security and tests`

   Include a registered project id in the message (e.g. `project.foo-bar`) or send chat with `project_id` set.

2. Read **`operator_result.pending_droid`**: `proposal_digest`, `base_revision`, `droid_user_prompt`, `mutates`, `summary_preview`.

3. **Launch** — send `operator` JSON with:

   - `phase`: `droid_launch`
   - `confirmed`: `true`
   - `project_id`, `droid_workflow_id`, `droid_user_prompt` (same as preview)
   - `droid_proposal_digest`, `droid_base_revision` from `pending_droid`
   - For **`safe_edit_low`**: `Authorization: Bearer <HAM_DROID_EXEC_TOKEN>`

Structured preview without NL: `phase: droid_preview` with `droid_workflow_id` + `droid_user_prompt`.

## Prerequisites

- **Runner host** has `droid` installed, Factory auth (e.g. `FACTORY_API_KEY`), and filesystem access to the **registered project root** the API uses.
- **Phase 1** assumes **co-location** (API runs `droid` locally) unless you deploy the documented **remote runner** HTTP seam (`HAM_DROID_RUNNER_URL`).
- Custom Droid names in a workflow must exist under **`.factory/droids/*.md`** on that repo; otherwise preview **blocks** (fail closed).

## Tier meanings

- **`readonly`:** no `--auto`; intended for audits and read-only analysis.
- **`low_edit`:** `droid exec --auto low` — tightly scoped doc/comment/typo class edits per registry template; not a general coding agent.

## What is explicitly not allowed

- **No arbitrary shell** from chat — only registry-built argv and templated prompts.
- **No** `--skip-permissions-unsafe` (forbidden in code).
- **No** `FACTORY_API_KEY` in the browser, chat prompts, or Ham logs.
- **No** mutating launch without **preview**, **confirm** (`confirmed=true`), and **bearer** where required.
- **No** launching on unknown `workflow_id`, bad digest, stale registry revision, or inaccessible project root.
- **No** Custom Droid authoring from chat in Phase 1.

## Where to read more

- Contract: `docs/FACTORY_DROID_CONTRACT.md`
- Control plane: `docs/HAM_CHAT_CONTROL_PLANE.md`
- Code: `src/ham/droid_workflows/`, `src/integrations/droid_runner_client.py`, `src/ham/chat_operator.py`
```

---

## `.cursor/skills/goham/SKILL.md`

```
---
name: goham
description: >-
  Guides conversational navigation of the Ham dashboard: settings sections, projects,
  Droids/registry, runs and activity, and how to scaffold sub-agent workflows or new
  assets using existing APIs and configs. Use when the user wants natural-language help
  finding settings, understanding Hermes vs Droid roles, creating workflows or agents, or
  pairing chat with the workspace UI without reading raw logs.
---

# GoHam — conversational product navigation

## When to use

- User asks **where** something lives in Ham (settings, API, CLI).
- User wants **step-by-step** setup: project, Droid profile, run inspection, context engine.
- User is **designing or wiring** dashboard chat and needs **accurate** product truth (sections, routes, pillars).
- User mentions **sub-agent workflows** or **creating** registry/workspace artifacts—ground answers in this repo, not generic agent tutorials.

## Read order

1. `AGENTS.md` — where implementation lives.
2. `VISION.md` — pillars and boundaries.
3. This skill — **UI/API/workflow map** (keep in sync when navigation changes).
4. Repo `SWARM.md` — project coding instructions.

## Pillars (short)

| Piece | Module(s) | Role |
|-------|-----------|------|
| Supervisory / critic | `src/hermes_feedback.py` | Review, learning signals; not the primary chat product unless wired. |
| Execution | `src/tools/droid_executor.py`, Bridge | Heavy work via CLI subprocess; auth stays with the tool. |
| Context | `src/memory_heist.py` | Repo scan, git, config, sessions—inject for grounded NL. |
| LLM | `src/llm_client.py` | Model calls; keys server-side. |
| Hermes-supervised context | `src/swarm_agency.py` | Single shared `ProjectContext` discovery + per-role prompts; **Hermes-led** orchestration only (no CrewAI). |
| API | `src/api/server.py` | Dashboard backend; extend with chat when implemented. |

## Conversational layer (intent)

- **Skill alone** improves accuracy for agents (e.g. Cursor) that load it.
- **Product “talk to Ham”** still needs in-app chat wired to the backend plus optional **actions** (API calls, deep links). When chat is stub-only, tell the user the **exact** UI path or `curl`/endpoint.

## Guardrails

- Do not invent settings tabs or API paths—**read** `frontend` and `src/api/server.py` or documented reference when unsure.
- Do not expose secrets in chat; API keys stay server/env.
- If Hermes **Agent** (Nous product) vs **Hermes** (this repo critic) is ambiguous, disambiguate once.

## Verification

- Instructions match current `AGENTS.md` and actual routes/settings IDs after IA changes.
- Prefer linking to canonical docs over duplicating `VISION.md`.
```

---

## `.cursor/skills/hermes-review-loop-validation/SKILL.md`

```
---
name: hermes-review-loop-validation
description: >-
  Validate the Hermes supervisory critic review loop: verify Hermes receives
  correct context, invokes HermesReviewer.evaluate(), and preserves learning
  signals for later persistence. Use when modifying hermes_feedback.py, the
  supervisory review path, or the review pipeline.
---

# Hermes Review Loop Validation

## When to Use

- Modifying `src/hermes_feedback.py`
- Changing Hermes-supervised context/backstory wiring in `src/swarm_agency.py`
- Integrating the real hermes-agent client
- Verifying FTS5 persistence after reviews

## Review Loop Contract

```
Execution output
      |
      v
Hermes supervisory critic path
      |
      v
HermesReviewer.evaluate(code, context)
      |
      v
FTS5 DB (persist learning signals)
```

## Validation Checklist

1. Hermes review logic must reference critique and learning signals, not broad execution ownership.
2. Hermes review path must not absorb Droid execution responsibilities.
3. `HermesReviewer.evaluate()` must receive the actual code output, not a summary.
4. `HermesReviewer.evaluate()` must receive repo-grounded context (from `ContextBuilder` / `ProjectContext` render path).
5. When the real hermes-agent client is integrated:
   - Verify it writes to `.hermes/` directory
   - Verify `.hermes/` is in `IGNORE_DIRS` so agents don't ingest the DB as source
6. The evaluate response must include structured fields: `ok`, `notes`, `code`, `context` at minimum.

## Current State

`HermesReviewer.evaluate()` is implemented with a stable schema and conservative
fallback behavior. Durable FTS5 learning persistence remains deferred.
```

---

## `.cursor/skills/prompt-budget-audit/SKILL.md`

```
---
name: prompt-budget-audit
description: >-
  Audit token budgets across the Ham swarm to prevent context window overflows.
  Use when checking prompt sizes, reviewing MAX_* constants, or diagnosing
  truncation issues in agent outputs.
---

# Prompt Budget Audit

## When to Use

- Diagnosing agent output truncation or degraded quality
- Reviewing `MAX_*` constants in `src/memory_heist.py`
- Checking total prompt size before supervisory orchestration execution
- After changing instruction files, config, or git diff caps

## Audit Steps

1. Read `src/memory_heist.py` and note all `MAX_*` constants.
2. For each Hermes-supervised role surface in `src/swarm_agency.py`, estimate total prompt/backstory size:
   - `ContextBuilder.build()` output size (instructions + git state + tree + config)
   - Plus the static backstory string
3. Compare against the model's context window (check `src/llm_client.py` for model ID).
4. Flag any agent whose estimated prompt exceeds 50% of the context window.
5. Check `SessionMemory.estimate_tokens()` -- the `chars // 4` heuristic can be 20-30% off for code-heavy content. Flag if compaction threshold is too close to the window limit.

## Common Model Context Windows

| Model | Window | 50% Budget |
|-------|--------|------------|
| Claude 3.5 Sonnet | 200K | 100K |
| GPT-4o | 128K | 64K |
| Llama 3.1 70B | 128K | 64K |

## Red Flags

- `git_diff()` returning >8K chars without `MAX_DIFF_CHARS` cap
- `_summarize()` Timeline section with >20 messages
- `_merge_summaries()` nesting without truncation
- `render_instruction_files()` hitting the budget cap silently
```

---

## `.cursor/skills/repo-context-regression-testing/SKILL.md`

```
---
name: repo-context-regression-testing
description: >-
  Test that memory_heist.py correctly scans the repo, discovers configs and
  instructions, captures git state, and compacts sessions without data loss.
  Use when adding tests for Context Engine changes or verifying cross-platform behavior.
---

# Repo Context Regression Testing

## When to Use

- After any behavioral change to `src/memory_heist.py`
- When adding new entries to `IGNORE_DIRS` or `INTERESTING_EXTENSIONS`
- When modifying config discovery, instruction loading, or session compaction
- When verifying cross-platform path handling

## Test Categories

### 1. Workspace Scanning
- `scan_workspace` respects `IGNORE_DIRS` (does not descend into `.sessions`, `.hermes`, `.git`)
- `scan_workspace` respects `max_files` cap
- `scan_workspace` only returns files with `INTERESTING_EXTENSIONS`
- `workspace_tree` respects `max_depth`

### 2. Instruction Discovery
- `discover_instruction_files` finds `SWARM.md` at project root
- `discover_instruction_files` finds `.ham/SWARM.md` in dot-dir
- `discover_instruction_files` deduplicates identical files
- `render_instruction_files` respects `MAX_INSTRUCTION_FILE_CHARS` and `MAX_TOTAL_INSTRUCTION_CHARS`

### 3. Config Discovery
- `discover_config` loads `.ham.json` from home and project dirs
- `discover_config` merges configs with correct precedence (user < project < local)
- `discover_config` does NOT look for `.claude.json`

### 4. Git State
- `git_diff` output is capped at `MAX_DIFF_CHARS`
- `git_diff` includes `--stat` summary when diff is truncated

### 5. Session Compaction
- `_summarize` Timeline is capped at 20 messages
- `_merge_summaries` truncates previous summary to prevent nesting growth
- `compact()` reduces total token estimate, not increases it
- `save()` / `load()` round-trips without data loss
- `_extract_prior_summary` recognizes both current and legacy `_format_continuation` end markers (if backward compatibility is required)

### 6. Cross-Platform
- `_extract_key_files` detects `src/foo.py`, `src\foo.py`, and bare `foo.py`

## Test Location

All tests go in `tests/test_memory_heist.py`. Use `pytest` with `tmp_path` fixtures for filesystem tests.
```

---

## `AGENTS.md`

```
# Ham — Agent Context Index

This file declares which files are first-class project context. Any agent
working on this repo should read these before proposing changes.

## Read order (recommended)

1. `VISION.md` — pillars, boundaries, and how components connect
2. This file — where implementation lives (see § *Git workflow* for direct-main testing; Cursor: `ham-direct-main-workflow.mdc`)
3. `SWARM.md` — repo coding instructions (loaded by `memory_heist`)
4. `PRODUCT_DIRECTION.md` — product lens: HAM-native model vs reference ecosystems
5. `docs/TEAM_HERMES_STATUS.md` (when changing Command Center, Activity, Capabilities, or desktop Hermes copy) — **API-side** vs **desktop-side** operator story, boundaries, troubleshooting

## Ham bet: memory, Hermes, and CLI-native muscle

Three ideas stay stable while execution backends evolve:

1. **Repo-grounded context (`memory_heist`)** — Workspace truth (scan, git, merged `.ham` config, instruction files, session compaction) is assembled once and injected into agents so supervision and planning do not hallucinate project state.

2. **Hermes learning loop (`hermes_feedback`)** — Critique and structured review over **evidence-shaped outcomes** (bridge/run envelopes, capped text). The goal is a compounding signal: routing and quality improve over time; durable institutional memory is still incremental (see `GAPS.md` and hardening docs).

3. **CLI-first execution surface** — Heavy work is delegated to **CLI-based agentic runtimes** (subprocess + framed IO), not re-embedded vendor HTTP stacks inside Ham. **Auth and account state stay with the tool** (its login flows, tokens on disk, device/browser steps). Ham supplies **scoped intent, policy limits, and capture**; Hermes reasons over **comparable envelopes** regardless of whether the muscle is Factory/Droid-style, Claude Code–style, ElizaOS-flavored hosts, OpenClaw-informed gateways, or future adapters—**one supervision vocabulary, many CLIs**.

**Narrow exception (interactive dashboard chat):** The Ham API may expose **`POST /api/chat`** with **HAM-native** JSON to the browser and implement it via a **server-side adapter** to an external OpenAI-compatible agent API (see `docs/HERMES_GATEWAY_CONTRACT.md`, `src/integrations/nous_gateway_client.py`). The browser **never** calls that gateway directly. This does **not** replace **`HermesReviewer`** / `main.py` critique-on-run flow—they stay separate.

Shipped muscle today centers on **Bridge + Droid executor** (`src/tools/droid_executor.py`, `src/bridge/`). Reference notes (patterns only, not parity targets): `docs/reference/factory-droid-reference.md`, `docs/reference/openclaw-reference.md`, `docs/reference/elizaos-reference.md`. Ham remains **HAM-native** in naming and contracts; see `PRODUCT_DIRECTION.md`.

## Architecture

- `.cursor/rules/ham-local-control-boundary.mdc` — local control boundary (web UI + Windows bridge, mandatory desktop/IDE lane, escalation patterns, ancillary cloud **`/api/browser`**, verify-first/minimal-diff; Linux **installers removed** — see rule file)
- `VISION.md` — canonical architecture, core pillars, design principles
- **`src/ham_cli/`** — HAM operator CLI v1 (`python -m src.ham_cli` or `./scripts/ham`): `doctor`, `status`, `api status`, **`desktop package win`** — diagnostics + **Windows** desktop packaging helpers; not chat/missions (see `main.py` for bridge/Hermes one-shot CLI)
- `docs/CONTROL_PLANE_RUN.md` — `ControlPlaneRun` substrate (v1 file-backed: `src/persistence/control_plane_run.py`): durable provider-neutral launch record (Cursor/Droid) + Cursor status updates, separate from bridge runs and audit JSONL; read API: `src/api/control_plane_runs.py` (`GET /api/control-plane-runs`, `GET /api/control-plane-runs/{ham_run_id}`) — not orchestration, queues, or mission graphs
- `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md` — what’s shipped vs partial vs out of scope for Cursor Cloud Agent + `ManagedMission`, and phased gap closure (correlation, optional Hermes-on-mission, honest E2E scope)
- `docs/MISSION_AWARE_FEED_CONTROLS.md` — mission-scoped live feed + operator controls (`mission_registry_id`); client transcript rendering over bounded feed `events`

## Pillar modules

- `src/hermes_feedback.py` — Hermes supervisory core + critic/learner surface (`HermesReviewer` MVP complete; supervisory wiring still transitional)
- `src/tools/droid_executor.py` — Droid execution engine (implementation-heavy execution; local self-orchestration while executing)
- `src/memory_heist.py` — Context Engine (repo scan, git state, config, sessions)
- `src/llm_client.py` — LiteLLM / OpenRouter wiring
- `src/swarm_agency.py` — Hermes-supervised **context assembly** (shared `ProjectContext` + per-role render budgets for Architect / routing / critic prompts); **not** a separate orchestration framework (no CrewAI)
- `src/registry/droids.py` — `DroidRecord` + `DroidRegistry` + `DEFAULT_DROID_REGISTRY` (builder, reviewer)
- `src/persistence/run_store.py` — read-side `RunStore` over `.ham/runs/*.json`
- `src/api/server.py` — FastAPI app: read API (`/api/status`, `/api/runs`, …) plus **`POST /api/chat`**, **`POST /api/chat/stream`** (see `src/api/chat.py` — optional `project_id` + **HAM active agent guidance** from Agent Builder; distinct from Cursor operator skills and Hermes CLI profiles), **`GET /api/cursor-skills`** (Cursor operator skills), **`GET /api/hermes-skills/*`** (Hermes **runtime** skills catalog + host probe + **Phase 2a** shared install preview/apply; see `src/api/hermes_skills.py`, `src/ham/hermes_skills_install.py`), **`GET /api/capability-library/*`** and **`POST .../save|remove|reorder`** (per-project **My library** of saved `hermes:` / `capdir:` catalog refs; `HAM_CAPABILITY_LIBRARY_WRITE_TOKEN`; see `src/api/capability_library.py`, `src/ham/capability_library/`), **`GET /api/cursor-subagents`**, **`GET /api/projects/{id}/agents`** (HAM agent builder profiles; on `app` in `src/api/server.py`), and **project settings** preview/apply (`src/api/project_settings.py`, `HAM_SETTINGS_WRITE_TOKEN` for mutating routes)
- `src/ham/cursor_skills_catalog.py` — loads `.cursor/skills` for chat control plane + API index (operator docs; **not** Hermes runtime skills)
- `src/ham/hermes_skills_catalog.py` — vendored Hermes-runtime catalog manifest (`src/ham/data/hermes_skills_catalog.json`)
- `scripts/build_hermes_skills_catalog.py` — regenerate catalog from pinned **NousResearch/hermes-agent** (`skills/` + `optional-skills/`); requires network unless `--repo-root` points at a checkout
- `src/ham/hermes_skills_probe.py` — read-only Hermes home / profile discovery (`HAM_HERMES_SKILLS_MODE=remote_only` for non-co-located APIs)
- `src/ham/hermes_skills_install.py` — Phase 2a shared-target install: HAM-managed bundles under `~/.hermes/ham-runtime-bundles/`, merge `skills.external_dirs` in Hermes `config.yaml`, atomic write, lock, backup + audit (`HAM_HERMES_SKILLS_SOURCE_ROOT` + `.ham-hermes-agent-commit` pin, `HAM_SKILLS_WRITE_TOKEN` for apply)
- `src/ham/cursor_subagents_catalog.py` — loads `.cursor/rules/subagent-*.mdc` for chat + **`GET /api/cursor-subagents`**
- `src/ham/ui_actions.py` — parse/validate `HAM_UI_ACTIONS_JSON` for chat → UI
- `src/ham/settings_write.py` — allowlisted writes to `.ham/settings.json` (backup + audit); includes **`agents`** subtree (HAM agent profiles + `primary_agent_id`)
- `src/ham/agent_profiles.py` — Pydantic models + validation for HAM agent profiles (Hermes runtime skill catalog ids on `skills: string[]`; not Hermes CLI profiles)
- `src/ham/active_agent_context.py` — compact **guidance** block from primary HAM agent profile + vendored Hermes catalog entries for `/api/chat` (context only; no install/execution)
- `docs/HAM_CHAT_CONTROL_PLANE.md` — chat + skills intent mapping roadmap

## Deploy (API on GCP)

- **Staging SOT:** GCP project **`clarity-staging-488201`**, region **`us-central1`**, Cloud Run **`ham-api`** — see `docs/DEPLOY_CLOUD_RUN.md` (Cursor key via **Secret Manager** `ham-cursor-api-key` → env `CURSOR_API_KEY`).
- `Dockerfile` — Cloud Run–style image (`uvicorn src.api.server:app`, `PORT` aware)
- `docs/DEPLOY_CLOUD_RUN.md` — Artifact Registry + `gcloud builds submit` + `gcloud run deploy` + env vars + **private Hermes on GCE** (Direct VPC egress preferred, Serverless VPC connector fallback)
- `docs/DEPLOY_HANDOFF.md` — Vercel + Cloud Run checklist (what to set in each host)
- `docs/examples/ham-api-cloud-run-env.yaml` — copy to `.gcloud/ham-api-env.yaml` for `--env-vars-file`
- `docs/HERMES_GATEWAY_CONTRACT.md` — server-side adapter to Hermes/OpenAI-compatible chat (streaming `http` mode)
- `scripts/verify_ham_api_deploy.sh` — CORS + `/api/chat` + stream smoke test; **fails if responses look like `mock`** unless `HAM_VERIFY_ALLOW_MOCK=1`
- `scripts/render_cloud_run_env.py` — merge `.env` secrets into env YAML for deploy (`OPENROUTER_API_KEY` for openrouter; **`HERMES_GATEWAY_API_KEY`** for `http` when set in `.env`)

## Configuration & entry

- `main.py` — runtime entrypoint (CLI arg parsing, env load, orchestration assembly)
- `SWARM.md` — project-level coding instructions (loaded by memory_heist)
- `AGENTS.md` — this file
- `requirements.txt` — Python dependencies
- `README.md` — project overview and pointers
- `.env.example` — environment variable template
- `.ham.json` / `.ham/settings.json` — project config (if present)

## Hardening & remediation

- `docs/HAM_HARDENING_REMEDIATION.md` — audit summary, continuation/parser coupling, remediation order, deferred work

## Git workflow (testing / direct-main)

Two audiences: **owner/local canonical** vs **HAM VM / Cloud Agent / ephemeral remotes**.

### Cloud Agent / HAM VM Git policy

**HAM VM, Cursor Cloud Agents, and other ephemeral/remote automation environments** — **branch + PR only**:

**They may:**

- create a **feature branch** from `main` (use a descriptive, collision-safe branch name such as `cursor/<topic>-<shortid>`).
- commit **scoped** changes only.
- **`git push origin <that-branch>`** (or `-u origin <branch>` on first push).
- **`gh pr create`** targeting **`main`** when landing **product or code changes**.

**Typical landing sequence:**

```txt
git checkout -b <safe-branch-name>
git add <exact files>
git commit -m "<message>"
git push -u origin <safe-branch-name>
gh pr create --title "<title>" --body "<body>"
```

**They must not:**

- **`git push origin main`** (or any variant that advances remote `refs/heads/main` directly).
- **force-push** `main`: no `git push --force*` to `origin main` / upstream `main`.
- **repair or overwrite remote `main`** from this clone.
- Treat this workspace as **canonical source of truth** for **`main`** ( **`MAIN_PUSH_REQUIRES_OWNER_LOCAL_CONTEXT`** applies).

If asked to push to **`main`**:

1. Respond with **`MAIN_PUSH_REQUIRES_OWNER_LOCAL_CONTEXT`** and plain language:
   **`I can push this to a branch and open a PR instead.`**
2. Then carry out **`git checkout -b …` → push branch → `gh pr create`** as above.

**Read-only / report-only missions:** if the mission is strictly investigation with **no landed code/doc commits**, summarize without `gh pr create` unless the operator asked you to ship a change.

**Docs-only churn:** Prefer **in-place edits** per *Cloud Agent PR hygiene* later in this section. Use `gh pr list` overlap checks before any docs-only PR. If `gh` is unavailable or returns an auth error (for example HTTP 401), you cannot satisfy the overlap scan from automation alone—coordinate with a human who has `gh auth login`, or extend an existing open docs PR/branch manually; do not open parallel duplicate docs PRs blindly.

**Incident note (2026-04):** a VM force-push overwrote GitHub `main`; combine this policy with **branch protection** and tight VM credentials until access is productized (prefer **GitHub App** tokens).

---

### Owner-local canonical (direct `main`)

**Owner/local canonical repo** is a workstation **you control** with a trusted path (e.g. `C:\Projects\GoHam\ham`). **Nothing here blocks you** from pushing to **`main`** when **you intend to**. The **direct-`main`** flow below applies **only** in that environment.

For **that** workflow, prefer **`main` directly** — not feature branches or automatic PRs.

**Standing rule (owner-local):** Do not create draft PRs by default. Do not run `gh pr create`, `gh pr ready`, `gh pr edit`, or suggest opening a PR / pushing a feature branch for review **unless** the user explicitly asks for a PR.

**Procedure (owner-local canonical only):**

1. `git status --short --branch` and `git branch --show-current`.
2. If not on `main`: `git checkout main`, then `git pull origin main`.
3. Apply the requested change. Stage **only** intended files.
4. **Do not stage:** `desktop/live-smoke/`, repomix outputs, build artifacts, temp scripts, unrelated dirty files, or your local Cursor settings file at .cursor/settings.json (gitignored).
5. Run **scoped** tests for the touched area.
6. Commit on `main`: `git commit -m "<clear commit message>"`.
7. Push: `git push origin main`.

**Report:** commit hash, files changed, tests run, pushed yes/no, deploy/smoke status if applicable.

**If direct push to `main` is blocked** (branch protection, permissions): do **not** create a PR automatically. Stop and report `DIRECT_MAIN_PUSH_BLOCKED` with reason and required action.

**PR exception** — only when the user explicitly says e.g. “open a PR”, “make a draft PR”, “use feature branch”, or “do this as PR review”.

**Draft PRs:** Do not add PR clutter. Before substantial work, you may list and **classify** open draft PRs (superseded, docs-only safe to close, contains useful unmerged work, unknown); do **not** close or merge automatically until classified and the user approves a batch plan. Cursor enforces the short form of these rules in `.cursor/rules/ham-direct-main-workflow.mdc`.

**Separate cleanup run** — paste when you want a dedicated draft-PR audit (agents classify only; no auto-close/merge unless clearly safe):

```md
Clean up HAM draft PR clutter safely.

## Goal

There are many draft PRs for small docs notes. I want to stop accumulating PR clutter.

## Instructions

1. List all open draft PRs.

2. For each draft PR, classify:

- `SUPERSEDED_BY_MAIN`
- `DOCS_ONLY_SAFE_TO_CLOSE`
- `CONTAINS_UNMERGED_USEFUL_WORK`
- `UNKNOWN_REVIEW_NEEDED`

3. For each PR, report:
- PR number
- title
- branch
- changed files
- whether its commits are already in `main`
- recommended action

4. Do not close or merge anything yet unless clearly safe.

5. After classification, ask for approval with a batch plan:
- close these PRs
- merge these PRs
- leave these open
```

## Guidance

- `.cursor/rules/` — Cursor project rules (architecture, diffs, roles, vision sync)
- `.cursor/skills/` — eight reusable operator skills (see skills table in [`CURSOR_SETUP_HANDOFF.md`](CURSOR_SETUP_HANDOFF.md))
- `CURSOR_SETUP_HANDOFF.md` — human guide to rules, skills, subagents, commands
- `CURSOR_EXACT_SETUP_EXPORT.md` — verbatim snapshot of Cursor setup + first-class docs (regenerate via `python scripts/build_cursor_export.py`)
- `GAPS.md` — tracked gaps and active implementation notes

## Frontend (workspace UI)

- `desktop/` — Milestone 1 Electron shell (thin wrapper; see `desktop/README.md`); `npm start` after `npm run dev` in `frontend/`
- `frontend/` — Vite + React workspace; `npm run dev` (port 3000), `npm run lint` (`tsc --noEmit`)
- `frontend/src/features/hermes-workspace/screens/skills/WorkspaceSkillsScreen.tsx` — **Skills** catalog UI (`/workspace/skills`, with redirects from `/skills` and `/hermes-skills`); distinct from Cursor operator skills; API remains `/api/hermes-skills/*`

## Tests

- `tests/test_memory_heist.py` — Context Engine + Phase 1/3 guardrails (23 cases)
- `tests/test_hermes_feedback.py` — Critic MVP + Phase 3 guardrails (7 cases)
- `tests/test_droid_registry.py` — Droid registry conventions (10 cases)
- Run: `python -m pytest` — full suite (`pytest.ini` sets `pythonpath = .`; run `pytest tests/ --collect-only -q` for current count — on the order of 1200+ tests)
- Other tests under `tests/` as added; bootstrap with `/test-context-regressions` for Context Engine focus

## Cursor Cloud specific instructions

### Services overview

| Service | Command | Port | Notes |
|---------|---------|------|-------|
| Backend API | `python3 scripts/run_local_api.py` | 8000 | Sets `HERMES_GATEWAY_MODE=mock` + loose Clerk by default |
| Frontend | `npm run dev` (in `frontend/`) | 3000 | Vite proxies `/api/*` to `:8000` automatically |

### Startup caveats

- **pytest is not in `requirements.txt`** — install separately: `pip install pytest`.
- The backend uses `scripts/run_local_api.py` for local dev (not bare `uvicorn`). It auto-loads `.env`, sets mock gateway mode, and disables Clerk auth enforcement. Alternatively use `python3 -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000`.
- Create `.env` from `.env.example` before first run. Default mock mode needs no API keys.
- Frontend lint is `npm run lint --prefix frontend` (`tsc --noEmit`).
- Full test suite: `python3 -m pytest tests/ -q`. Some HAM-on-X reactive inbox tests may have pre-existing failures unrelated to setup.
- **Hanging tests in Cloud VMs:** `tests/test_workspace_terminal.py` (3 tests) hangs indefinitely in cloud agent environments due to PTY requirements. Exclude with `--ignore=tests/test_workspace_terminal.py`. One pre-existing failure in `tests/test_model_capabilities.py::test_known_vision_model_enables_image_input` can be deselected.
- **PyJWT system conflict:** The base image has a system-installed `PyJWT 2.7.0` without RECORD metadata. Use `pip install --ignore-installed PyJWT>=2.8.0` before `pip install -r requirements.txt` if install fails.
- See `.cursor/skills/cloud-agent-starter/SKILL.md` for detailed per-area testing workflows and common quick fixes.

### HAM / Cursor Cloud Agent truth table

- **Cursor Cloud Agent** executes repo work (provider execution/runtime).
- **HAM** orchestrates missions — owns `ManagedMission` state, feed, audit, UI, follow-up/cancel controls.
- Browser never talks directly to Cursor: `Browser → HAM backend → Cursor SDK/API`.
- HAM remains the system of record; REST launch path remains primary.

### SDK bridge current truth

- SDK bridge is **live** (`HAM_CURSOR_SDK_BRIDGE_ENABLED=true`).
- It attaches to existing `bc-*` Cursor agents/runs via `src/integrations/cursor_sdk_bridge_client.py` + `bridge.mjs`.
- It streams provider-native events (`status`, `thinking`, `assistant_message`, `completed`) into HAM feed (backend bridge + SSE path to ingest; operators still poll `/feed` via HAM; no Cursor calls from the browser).
- Feed mode `sdk_stream_bridge`: native provider stream through backend bridge; frontend still talks only to HAM.
- Feed mode `rest_projection`: fallback REST refresh/projection (not provider-native streaming).
- Rollback: set `HAM_CURSOR_SDK_BRIDGE_ENABLED=false` — forces REST projection without changing launch path or frontend flow.

### Cloud Agent PR hygiene (prevent spam; Git lands branch + PR)

HAM appends deterministic guardrails to **Cursor Cloud Agent** launch prompts (`src/ham/cursor_agent_workflow.py`, `CURSOR_AGENT_BASE_REVISION=cursor-agent-v2`). See also **§ Cloud Agent / HAM VM Git policy** above for **`main`** vs **`branch → PR`** ( **`MAIN_PUSH_REQUIRES_OWNER_LOCAL_CONTEXT`** ).

From **HAM VM / Cursor Cloud**:

- **Code or doc edits you ship:** use **branch → push branch → `gh pr create`** into **`main`** (never **`git push origin main`** or **force-push `main`** from that environment).
- **Plan/report-only missions:** summarize without **`gh pr create`** unless the operator asked you to land commits.
- **Docs-only churn:** Prefer in-place edits to **canonical** paths: `README.md`, `AGENTS.md`, `VISION.md`, `docs/README.md`, `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`, `docs/MISSION_AWARE_FEED_CONTROLS.md`, `docs/HAM_HARDENING_REMEDIATION.md`, `GAPS.md`, `.cursor/skills/**/SKILL.md`. **`CURSOR_EXACT_SETUP_EXPORT.md`** is regenerated via `python scripts/build_cursor_export.py`.
- Avoid duplicating identical “Cloud Agent truth” bullets across unrelated files when one canonical paragraph suffices.
- **Before opening a docs-only PR:** run  
  `gh pr list --repo <org>/<repo> --state open --limit 50`  
  and scan titles/branches (`gh pr view <n> --json files` helps). If overlapping docs intent exists → report **`OVERLAPPING_DOCS_PR_FOUND`** and extend the existing PR/list it — do **not** open parallel duplicates from the same automation.
- **Code vs docs cleanup:** do not lump unrelated observability/UI fixes together with unrelated doc sweeps unless the operator asked — separate PR scopes reduce reviewer noise.

When opening a permitted PR:

- Prefer titles like `docs(agent): …`, `fix(missions): …`, `feat(missions): …`, `chore(agent): …`.
- Mention **mission_registry_id / agent id** when known; list files touched; say **docs-only vs code-bearing**; list tests/commands run — see also direct-main discipline in `.cursor/rules/ham-direct-main-workflow.mdc` where applicable.

## Local hooks (Phase A baseline)

Repo hardening landed in PR1 (`pyproject.toml`, `requirements-dev.txt`, `.pre-commit-config.yaml`, `.github/CODEOWNERS`, `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/*`, `.github/dependabot.yml`). To opt in locally:

```bash
pip install -r requirements-dev.txt
pre-commit install
# one-off audit pass
pre-commit run --all-files
```

What runs:

- **`ruff`** (lint) and **`ruff format --check`** — fast, single binary; config in `pyproject.toml [tool.ruff]`. Curated rule set: `E,F,I,N,B,UP,S,C901`. Tests/scripts get per-file ignores.
- **`mypy`** — warning-only baseline (`ignore_missing_imports = true`, no `disallow_untyped_defs` yet); not in pre-commit, but installed via `requirements-dev.txt` for local use. Will be ratcheted module-by-module in a follow-up PR.
- **`pre-commit-hooks`** standard hygiene: trailing whitespace, EOF newlines, YAML/JSON syntax, merge-conflict markers, large files (>1MB), private-key detector.
- **`gitleaks`** with **`--redact`** — secret-value scrubbed; pre-push stage only so commits stay fast. CI integration lands in Phase B.

What is **not** yet enforced:

- ESLint / Prettier on `frontend/` and `desktop/` (Phase A.2 follow-up).
- Coverage gate (`pytest --cov-fail-under=…`) (Phase B).
- Vitest scaffold + frontend test runner (Phase C).
- Vulture / deptry / knip / jscpd dead/duplicate-code checks (Phase C, warning-only).
- Branch protection / ruleset on `main` and GitHub native secret scanning (Phase B; requires repo settings change).

Do **not** wire `--fix`/`--write` autofixers into CI. Autofix is a local pre-commit concern; CI runs `--check` variants only. See the readiness lift plan in `~/.factory/specs/2026-05-03-ham-agent-readiness-lift-plan-foundations.md` for the full phased plan.

## CI guardrails (Phase B baseline)

Phase B added CI steps and a separate `secret-scan` workflow without raising the bar all at once. What runs today:

**Blocking** (failure blocks merge):

- `python` job → `python -m pytest tests/ -q --durations=20` (existing green path; `--durations=20` adds test-performance reporting at no measurable extra time).
- `python` job → `large-file-guard` step (fails if any **git-tracked** file is >1MB; current tree has zero tracked files >1MB).
- `frontend` job → `npm run lint` (existing `tsc --noEmit`).
- `gitleaks` job (in `.github/workflows/secret-scan.yml`) → scans PR diff or full tree on push, always with `--redact` so secret values never appear in logs.

**Warning-only** (`continue-on-error: true`, surfaces in the run UI but never blocks):

- `ruff check . --output-format=github` — the codebase has ~530 pre-existing lint findings; ratchet to blocking after a dedicated cleanup PR.
- `ruff format --check .` — ~280 files would reformat; ratchet after a separate `ruff format --write` PR.
- `mypy src --ignore-missing-imports` — baseline only; per-module strict overrides in a follow-up.
- `pytest --cov=src --cov-report=xml` — coverage report uploaded as artifact `coverage-xml`; **no** `--cov-fail-under` threshold yet.
- `python scripts/check_docs_freshness.py` — checks canonical docs were touched within 180 days and that markdown link targets resolve. Currently surfaces 2 pre-existing dangling references to be cleaned up separately.

**Not yet wired** (deferred per the lift plan):

- Branch protection / ruleset on `main` — see `docs/BRANCH_PROTECTION_SETUP.md`. Enable only after PR2 has at least one green run on `main`.
- ESLint / Prettier on `frontend/` and `desktop/` (Phase A.2).

## Frontend tests (Phase C.1 baseline)

Phase C.1 introduced Vitest as the frontend test runner. Pure-function tests
live under `frontend/src/**/__tests__/*.test.ts`. The runner is wired with
jsdom + `@testing-library/jest-dom` matchers so component smoke tests can
land in a follow-up without further setup.

Run locally from `frontend/`:

```bash
npm install            # one-time, picks up vitest + jsdom + @testing-library/*
npm test               # one-shot run (CI mode)
npm run test:watch     # interactive watch mode for local dev
```

What's covered today:

- `frontend/src/lib/ham/__tests__/voiceRecordingErrors.test.ts` — locks user-
  facing copy for MediaRecorder / getUserMedia error mapping.
- `frontend/src/lib/ham/__tests__/desktopDownloadsManifest.test.ts` — happy /
  sad paths for the manifest parser (trust boundary on fetched JSON).
- `frontend/src/features/hermes-workspace/screens/social/lib/__tests__/socialViewModel.test.ts`
  — pins product-truth helpers (mode/readiness/frequency/volume mapping).

CI status:

- `frontend` job → `npm test` runs **warning-only** for one cycle
  (`continue-on-error: true` in `.github/workflows/ci.yml`). Promote to
  blocking in a follow-up PR after one green run on `main`.

Out of scope for C.1 (deferred):

- Component / route smoke tests (need Clerk env mocking).
- Coverage threshold for the frontend.
- ESLint / Prettier on `frontend/`.

## Python dead-code + unused-deps (Phase C.2 baseline)

Phase C.2 wires two Python static-analysis tools into the existing `python`
CI job, both **warning-only** (`continue-on-error: true`). They surface
signal without blocking merges; ratchet to blocking later via a one-line
follow-up PR after a cleanup pass.

Run locally from the repo root (after `pip install -r requirements-dev.txt`):

```bash
vulture src              # dead-code (uses [tool.vulture] in pyproject.toml)
deptry .                 # unused / transitive deps (uses [tool.deptry])
```

What's covered today:

- **Vulture** — `min_confidence=80`, `paths=["src"]`, excludes `tests/`
  and `.venv/`. Surfaces unused imports, unused variables, dead branches.
  Current baseline: 7 findings (all 90–100% confidence) — eligible for a
  separate cleanup PR.
- **Deptry** — scans `requirements.txt` against actual imports. The
  `[tool.deptry.per_rule_ignores]` table holds explicit, commented entries
  for known false positives:
  - `DEP001` ignores `winpty` (Windows-only, ships via `pywinpty`).
  - `DEP002` ignores `python-multipart` (FastAPI `Form()` implicit),
    `google-cloud-storage` (dotted import), `pywinpty`, `cryptography`
    (pinned for TLS/JWT). Plus `package_module_name_map` quietens the
    package→module hint warnings.
  - Visible `DEP003` findings (`requests`, `starlette`) are intentional
    cleanup signal — treat them as TODO to promote to direct deps.

CI status:

- `python` job → `vulture src` and `deptry .` run **warning-only**
  (`continue-on-error: true` in `.github/workflows/ci.yml`). Promote to
  blocking only after the listed dead-code cleanup PR lands.

Out of scope for C.2 (deferred):

- Cleaning the 7 vulture findings (separate cleanup PR).
- Promoting `requests` / `starlette` from transitive to direct deps.
- Pre-commit integration of vulture / deptry (CI is sufficient for now).

## Frontend dead-code + duplicate-code (Phase C.3 baseline)

Phase C.3 wires two frontend static-analysis tools into the existing
`frontend` CI job, both **warning-only** (`continue-on-error: true`).
They surface signal without blocking merges; cleanup is a separate
follow-up PR.

Run locally from `frontend/` (after `npm install` picks up the new
devDeps):

```bash
npm run dup-check    # jscpd; reads frontend/.jscpd.json
npm run knip         # knip; reads frontend/knip.json
```

What's covered today:

- **jscpd** (`^4.0.5`) — token-based duplicate-code detector.
  `min-lines=8`, `min-tokens=70`, scans `src/**/*.{ts,tsx}`, ignores
  test files. Current baseline: **54 clones, 754 duplicated lines
  (2.57%)** — well under the 5% concerning threshold. Heaviest cluster
  in `frontend/src/components/settings/DesktopLocalControlStatusCard.tsx`
  and `frontend/src/features/hermes-workspace/adapters/conductorAdapter.ts`.
- **knip** (`^5.62.0`) — TS-aware unused files / exports / deps finder.
  Reads `frontend/knip.json` (entry=`index.html`, project=`src+scripts`,
  ignores `src/components/ui/**` shadcn primitives, ignoreDependencies
  for build-config-implicit deps `autoprefixer`, `tailwindcss`,
  `@testing-library/react`). Current baseline: 17 unused files, 8
  unused deps, 2 unused devDeps, 134 unused exports, 130 unused exported
  types, 1 duplicate export. **All cleanup is deferred** to separate
  follow-up PRs.

CI status:

- `frontend` job → `npm run dup-check` and `npm run knip` run
  **warning-only** (`continue-on-error: true` in
  `.github/workflows/ci.yml`). Knip is invoked with `--no-exit-code` as
  belt-and-suspenders so the binary itself never fails the step.

Out of scope for C.3 (deferred):

- Cleaning any flagged duplicate, file, export, or dependency.
- Promoting any check (Vitest, vulture, deptry, jscpd, knip) to blocking.
- Pre-commit integration of jscpd / knip (CI is sufficient for now).
- HTML / JSON report uploads (console output is enough for the baseline).
- Frontend ESLint / Prettier (Phase A.2 follow-up).

## Issue label taxonomy

GitHub issue labels are managed by `scripts/sync_github_labels.sh` —
an idempotent bash script that wraps `gh label create --force` for each
entry. Re-run any time the taxonomy changes; existing default GitHub
labels (`bug`, `enhancement`, `documentation`, etc.) are NOT touched and
coexist with the prefixed taxonomy below.

Five orthogonal dimensions plus one operational tag:

- **`priority:P0`/P1/P2/P3** — actionability ladder (drop-everything →
  backlog).
- **`severity:critical`/high/medium/low** — impact ladder (orthogonal to
  priority; e.g. a `severity:high` regression can still be `priority:P2`
  if a workaround exists).
- **`status:needs-triage`/blocked** — workflow state.
- **`area:frontend`/backend/desktop/ci/docs** — codebase surface (matches
  the labels used in `.github/dependabot.yml`).
- **`type:bug`/feature/agent-run** — issue category. `type:agent-run`
  is for capturing notable Cursor / Hermes / droid_executor runs via
  `.github/ISSUE_TEMPLATE/agent_run.yml`.
- **`dependencies`** — Dependabot / Renovate update PRs.

To sync the live labels on the GitHub repo with the script after editing:

```bash
# locally (requires gh authenticated with `repo` scope)
./scripts/sync_github_labels.sh

# or trigger the manual workflow from the Actions tab:
gh workflow run sync-labels.yml
```

The workflow at `.github/workflows/sync-labels.yml` also auto-runs on
pushes to `main` that touch `scripts/sync_github_labels.sh` itself, so
edits to the taxonomy land on the repo without a separate manual step.

Out of scope (deferred):

- Migrating existing issues from old unprefixed labels (`bug`,
  `needs-triage`, `feature`, `agent`) to the new `type:` / `status:`
  prefixes — there are 0 open issues at the time of this taxonomy.
- Deleting GitHub's default labels — kept for compatibility with external
  tools that expect them.
- Wiring labels into branch protection or required-status checks.
```

---

## `VISION.md`

```
# Ham — Vision & Architecture

## What Ham Is

Ham is an open-source, multi-agent autonomous developer swarm that executes
the full Software Development Life Cycle (SDLC). It is not a chatbot wrapper.
It is an opinionated assembly line: plan, build, review, learn, repeat.

**Orchestration contract:** supervisory orchestration is **Hermes-led only**.
There is **no CrewAI** (or any other third-party orchestration framework) in
the architecture. `src/swarm_agency.py` assembles per-role context for
Hermes-supervised reasoning surfaces; it does not constitute a parallel
orchestrator.

## Builder platform product north star (aspirational)

Long-term **Builder Platform** vision (last-mile app building, enterprise orchestration, phased roadmap) lives in **[`docs/BUILDER_PLATFORM_NORTH_STAR.md`](docs/BUILDER_PLATFORM_NORTH_STAR.md)**. That document is **not** shipped pillar architecture; Hermes/Droid/context roles and the implementation table below remain authoritative here.

## The Four Core Pillars

### 1. Supervisory Core — Hermes

Hermes is the supervisory control plane for the swarm. It coordinates droids,
routes jobs, critiques outputs, and accumulates learning signals over time.
Hermes owns orchestration and quality policy at the system level.

Hermes may self-handle only tiny, bounded, critic-native tasks (for example:
small review normalization or bounded policy checks). Hermes is not the
primary execution engine.

### 2. Execution Engine — Factory Droid CLI

Factory Droid CLI is the execution-heavy implementation engine. Droid performs
code and shell work (scaffolding, edits, tests, refactors, command execution)
and may self-orchestrate locally while executing delegated work.

Droid is not a dumb worker: it can perform bounded local planning and
sequencing inside an assigned execution job. Ambiguous execution work defaults
to Droid.

### 3. Context Engine — memory_heist.py

Repository-grounded context assembly for the swarm: this module gives every
agent a factual view of the local workspace:

- **Workspace scanning**: filesystem tree, file inventory, ignore rules.
- **Instruction file discovery**: hierarchical SWARM.md / AGENTS.md loading
  from project root up through ancestors.
- **Config discovery**: `.ham.json` / `.ham/settings.json` merge chain.
- **Git state capture**: status, diff, recent log — injected into prompts so
  agents know what changed and what's staged.
- **Session compaction**: conversation history summarization and persistence
  so agents can survive context window limits across long tasks (including
  tool-output pruning and config-driven compaction thresholds).
- **Instruction hygiene**: scanning of discovered instruction files for
  obvious injection patterns and invisible unicode before injection into
  rendered context.

The Context Engine does NOT make decisions. It assembles ground truth and
injects it into agent prompts so they don't hallucinate about repo state.

### 4. LLM Routing — LiteLLM / OpenRouter

LiteLLM and OpenRouter provide model/provider abstraction and routing. Model
selection stays config-driven and decoupled from orchestration and execution
roles.

## Responsibilities Matrix

| Component | Owns | Must Not Own |
|-----------|------|--------------|
| **Hermes (Supervisory Core)** | Job routing, supervisory orchestration, critique policy, learning policy, escalation/handoff decisions | Broad execution loops, heavy code/test/build operations, replacing Droid as execution engine |
| **Droid (Execution Engine)** | Implementation-heavy execution, shell/code operations, bounded local self-orchestration while executing delegated jobs | Global supervisory policy, long-horizon learning governance, replacing Hermes as control plane |
| **memory_heist (Context Engine)** | Repo truth, context discovery/plumbing, instruction/config/git/session context assembly | Execution orchestration policy, critique decision-making, execution ownership |
| **LiteLLM/OpenRouter (Model Routing)** | Provider abstraction, model access, configurable routing | Orchestration policy, execution ownership, critique ownership |

**Default routing rule:** if work may mutate code, invoke tools, or requires
non-trivial execution judgment, route it to Droid.

## Anti-Drift Guardrails (Separation of Duties)

1. **Hermes is not a monolith.** Hermes coordinates, critiques, and learns; it
   does not absorb all runtime behavior.
2. **Hermes is not a second execution engine.** Hermes may run only tiny,
   bounded, critic-native tasks directly.
3. **Orchestration refactors must not absorb execution.** Shifting control flow
   or framework choice must not move execution-heavy behavior into Hermes by
   default.
4. **Droid is not reduced to a dumb worker.** Droid retains bounded local
   self-orchestration authority during execution.
5. **Ambiguous execution defaults to Droid.** If ownership is unclear and task
   impact is execution-heavy, route to Droid first.
6. **No verdict-based role collapse.** Critique outcomes must not be used to
   justify shifting execution ownership away from Droid.

## How They Connect

```
User Prompt
    │
    ▼
┌─────────────────────────────────────────────┐
│  Hermes Supervisory Core                    │
│                                             │
│  ┌───────────────────────────────────────┐  │
│  │ route jobs / supervise / critique     │  │
│  └───────────────────────┬───────────────┘  │
│                          │                  │
│                          ▼                  │
│                 ┌──────────────────┐        │
│                 │ Droid CLI        │        │
│                 │ execute + local  │        │
│                 │ self-orchestration│       │
│                 └──────────────────┘        │
│                          │                  │
│                          ▼                  │
│                 ┌──────────────────┐        │
│                 │ Critique + learn │        │
│                 │ (Hermes)         │        │
│                 └──────────────────┘        │
│                                             │
│  ┌──────────────────────────────────────┐   │
│  │ memory_heist.py — Context Engine     │   │
│  │ (repo scan, git state, instructions, │   │
│  │  config, session memory)             │   │
│  └──────────────────────────────────────┘   │
│                                             │
│  ┌──────────────────────────────────────┐   │
│  │ LiteLLM / OpenRouter — LLM Routing   │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

## Architecture Target (North Star)

| Pillar | Target Owner | Target Role |
|--------|--------------|-------------|
| Supervisory Core | `src/hermes_feedback.py` (and Hermes supervisory wiring) | Supervisory orchestration + critique + learning |
| Execution Engine | `src/tools/droid_executor.py` | Execution-heavy implementation with bounded local self-orchestration |
| Context Engine | `src/memory_heist.py` | Repo truth and context plumbing |
| LLM Routing | `src/llm_client.py` | Model/provider abstraction and routing |

## Current Implementation State (Transitional)

| Area | Primary Module(s) | Current Status |
|------|--------------------|----------------|
| Supervisory orchestration | `src/hermes_feedback.py`, `main.py`, `src/swarm_agency.py` (context only) | **Hermes-led:** primary path uses profile selection, Bridge execution, and Hermes (`HermesReviewer`) review; `swarm_agency.py` provides shared `ProjectContext` render budgets for Architect / routing / critic prompts—**not** a separate orchestration engine |
| Execution engine | `src/tools/droid_executor.py` | Bridge v0 bounded backend implemented (`shell=False`, timeout, deterministic capture, capped output) |
| Bridge runtime/policy | `src/bridge/contracts.py`, `src/bridge/policy.py`, `src/bridge/runtime.py`, `src/registry/profiles.py`, `src/registry/backends.py`, `src/registry/droids.py` | Bridge v0 hardened: fail-closed policy gate with command-profile checks, env override restrictions, total-output cap enforcement, deterministic status mapping, mutation-aware refresh gating, and registry-backed profile selection seam with backend-registry executor resolution, plus structured run persistence to `.ham/runs/`; droid registry records for UI/API |
| Read API + run store | `src/api/server.py`, `src/persistence/run_store.py` | Thin FastAPI layer over `RunStore` (`.ham/runs/`): status, runs list/detail, profiles, droids; read-only Context Engine snapshot (`/api/context-engine`, `/api/projects/{id}/context-engine`) for dashboard wiring; **Hermes runtime skills** catalog + host probe + **Phase 2a** shared-target install preview/apply (`/api/hermes-skills/*`, `src/ham/hermes_skills_install.py`, local/co-located only); **v1 allowlisted settings** preview/apply/rollback (`src/ham/settings_write.py`, `src/api/project_settings.py`) writes only `{root}/.ham/settings.json` with backup + audit under `.ham/_backups/settings` and `.ham/_audit/settings` (`HAM_SETTINGS_WRITE_TOKEN` for mutating routes) |
| Capability library (My library) | `src/ham/capability_library/`, `src/api/capability_library.py` | **Phase 1:** per-project **saved** Hermes + capability-directory **refs** in `.ham/capability-library/v1/index.json` (separate from settings); `GET` library + aggregate; **mutations** save/remove/reorder with `HAM_CAPABILITY_LIBRARY_WRITE_TOKEN` and audit under `.ham/_audit/capability-library/`; **no** auto-install, **no** shell; dashboard **Capabilities** page **My library** tab + **Skills** “Save to My Library” (requires `?project_id=`) — installed/active truth remains Hermes/inventory, not the library file |
| Hermes gateway broker (dashboard) | `src/ham/hermes_gateway/`, `src/api/hermes_gateway.py`, `docs/HERMES_GATEWAY_BROKER.md` | **Path B:** `GET /api/hermes-gateway/snapshot` (+ capabilities, optional SSE stream) aggregates hub, allowlisted CLI inventory, skills overlay, Hermes HTTP `/health` probe, run-store + control-plane summaries, external-runner cards; snapshot includes **operator_connection** (derived CLI + HTTP + chat `gateway_mode` + freshness guidance; no new `hermes` argv); **Path C** placeholders for JSON-RPC/WebSocket/live-menu REST until upstream exists; raw CLI captures redacted; UI: `/command-center` + desktop **Settings → HAM + Hermes setup** strip; team operator story: `docs/TEAM_HERMES_STATUS.md` |
| Workspace UI | `frontend/` (Vite + React), `desktop/` (Electron shell) | Extracted workspace; TypeScript types aligned with persisted run / bridge shapes; optional **Clerk** for chat JWT; **execution mode** routing + Bridge browser adapters (`src/ham/execution_mode.py`, `src/bridge/browser_*.py`). **Desktop** (`desktop/README.md`): **Windows** installers via `npm run pack:win*`; **Linux `.deb`/AppImage packaging targets were removed** (dev: `npm start`). `window.hamDesktop.localControl` exposes Local Control policy/audit/kill-switch, sidecar lifecycle, and **main-process** managed-browser IPC (MVP/real CDP) where enabled — separate from Ham API **`/api/browser*`.** **Workspace chat** does not run the removed **GoHAM-mode** managed-browser/chat loop (`POST /api/goham/planner` stays API-only). See `docs/desktop/local_control_v1.md`; `docs/goham/browser_smoke.md` for historical/future notes. |
| Chat operator + identity gate | `src/api/chat.py`, `src/ham/chat_operator.py`, `src/ham/clerk_auth.py`, `src/ham/clerk_policy.py`, `src/ham/clerk_email_access.py`, `src/ham/operator_audit.py` | Server-side operator before LLM; optional Clerk JWT (`HAM_CLERK_REQUIRE_AUTH` or `HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS`, `CLERK_JWT_ISSUER`), `ham:*` permission checks, optional HAM allowlist email/domain defense-in-depth; append-only audit in HAM JSONL — **not** Clerk metadata; Cursor API key unchanged |
| HAM-on-X social agent | `src/ham/ham_x/`, `docs/ham-x-agent/`, `src/api/social.py`, `src/ham/social_persona/`, `frontend/src/features/hermes-workspace/screens/social/` | **Phase 4C Reactive Batch Mode + Social TD-1/SP-3/TD-3A:** Phase 2B remains execution-disconnected, Phase 3A `goham_controller.py` remains dry-run-only, and Phase 3B `goham_live_controller.py` remains original-post-only. Phase 4A `goham_reactive.py` still classifies prepared/read-only inbound mentions/comments into dry-run review/exception records. Phase 4B `reactive_reply_executor.py` / `goham_reactive_live.py` remain a separate one-shot reply canary. Phase 4B.1 `goham_reactive_inbox.py` discovers mentions/comments and returns automatic reply targets without executing. Phase 4C adds opt-in, dry-run-first `goham_reactive_batch.py` for bounded multi-candidate processing with per-item policy/governor rechecks, existing reactive rolling caps/cooldowns, per-reply journal rows, provider failure stops, and no retries. Social TD-1 adds read-only Telegram/Discord readiness, capabilities, and setup checklist endpoints backed by safe Hermes gateway env/status-file signals, plus read-only workspace panels. Social SP-1/SP-3 adds the read-only `ham-canonical` persona registry, deterministic digest, bounded persona API, docs, Persona panel, and persona id/version/digest protection in X preview/apply digests. Social TD-2A strengthens Telegram readiness with safe token/allowlist/home/test-group/mode presence booleans plus bounded Hermes gateway runtime/platform-state validation. Social TD-2B adds `POST /api/social/providers/telegram/messages/preview` for deterministic, persona-protected, masked-target Telegram dry-run message previews with proposal digests. Social TD-3A adds a narrow HAM-owned Telegram Bot API one-shot sender (`src/ham/social_telegram_send.py`), redacted delivery log (`src/ham/social_delivery_log.py`), and confirmed `POST /api/social/providers/telegram/messages/apply` gated by operator token, exact confirmation, recomputed preview digest, persona digest, server-side target resolution, and connected Hermes/Telegram readiness; no Telegram batch/reactive route, arbitrary target/text, broad Hermes `send_message` tool, gateway process controls, credential inputs, raw IDs, Hermes/Eliza export, or persona editing. Reactive budgets remain separate from broadcast caps; no scheduler, daemon, infinite loop, original posts, quotes, DMs, likes/follows, xurl mutation, manual canary, broadcast executor, or Phase 2B execution |
| Control plane runs (v1) | `src/persistence/control_plane_run.py`, `src/ham/cursor_agent_workflow.py`, `src/ham/droid_workflows/preview_launch.py`, `src/api/control_plane_runs.py` | **Durable** JSON per `ham_run_id` under `HAM_CONTROL_PLANE_RUNS_DIR` (default `~/.ham/control_plane_runs`): committed Cursor Cloud Agent + Factory Droid launches and Cursor status updates; **read** list/detail API (`/api/control-plane-runs*`) is factual only; **not** a mission graph, queue, or bridge `RunStore` |
| Managed Cloud Agent + mission record | `src/persistence/managed_mission.py`, `src/ham/managed_mission_wiring.py`, `src/ham/managed_mission_truth.py`, `src/api/cursor_settings.py`, `src/api/cursor_managed_*.py`, `src/ham/cursor_agent_workflow.py`, `src/ham/chat_operator.py`, Hermes Workspace (`WorkspaceManagedMissionsLivePanel`), `src/integrations/cursor_sdk_bridge_client.py` | Durable per-agent mission JSON + API read (observed lifecycle, deploy/Vercel last-seen); optional `project_id` on HAM launch for create-time `mission_deploy_approval_mode` snapshot; **Chat operator** can preview/launch Cursor Cloud Agent with `cursor_mission_handling: managed` — same managed prompt for digest/launch, `ManagedMission` row on successful API launch; mission **feed** projection: `HAM_CURSOR_SDK_BRIDGE_ENABLED=true` uses the live Cursor SDK bridge (`bridge.mjs`); unset/false falls back to REST projection (same route, honest `provider_projection.mode`); **Roadmap phases A–D (v1 slices):** `GET .../truth` observability table; `GET .../correlation` + optional embedded `ControlPlaneRun`; token-gated `POST .../hermes-advisory` (`HAM_MANAGED_MISSION_WRITE_TOKEN`) for capped `HermesReviewer` advisory fields only; token-gated `PATCH .../board` for operator `mission_board_state` lanes (`backlog`/`active`/`archive`, not a graph) with automatic active→archive on terminal lifecycle; Workspace detail surfaces truth + correlation + token field; **not** a mission queue or Hermes-to-Cursor action loop — see `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`, `docs/examples/managed_cloud_agent_phases/README.md` |
| Context engine | `src/memory_heist.py` | Hardened + tested (Phase 1/3 guardrails complete) |
| LLM routing | `src/llm_client.py` | Working |
| Critique MVP | `src/hermes_feedback.py` | Implemented (`HermesReviewer.evaluate()`), conservative fallback, tested |

**Interpretation rule:** "Target" defines architecture direction; "Current"
reports implementation reality. Do not treat transitional scaffolding as
architecture contract.

### Registries

The shipped registry surface includes `IntentProfile`, `ProfileRegistry`, `Selector`, `KeywordSelector`, and `DEFAULT_PROFILE_REGISTRY` in `src/registry/profiles.py`, plus `DroidRecord`, `DroidRegistry`, and `DEFAULT_DROID_REGISTRY` in `src/registry/droids.py` (builder and reviewer droids; pure-data records per registry conventions). `IntentProfile` records are pure data with `id`, `version`, `argv`, and `metadata` fields. The selection seam is a `Protocol` with one method (`select(prompt) -> str`) and currently has one default implementation (`KeywordSelector`).

The shipped backend registry surface is `ExecutionBackend`, `LocalDroidBackend`, `BackendRecord`, `BackendRegistry`, `DEFAULT_BACKEND_ID`, and `DEFAULT_BACKEND_REGISTRY` in `src/registry/backends.py`. `BackendRecord` follows the same pure-data Pydantic convention as `IntentProfile` (`id`, `version`, `metadata`, no methods). Runtime backend resolution currently uses hardcoded `DEFAULT_BACKEND_ID` against a single registered backend; per-intent backend selection is deferred.

Completed runs are now persisted as structured JSON at `.ham/runs/<timestamp>-<run_id>.json`. Persisted records include `run_id`, `created_at`, `profile_id`, `profile_version`, `backend_id`, `backend_version`, `prompt_summary`, `bridge_result`, and `hermes_review`. `run_id` is canonical from `bridge_result.run_id` (never regenerated); the timestamp in the filename is metadata for sort/collision only. The stdout `RUNTIME_RESULT` envelope shape remains unchanged, and persistence is additive. `BackendRegistry.get_record()` is now the first public backend-record accessor.

**Tests**: full `pytest` suite including registry, bridge, main loop, droid registry, API/CORS, control-plane catalog (skills + subagents + Hermes runtime skills Phase 1/2a) + UI action parsing, chat streaming + SQLite session store, project settings preview/apply/rollback (including **HAM agent profiles** / `agents` in `.ham/settings.json`), and persistence tests — run `pytest` for current counts (`pytest.ini` sets `pythonpath = .`; GitHub Actions runs `pytest` + frontend `tsc`).

**Next milestone**: stronger **UI-actions** marker recovery; continue Bridge-profile hardening. **Capability library** Phase 1 is shipped (saved `hermes:` / `capdir:` refs, token + audit, **Capabilities → My library** + **Skills** save — no install). Optional follow-on: **Phase 2** wire save UI to **Hermes skills** install (delegate to existing preview/apply). **Hermes gateway broker** Path B is shipped (`/command-center`, broker docs); optional follow-on: consume official Hermes **run** SSE from HAM-orchestrated runs only, and widen HTTP probes when `/health/detailed` is verified on target Hermes builds. **HAM agent builder** Slices 1–2 (persisted profiles) and **Slice 3** (compact **active agent guidance** injected into `/api/chat` / stream when `project_id` is sent — catalog descriptors only, no install/execution) are shipped. Expand allowlisted settings keys only with explicit review. (Context & Memory **settings preview/apply** UI is shipped; **`GET /api/cursor-subagents`** + chat prompt injection for review charters is shipped; **Hermes runtime skills** Phase 2a shared local install is shipped — profile-target install and broader topologies deferred.)

**Deferred:** FTS5 durable learning persistence, second orchestration harness,
architecture sprawl.

## Design Principles

1. **Agents don't freestyle** — every agent gets grounded context from
   memory_heist before it touches anything. No hallucinating about repo state.
2. **Separation of duties is enforced** — Hermes supervises and critiques;
   Droid executes and may self-orchestrate locally during execution.
3. **Learning compounds** — Hermes collects and applies learning signals over
   time; durable FTS5 persistence is a planned follow-up.
4. **Models are disposable** — swap providers, swap models, swap pricing.
   The architecture doesn't care which LLM is behind the API.
5. **Local-first** — no cloud dependencies for context, memory, or learning.
   Everything runs against the local filesystem and local DBs.
```

---

## `GAPS.md`

```
# Ham — Gap Tracker

Gaps between the current codebase and the VISION.md architecture target.
Each item tracks what is missing, why it matters, and what blocks it.

**Cloud Agent + managed missions (what works vs stub + phased roadmap):** see [`docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`](docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md).

**Builder Platform (aspirational vs shipped):** long-term last-mile builder / enterprise orchestrator vision and phased anchors (Builder Blueprint Mode → lifecycle governance) live in [`docs/BUILDER_PLATFORM_NORTH_STAR.md`](docs/BUILDER_PLATFORM_NORTH_STAR.md). [`VISION.md`](VISION.md) remains the shipped pillar SSOT.

## Active implementation notes (Cursor / hardening)

- Context Engine hardening and **Phase 1** (Hermes-aligned scanning, tool-output pruning, config-driven compaction thresholds) are **complete** in `src/memory_heist.py`; **Phase 3** guardrail tests are in `tests/test_memory_heist.py` (23 cases).
- **Phase 2** Critic MVP is **complete** in `src/hermes_feedback.py` (LLM-backed `HermesReviewer.evaluate()`, stable schema, conservative fallback); **Phase 3** tests in `tests/test_hermes_feedback.py` (7 cases). **`python -m pytest tests/test_memory_heist.py tests/test_hermes_feedback.py` — 30 passed** (verify locally after edits).
- Keep `_extract_prior_summary` marker parsing coupled with `_format_continuation` wording on future edits (see `docs/HAM_HARDENING_REMEDIATION.md`).
- **`VISION.md` must stay in sync** with real module status after each milestone (see `.cursor/rules/vision-sync.mdc`).
- **Avoid** multiple `ProjectContext.discover()` passes for one run; prefer one shared snapshot and role-appropriate render budgets.
- **Prefer config-driven** context budgets (`.ham.json` / merged config) over long-term hardcoded magic numbers.
- **Deferred (unchanged direction):** no second orchestration harness, no FTS5 durable learning persistence yet, no Phase 4 Droid execution-safety work until broader mutating-command policy is approved (bounded subprocess executor exists today).
- **Dashboard chat (Phase A+):** `POST /api/chat` and **`POST /api/chat/stream`** (NDJSON deltas) are **shipped** with HAM-native DTOs and `src/integrations/nous_gateway_client.py` (**mock**, **openrouter**, or **http**; streaming uses upstream `stream: true` where supported). **`GET /api/cursor-subagents`** indexes `.cursor/rules/subagent-*.mdc` (review charters); chat can inject them via **`include_operator_subagents`** (default true). Session store defaults to **memory**; opt-in **`HAM_CHAT_SESSION_STORE=sqlite`** (`src/persistence/sqlite_chat_session_store.py`). Mission/walking APIs are **not** started here.
- **Dashboard settings (Phase C v1):** `POST /api/projects/{id}/settings/preview|apply|rollback` and `GET /api/settings/write-status` are **shipped** (`src/ham/settings_write.py`, `src/api/project_settings.py`). **Context & Memory** settings tab includes **Preview / Apply** for the allowlisted keys (`UnifiedSettings.tsx`): resolves or auto-registers an API project for the context-engine `cwd`, preview without auth, apply with **session-only pasted** `HAM_SETTINGS_WRITE_TOKEN` (not baked into the frontend build).
- **Hermes runtime skills (Phase 1 + 2a shared install):** Read-only catalog **`GET /api/hermes-skills/catalog`**, **`.../catalog/{id}`**, **`.../capabilities`**, **`.../targets`**; **Phase 2a** **`POST /api/hermes-skills/install/preview`** and **`.../install/apply`** (shared target only, local/co-located API, curated catalog, `HAM_SKILLS_WRITE_TOKEN`, bundle + `skills.external_dirs` — see `src/ham/hermes_skills_install.py`). **`/skills`** UI (`src/api/hermes_skills.py`). Catalog JSON: **`scripts/build_hermes_skills_catalog.py`**. **Deferred:** profile-target install, uninstall, rollback endpoint, Hermes CLI install path, arbitrary sources — see `docs/HAM_CHAT_CONTROL_PLANE.md`.

## Active Gaps

### 1. Hermes supervisory wiring into execution flow

**Status**: In progress (Hermes-led orchestration is the contract; runtime wiring deepens over time)
**Impact**: Docs and rules now state **Hermes as the sole supervisory orchestrator** (no CrewAI). Remaining work is richer routing/policy in code paths—not adopting another orchestration framework.
**Blocked by**: Incremental runtime hardening and tests for supervisory routing semantics.
**Fix**: Extend explicit Hermes-owned routing that delegates execution-heavy work to Droid by default, preserves separation-of-duties, and keeps Hermes direct execution limited to tiny bounded critic-native tasks.

### 2. Context refresh after Droid mutations

**Status**: Not started
**Impact**: After Droid modifies the repo (creates/deletes files), any previously
captured `ProjectContext` snapshot is stale. Agents making decisions after Droid
runs may reference files that no longer exist or miss newly created ones.
**Blocked by**: No automatic `ProjectContext` refresh after bridge/Droid subprocess steps yet (executor exists; wiring is follow-up).
**Fix**: Add a `ProjectContext.refresh()` method or rebuild `ContextBuilder` after
each Droid execution step once integrated with the execution loop.

### 3. Role-specific context shaping (follow-up refinement)

**Status**: Baseline implemented; further refinement optional
**Impact**: Context consumers have different needs. Supervisory Hermes and
execution paths should not consume identical prompt payloads by default.
**Follow-up**: Current wiring already uses per-agent render budgets on a shared
`ProjectContext` snapshot. Additional shaping (role-specific section filtering,
different tree/config emphasis) is a next-phase quality improvement.

### 4. LLM-backed session summarization

**Status**: Not started
**Impact**: `SessionMemory._summarize()` is string formatting, not real
summarization. Compacted summaries are verbose timelines that waste tokens.
Repeated compaction causes unbounded nesting growth.
**Blocked by**: Need to decide which model to use for summarization (cheap/fast
via LiteLLM) and whether summarization happens inline or async.
**Fix**: Call `llm_client.get_llm_client()` from `_summarize()` with a short
system prompt. Add `MAX_SUMMARY_CHARS` hard cap as a safety net.

### 5. Critic learning persistence (FTS5 / external Hermes client)

**Status**: Deferred (not started)
**Impact**: `HermesReviewer.evaluate()` is a **minimal LLM-backed critic MVP**
(via `src/llm_client.py`); there is still no FTS5 persistence, no external
hermes-agent-only client, and no durable “institutional memory” from reviews.
**Blocked by**: Product choice and follow-up milestone after Hermes supervisory
wiring + real Droid execution path are farther along.
**Fix (later):** Add FTS5-backed persistence under `.hermes/` (with `.hermes/`
already in `IGNORE_DIRS`), or integrate a dedicated hermes-agent API if required;
wire reviewer into the supervisory execution flow explicitly if not already.

### 6. Real Droid CLI integration

**Status**: **Executor implemented** — `src/tools/droid_executor.py` uses bounded `subprocess.run()` with timeout, capture, and stdout/stderr caps (see module). Meaningful **Factory/Droid** runs still depend on **profile argv** pointing at an installed CLI and policy allowing the command.
**Impact**: Bridge can invoke real subprocesses; supervision and safety reviews still assume bounded inspect-style defaults in `main.py` until missions expand.
**Blocked by**: Operator setup (binary on PATH, auth on disk per tool) and execution-safety policy hardening for mutating commands.
**Fix (follow-up):** Execution-safety milestones (Phase 4 in remediation docs), refresh-after-mutation context, and richer mission orchestration—without collapsing Hermes/Droid roles.

### 7. Test coverage (follow-up after Droid / supervisory wiring)

**Status**: Phase 3 guardrail suite **complete** for current Context Engine + critic MVP
**Impact**: `tests/test_memory_heist.py` and `tests/test_hermes_feedback.py`
cover hardening, Phase 1–2 behavior, and follow-up guardrails (tail preservation,
config precedence, repeated compaction bounds, reviewer schema/fallback). Further
expansion waits on supervisory integration tests and refresh-after-mutation wiring.
**Next (post wiring):** refresh-after-tool semantics, subprocess/output caps in integration tests, optional end-to-end supervisory smoke without orchestration redesign.

### 8. Productization direction (deferred / exploratory)

**Status**: Deferred (exploratory)

SaaS/control-plane expansion concepts (including gamification and marketplace
surfaces) are tracked as exploratory direction, not committed architecture.
Current architecture contracts remain Hermes/Bridge/Droid with bounded
execution and review seams.

Phases 0 and 1 shipped as enabling foundations: selector correctness hardening
and intent profile registry promotion (`IntentProfile` / `ProfileRegistry` /
`Selector` / `KeywordSelector`). No additional productization implementation is
approved in the codebase at this time.
Phase 3 also shipped as an enabling foundation: a minimal backend abstraction
seam (`ExecutionBackend` / `LocalDroidBackend` / `BackendRegistry`) now used by
bridge runtime executor resolution.
Phase 5 also shipped as an enabling foundation: completed runs now persist to
`.ham/runs/` as structured JSON with canonical bridge-derived `run_id`.

No rules or skills should be added for this direction until the relevant code
surface is implemented and has survived at least one follow-up use with stable
interfaces.

## Completed Items

- Rebrand memory_heist.py (Claude -> Ham naming): **Done** (Part 1)
- Add `.sessions` and `.hermes` to IGNORE_DIRS: **Done** (Part 1)
- Complete memory_heist hardening milestone: **Done** (caps, marker coupling,
  render-time budgets, single-discover wiring, baseline regression tests)
- **Phase 1** (Hermes-aligned Context Engine): instruction/context scanning,
  tool-output pruning before compaction, config-driven session compaction thresholds
  (`memory_heist` section + top-level keys), targeted tests — **Done**
- **Phase 2** Critic MVP: `HermesReviewer.evaluate()` LLM-backed path, stable
  `ok` / `notes` / `code` / `context` schema, conservative fallback, dict + string
  `ok` normalization — **Done**
- **Phase 3** guardrail/follow-up tests: expanded `test_memory_heist.py` and
  strengthened `test_hermes_feedback.py` coverage — **Done**
```

---

## `docs/HAM_HARDENING_REMEDIATION.md`

```
# Ham — Context Engine hardening audit & remediation

Canonical reference for the **memory_heist** hardening plan, audit findings, and safe execution order. Align with `VISION.md` and `.cursor/skills/context-engine-hardening/SKILL.md`.

## Next milestone (VISION.md)

The original Context Engine hardening goals (rebrand, ignore rules, wire
`memory_heist` into `swarm_agency.py`, caps, marker coupling) are **complete**
in code and tests. Subsequent **Phase 1–3** work added Hermes-aligned
instruction scanning, tool-output pruning before compaction, config-driven
session compaction thresholds, critic MVP tests, and guardrail coverage —
see `GAPS.md` and `VISION.md` for current status. This document remains a
**maintenance reference** for continuation/parser coupling and safe edit order.

## Audit summary (accurate)

The hardening plan correctly targets: cross-platform `_extract_key_files`, agent-oriented `_format_continuation`, public `has_summary`, capped `git_diff`, configurable instruction/diff budgets on `ContextBuilder`, capped `_summarize` / `_merge_summaries`, and wiring into `swarm_agency.py`.

## Critical coupling (maintain on future edits)

`_extract_prior_summary()` uses `end_markers` that must match `_format_continuation()` closing text. Changing continuation phrasing **without** updating markers breaks summary extraction and can cause unbounded summary growth.

**Status**: Addressed in the completed hardening milestone (legacy + new markers supported).
**Maintenance rule**: Update `end_markers` in `_extract_prior_summary` whenever `_format_continuation` changes; keep **legacy** markers for old session JSON until migrated.

## Other guidance

- **VISION.md**: Update the "Current State" table and "Next milestone" after each milestone that changes repo reality (see `.cursor/rules/vision-sync.mdc`).
- **Single discover**: Avoid multiple `ContextBuilder()` / `ProjectContext.discover()` calls per run assembly; share one snapshot and vary render budgets only (see Agent Context Wiring skill).
- **Config-driven budgets**: Prefer `.ham.json` / merged config for per-agent caps; avoid permanent magic numbers only in `swarm_agency.py`.
- **Tests**: `tests/test_memory_heist.py` — 23 cases (hardening + Phase 1 + Phase 3 guardrails). `tests/test_hermes_feedback.py` — 7 cases (Phase 2 critic MVP + Phase 3). Together **30 passed** with `python -m pytest tests/test_memory_heist.py tests/test_hermes_feedback.py` (re-run after changes to confirm).

## Remediation order executed (record)

1. Quick wins completed: `_extract_key_files`, `_format_continuation` + **synced `_extract_prior_summary` markers**, `has_summary` / `with_memory`.
2. Safety caps completed: `MAX_DIFF_CHARS` + `git_diff`, budget params threaded through `ContextBuilder` / `render`, `MAX_SUMMARY_CHARS` + timeline cap + `_merge_summaries` cap.
3. Wiring completed: `swarm_agency.py` uses **one** `ProjectContext.discover` with per-agent `render` budgets.
4. Verification/docs completed: regression tests added and passing; `VISION.md` status updated.

## Deferred (not in this milestone)

- LLM-backed session summarization (`SessionMemory._summarize()` remains string-based).
- Context refresh immediately after Droid writes (not wired yet; bounded subprocess executor exists).
- Supervisory-flow callbacks/hooks for `SessionMemory` (separate integration task).
- Critic **learning** persistence (FTS5 / durable review store) — not started; no second harness layer.
- Phase 4 Droid execution-safety hardening — deferred until broader mutating-command policy is approved (`droid_executor` already enforces timeout and output caps).
```

---

