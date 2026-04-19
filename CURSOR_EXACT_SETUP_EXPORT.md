# Cursor setup — exact export

Generated snapshot of `.cursor/` rules and skills, plus first-class context documents from the handoff source-of-truth list.

## File counts (this document)

| Category | Count |
|----------|-------|
| Rules (`.mdc`) | 13 |
| Skills (`SKILL.md`) | 6 |
| First-class context | 4 |
| **Total embedded files** | **23** |

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
2. This file — where implementation lives
3. `SWARM.md` — repo coding instructions (loaded by `memory_heist`)
4. `PRODUCT_DIRECTION.md` — product lens: HAM-native model vs reference ecosystems

## Ham bet: memory, Hermes, and CLI-native muscle

Three ideas stay stable while execution backends evolve:

1. **Repo-grounded context (`memory_heist`)** — Workspace truth (scan, git, merged `.ham` config, instruction files, session compaction) is assembled once and injected into agents so supervision and planning do not hallucinate project state.

2. **Hermes learning loop (`hermes_feedback`)** — Critique and structured review over **evidence-shaped outcomes** (bridge/run envelopes, capped text). The goal is a compounding signal: routing and quality improve over time; durable institutional memory is still incremental (see `GAPS.md` and hardening docs).

3. **CLI-first execution surface** — Heavy work is delegated to **CLI-based agentic runtimes** (subprocess + framed IO), not re-embedded vendor HTTP stacks inside Ham. **Auth and account state stay with the tool** (its login flows, tokens on disk, device/browser steps). Ham supplies **scoped intent, policy limits, and capture**; Hermes reasons over **comparable envelopes** regardless of whether the muscle is Factory/Droid-style, Claude Code–style, ElizaOS-flavored hosts, OpenClaw-informed gateways, or future adapters—**one supervision vocabulary, many CLIs**.

**Narrow exception (interactive dashboard chat):** The Ham API may expose **`POST /api/chat`** with **HAM-native** JSON to the browser and implement it via a **server-side adapter** to an external OpenAI-compatible agent API (see `docs/HERMES_GATEWAY_CONTRACT.md`, `src/integrations/nous_gateway_client.py`). The browser **never** calls that gateway directly. This does **not** replace **`HermesReviewer`** / `main.py` critique-on-run flow—they stay separate.

Shipped muscle today centers on **Bridge + Droid executor** (`src/tools/droid_executor.py`, `src/bridge/`). Reference notes (patterns only, not parity targets): `docs/reference/factory-droid-reference.md`, `docs/reference/openclaw-reference.md`, `docs/reference/elizaos-reference.md`. Ham remains **HAM-native** in naming and contracts; see `PRODUCT_DIRECTION.md`.

## Architecture

- `VISION.md` — canonical architecture, core pillars, design principles

## Pillar modules

- `src/hermes_feedback.py` — Hermes supervisory core + critic/learner surface (`HermesReviewer` MVP complete; supervisory wiring still transitional)
- `src/tools/droid_executor.py` — Droid execution engine (implementation-heavy execution; local self-orchestration while executing)
- `src/memory_heist.py` — Context Engine (repo scan, git state, config, sessions)
- `src/llm_client.py` — LiteLLM / OpenRouter wiring
- `src/swarm_agency.py` — Hermes-supervised **context assembly** (shared `ProjectContext` + per-role render budgets for Architect / routing / critic prompts); **not** a separate orchestration framework (no CrewAI)
- `src/registry/droids.py` — `DroidRecord` + `DroidRegistry` + `DEFAULT_DROID_REGISTRY` (builder, reviewer)
- `src/persistence/run_store.py` — read-side `RunStore` over `.ham/runs/*.json`
- `src/api/server.py` — FastAPI app: read API (`/api/status`, `/api/runs`, …) plus **`POST /api/chat`** (see `src/api/chat.py`) and **`GET /api/cursor-skills`**
- `src/ham/cursor_skills_catalog.py` — loads `.cursor/skills` for chat control plane + API index
- `src/ham/ui_actions.py` — parse/validate `HAM_UI_ACTIONS_JSON` for chat → UI
- `docs/HAM_CHAT_CONTROL_PLANE.md` — chat + skills intent mapping roadmap

## Deploy (API on GCP)

- `Dockerfile` — Cloud Run–style image (`uvicorn src.api.server:app`, `PORT` aware)
- `docs/DEPLOY_CLOUD_RUN.md` — Artifact Registry + `gcloud builds submit` + `gcloud run deploy` + env vars
- `docs/DEPLOY_HANDOFF.md` — Vercel + Cloud Run checklist (what to set in each host)
- `docs/examples/ham-api-cloud-run-env.yaml` — copy to `.gcloud/ham-api-env.yaml` for `--env-vars-file`
- `scripts/verify_ham_api_deploy.sh` — CORS + `/api/chat` smoke test against a deployed API
- `scripts/render_cloud_run_env.py` — merge `.env` into `.gcloud/ham-api-env.yaml` for `gcloud run deploy --env-vars-file` (avoids committing OpenRouter keys)

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

## Guidance

- `.cursor/rules/` — Cursor project rules (architecture, diffs, roles, vision sync)
- `.cursor/skills/` — reusable agent skills (hardening, wiring, auditing, testing)
- `CURSOR_SETUP_HANDOFF.md` — human guide to rules, skills, subagents, commands
- `CURSOR_EXACT_SETUP_EXPORT.md` — verbatim snapshot of Cursor setup + first-class docs (regenerate via `python scripts/build_cursor_export.py`)
- `GAPS.md` — tracked gaps and active implementation notes

## Frontend (workspace UI)

- `frontend/` — Vite + React workspace; `npm run dev` (port 3000), `npm run lint` (`tsc --noEmit`)

## Tests

- `tests/test_memory_heist.py` — Context Engine + Phase 1/3 guardrails (18 cases)
- `tests/test_hermes_feedback.py` — Critic MVP + Phase 3 guardrails (7 cases)
- `tests/test_droid_registry.py` — Droid registry conventions (10 cases)
- Run: `python -m pytest` — full suite (`pytest.ini` sets `pythonpath = .`; 158+ cases as of UI actions)
- Other tests under `tests/` as added; bootstrap with `/test-context-regressions` for Context Engine focus
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

Adapted from Claude Code's context-awareness runtime. This module gives every
agent in the swarm a grounded understanding of the local repository:

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
| Read API + run store | `src/api/server.py`, `src/persistence/run_store.py` | Thin FastAPI layer over `RunStore` (`.ham/runs/`): status, runs list/detail, profiles, droids; read-only Context Engine snapshot (`/api/context-engine`, `/api/projects/{id}/context-engine`) for dashboard wiring |
| Workspace UI | `frontend/` (Vite + React) | Extracted workspace; TypeScript types aligned with persisted run / bridge shapes |
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

**Tests**: full `pytest` suite including registry, bridge, main loop, droid registry, API/CORS, control-plane catalog + UI action parsing, and persistence tests — **158 passed** regression/guardrail cases (`pytest.ini` sets `pythonpath = .`; GitHub Actions runs `pytest` + frontend `tsc`).

**Next milestone**: **safe settings mutations** from chat/API (audited config writes) on top of structured UI actions + **`/api/cursor-skills`**; continue Bridge-profile hardening.

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

## Active implementation notes (Cursor / hardening)

- Context Engine hardening and **Phase 1** (Hermes-aligned scanning, tool-output pruning, config-driven compaction thresholds) are **complete** in `src/memory_heist.py`; **Phase 3** guardrail tests are in `tests/test_memory_heist.py` (18 cases).
- **Phase 2** Critic MVP is **complete** in `src/hermes_feedback.py` (LLM-backed `HermesReviewer.evaluate()`, stable schema, conservative fallback); **Phase 3** tests in `tests/test_hermes_feedback.py` (7 cases). **`python -m pytest tests/test_memory_heist.py tests/test_hermes_feedback.py` — 25 passed** (verify locally after edits).
- Keep `_extract_prior_summary` marker parsing coupled with `_format_continuation` wording on future edits (see `docs/HAM_HARDENING_REMEDIATION.md`).
- **`VISION.md` must stay in sync** with real module status after each milestone (see `.cursor/rules/vision-sync.mdc`).
- **Avoid** multiple `ProjectContext.discover()` passes for one run; prefer one shared snapshot and role-appropriate render budgets.
- **Prefer config-driven** context budgets (`.ham.json` / merged config) over long-term hardcoded magic numbers.
- **Deferred (unchanged direction):** no second orchestration harness, no FTS5 durable learning persistence yet, no Phase 4 Droid execution-safety work until Droid is real.
- **Dashboard chat (Phase A):** `POST /api/chat` is **shipped** with HAM-native DTOs, in-memory `ChatSessionStore`, and `src/integrations/nous_gateway_client.py` (**mock** or **http** per env). Streaming, SQLite session persistence, and mission/walking APIs are **not** started here.

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
**Blocked by**: Droid executor is still a stub. Address when real subprocess
execution lands.
**Fix**: Add a `ProjectContext.refresh()` method or rebuild `ContextBuilder` after
each Droid execution step.

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
expansion waits on real Droid execution and supervisory integration tests.
**Next (when Droid is real):** refresh-after-tool semantics, subprocess/output
caps, optional end-to-end supervisory smoke without orchestration redesign.

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
- **Tests**: `tests/test_memory_heist.py` — 18 cases (hardening + Phase 1 + Phase 3 guardrails). `tests/test_hermes_feedback.py` — 7 cases (Phase 2 critic MVP + Phase 3). Together **25 passed** with `python -m pytest tests/test_memory_heist.py tests/test_hermes_feedback.py` (re-run after changes to confirm).

## Remediation order executed (record)

1. Quick wins completed: `_extract_key_files`, `_format_continuation` + **synced `_extract_prior_summary` markers**, `has_summary` / `with_memory`.
2. Safety caps completed: `MAX_DIFF_CHARS` + `git_diff`, budget params threaded through `ContextBuilder` / `render`, `MAX_SUMMARY_CHARS` + timeline cap + `_merge_summaries` cap.
3. Wiring completed: `swarm_agency.py` uses **one** `ProjectContext.discover` with per-agent `render` budgets.
4. Verification/docs completed: regression tests added and passing; `VISION.md` status updated.

## Deferred (not in this milestone)

- LLM-backed session summarization (`SessionMemory._summarize()` remains string-based).
- Context refresh immediately after Droid writes (until Droid is real).
- Supervisory-flow callbacks/hooks for `SessionMemory` (separate integration task).
- Critic **learning** persistence (FTS5 / durable review store) — not started; no second harness layer.
- Phase 4 Droid execution-safety hardening — deferred until `droid_executor` is real.
```

---

