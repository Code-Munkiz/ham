# Cursor setup — exact export

Generated snapshot of `.cursor/` rules and skills, plus first-class context documents from the handoff source-of-truth list.

## File counts (this document)

| Category | Count |
|----------|-------|
| Rules (`.mdc`) | 12 |
| Skills (`SKILL.md`) | 5 |
| First-class context | 4 |
| **Total embedded files** | **21** |

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

Wire `ContextBuilder` into all agents in `src/swarm_agency.py`.

1. Read the Agent Context Wiring skill (`.cursor/skills/agent-context-wiring/SKILL.md`).
2. Read `src/swarm_agency.py` and `src/memory_heist.py`.
3. Add `from src.memory_heist import ContextBuilder` (or equivalent) if missing.
4. **Single discovery pass**: build **one** `ProjectContext` (or one `ContextBuilder` that shares a single discovered context) and vary **only render budgets** per agent. Do not create multiple `ContextBuilder()` instances that each run a full `ProjectContext.discover()` (duplicate scans and git calls).
5. Prefer loading per-agent budgets from `.ham.json` / config (`discover_config`) over long-term hardcoded magic numbers; use code defaults only as fallback.
6. Inject per-agent rendered context strings into each agent's `backstory`.
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
4. Check: is `memory_heist.py` actually imported and used by `swarm_agency.py`?
5. Check: does each agent's definition respect role boundaries?
6. Report as a table: pillar, module, vision role, actual status, gaps.
7. If the table fixes factual drift, apply updates to `VISION.md` (status table and next milestone) per the vision-sync rule.
```

---

## `.cursor/rules/ham-architecture.mdc`

```
---
description: Enforces the Ham five-pillar architecture. Apply always.
alwaysApply: true
---

# Ham Architecture Contract

The architecture is fixed unless the user explicitly approves a change.

## Five Pillars

| Pillar | Module | Role |
|--------|--------|------|
| Orchestrator | CrewAI (`src/swarm_agency.py`) | Routes tasks, manages agents |
| Muscle | Factory Droid CLI (`src/tools/droid_executor.py`) | Parallel shell execution via subprocess |
| Critic | Hermes (`src/hermes_feedback.py`) | Reviews output, learns via FTS5 |
| Context Engine | `src/memory_heist.py` | Repo scanning, git state, config, session memory |
| LLM Routing | LiteLLM / OpenRouter (`src/llm_client.py`) | Model-agnostic API layer, BYOK |

## Rules

- Do not merge, split, or reassign pillar responsibilities.
- Do not introduce new orchestration frameworks alongside CrewAI.
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
| **Commander** | Delegate work, invoke Droid tool, coordinate sequencing | Make design decisions, review quality, persist learnings |
| **Hermes Critic** | Review outputs, flag regressions, feed FTS5 learning DB | Plan architecture, invoke Droid, modify source directly |

- When adding a new agent, define its charter before writing code.
- When modifying `swarm_agency.py`, verify no agent's `goal` or `tools` list violates these boundaries.
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

- Redesign the Commander or Hermes agents.
- Change the CrewAI process type or task graph.
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

Audit the Droid executor tool for safety and correct integration with CrewAI.

## Scope -- Do This

- Verify `droid_executor` is a proper CrewAI `@tool` with typed args and docstring.
- Verify subprocess calls use `capture_output=True`, `text=True`, and a `timeout`.
- Verify stdout/stderr output is capped before returning to the agent.
- Verify only the Commander agent has `droid_executor` in its `tools` list.
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
- Verify the Hermes Critic agent in `swarm_agency.py` does NOT have `droid_executor` in its tools.
- Verify `.hermes/` is in `IGNORE_DIRS` in `memory_heist.py`.
- When real hermes-agent integration lands, verify it writes to `.hermes/` and the FTS5 DB path is configurable.

## Out of Scope -- Do NOT

- Redesign the CrewAI task graph.
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
  Wire memory_heist ContextBuilder into CrewAI agent backstories in swarm_agency.py
  using a single shared ProjectContext and per-agent render budgets. Use when connecting
  agents to repo context, adjusting budgets, or integrating SessionMemory into task callbacks.
---

# Agent Context Wiring

## When to Use

- Integrating `ContextBuilder` into `src/swarm_agency.py`
- Setting per-agent token / instruction / diff budgets
- Wiring `SessionMemory` into CrewAI task callbacks

## Anti-pattern: N full scans

**Do not** create one `ContextBuilder()` per agent if each constructor calls `ProjectContext.discover()` independently. That repeats `scan_workspace`, instruction discovery, config merge, and multiple git subprocess calls.

## Preferred pattern: one discovery, vary render only

1. Call `ProjectContext.discover()` **once** (or construct one `ContextBuilder` that owns a single `project` snapshot).
2. For each agent, render context with **different budgets** (instruction caps, diff caps) by passing parameters into render helpers — or add a small API on `ContextBuilder` / `ProjectContext` such as `render_for_agent(budgets=...)`.
3. Concatenate each agent's static role line + that rendered string into `backstory`.

Example shape (adapt to actual `memory_heist` API after hardening):

```python
from pathlib import Path
from src.memory_heist import ProjectContext  # or ContextBuilder with shared project

def build_swarm_crew(user_prompt: str) -> Crew:
    root = Path.cwd()
    project = ProjectContext.discover(root)

    arch_text = project.render(
        max_instruction_file_chars=4_000,
        max_total_instruction_chars=16_000,
        max_diff_chars=8_000,
    )
    cmd_text = project.render(
        max_instruction_file_chars=2_000,
        max_total_instruction_chars=4_000,
        max_diff_chars=2_000,
    )
    # ... critic with its own budgets ...

    architect = Agent(
        backstory=f"You plan structure and interfaces.\n\n{arch_text}",
        ...
    )
```

Until `ProjectContext.render()` accepts budget overrides, implement the minimal change in `memory_heist.py` to support this pattern rather than constructing multiple discoverers.

## Config-driven budgets

Prefer reading per-agent budgets from merged project config (`discover_config` / `.ham.json`) with sane code defaults. Avoid leaving magic numbers only in `swarm_agency.py` long-term.

## Budget guidelines (defaults until config exists)

| Agent | Instruction budget (total) | Diff budget | Rationale |
|-------|---------------------------|-------------|-----------|
| Architect | Higher (e.g. 16,000) | Full (e.g. 8,000) | Needs design + instructions |
| Commander | Lower (e.g. 4,000) | Tighter (e.g. 2,000) | Task scope, less prose |
| Hermes Critic | Medium (e.g. 8,000) | Default | Enough to review |

## Verification

1. Every agent in `build_swarm_crew()` receives repo-grounded context in `backstory`.
2. Repo scan + git capture runs **once** per crew build (unless explicitly refreshing after Droid).
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

## `.cursor/skills/hermes-review-loop-validation/SKILL.md`

```
---
name: hermes-review-loop-validation
description: >-
  Validate the Hermes critic review loop: verify the Critic agent receives
  correct context, invokes HermesReviewer.evaluate(), and persists learning
  signals to FTS5. Use when modifying hermes_feedback.py, the Critic agent
  definition, or the review pipeline.
---

# Hermes Review Loop Validation

## When to Use

- Modifying `src/hermes_feedback.py`
- Changing the Hermes Critic agent in `src/swarm_agency.py`
- Integrating the real hermes-agent client
- Verifying FTS5 persistence after reviews

## Review Loop Contract

```
Commander output
      |
      v
Hermes Critic agent (CrewAI)
      |
      v
HermesReviewer.evaluate(code, context)
      |
      v
FTS5 DB (persist learning signals)
```

## Validation Checklist

1. The Critic agent's `goal` must reference review and learning, not planning or execution.
2. The Critic agent must NOT have `droid_executor` in its `tools` list.
3. `HermesReviewer.evaluate()` must receive the actual code output, not a summary.
4. `HermesReviewer.evaluate()` must receive context from `ContextBuilder` so it knows repo state.
5. When the real hermes-agent client is integrated:
   - Verify it writes to `.hermes/` directory
   - Verify `.hermes/` is in `IGNORE_DIRS` so agents don't ingest the DB as source
6. The evaluate response must include structured fields: `ok`, `notes`, `code`, `context` at minimum.

## Current State

`HermesReviewer` is a stub. The `evaluate()` method returns a hardcoded dict.
Integration with the real hermes-agent API is pending.
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
- Checking total prompt size before CrewAI kickoff
- After changing instruction files, config, or git diff caps

## Audit Steps

1. Read `src/memory_heist.py` and note all `MAX_*` constants.
2. For each agent in `src/swarm_agency.py`, estimate the total backstory size:
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

## Architecture

- `VISION.md` — canonical architecture, five pillars, design principles

## Pillar modules

- `src/memory_heist.py` — Context Engine (repo scan, git state, config, sessions)
- `src/swarm_agency.py` — CrewAI orchestrator (agent + task definitions)
- `src/hermes_feedback.py` — Hermes critic (review loop, FTS5 learning)
- `src/tools/droid_executor.py` — Droid CLI tool (parallel shell execution)
- `src/llm_client.py` — LiteLLM / OpenRouter wiring

## Configuration & entry

- `main.py` — runtime entrypoint (CLI arg parsing, env load, crew assembly)
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

## Tests

- `tests/` — regression tests (bootstrap with `/test-context-regressions`)
```

---

## `VISION.md`

```
# Ham — Vision & Architecture

## What Ham Is

Ham is an open-source, multi-agent autonomous developer swarm that executes
the full Software Development Life Cycle (SDLC). It is not a chatbot wrapper.
It is an opinionated assembly line: plan, build, review, learn, repeat.

## The Five Pillars

### 1. The Orchestrator — CrewAI

CrewAI manages the workflow graph. It routes tasks between agents, enforces
sequencing (sequential or hierarchical process), and owns the agent lifecycle.
Every agent in the swarm is a CrewAI `Agent`; every unit of work is a CrewAI
`Task`. CrewAI is the spine — nothing moves without it.

### 2. The Muscle — Factory Droid CLI

Factory Droid CLI is the execution engine, wrapped as a CrewAI `@tool` so
agents can trigger massive parallel shell execution. When the Commander agent
needs to scaffold 40 files, run a test matrix, or batch-apply refactors, it
delegates to Droid via `subprocess`. Droid is pure throughput — it does not
think, it executes.

### 3. The Critic / Learner — Hermes

Hermes (NousResearch's hermes-agent) acts as a dedicated Reviewer Agent in
the Crew. After Droid executes, Hermes reviews the output: checks code quality,
catches regressions, and feeds learning signals back into a local FTS5 SQLite
database. Over time Hermes accumulates institutional knowledge about the
project — what patterns work, what breaks, what to avoid. This is the swarm's
long-term memory and taste.

### 4. The Context Engine — memory_heist.py

Adapted from Claude Code's context-awareness runtime. This module gives every
agent in the swarm a grounded understanding of the local repository:

- **Workspace scanning**: filesystem tree, file inventory, ignore rules.
- **Instruction file discovery**: hierarchical SWARM.md / AGENTS.md loading
  from project root up through ancestors.
- **Config discovery**: `.ham.json` / `.ham/settings.json` merge chain.
- **Git state capture**: status, diff, recent log — injected into prompts so
  agents know what changed and what's staged.
- **Session compaction**: conversation history summarization and persistence
  so agents can survive context window limits across long tasks.

The Context Engine does NOT make decisions. It assembles ground truth and
injects it into agent prompts so they don't hallucinate about repo state.

### 5. LLM Routing — LiteLLM / OpenRouter

LiteLLM provides the model-agnostic API layer. OpenRouter provides the BYOK
(bring your own key) gateway. Together they let Ham hot-swap models on the
fly — use a fast model for planning, a strong model for code generation, a
cheap model for summarization. Model selection is config-driven, not hardcoded.

## How They Connect

```
User Prompt
    │
    ▼
┌─────────────────────────────────────────────┐
│  CrewAI Orchestrator                        │
│                                             │
│  ┌───────────┐  ┌───────────┐  ┌─────────┐ │
│  │ Architect │→ │ Commander │→ │ Hermes  │ │
│  │  (plan)   │  │ (execute) │  │ (review)│ │
│  └───────────┘  └─────┬─────┘  └────┬────┘ │
│                       │              │      │
│                       ▼              ▼      │
│               ┌──────────────┐  ┌────────┐  │
│               │ Droid CLI    │  │ FTS5   │  │
│               │ (subprocess) │  │ (learn)│  │
│               └──────────────┘  └────────┘  │
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

## Current State

The skeleton is assembled. Each pillar has a module:

| Pillar         | Module                     | Status     |
|----------------|----------------------------|------------|
| Orchestrator   | `src/swarm_agency.py`      | Scaffold   |
| Muscle         | `src/tools/droid_executor.py` | Scaffold |
| Critic         | `src/hermes_feedback.py`   | Stub       |
| Context Engine | `src/memory_heist.py`      | Rebranded (Ham paths/ignores); hardening + wiring pending |
| LLM Routing    | `src/llm_client.py`        | Working    |

**Next milestone**: harden memory_heist.py (diff/summary caps, configurable
budgets, continuation/parser marker safety), wire a **single** discovered
`ProjectContext` into `swarm_agency.py` with per-agent render budgets, add
regression tests, and keep this doc in sync.

## Design Principles

1. **Agents don't freestyle** — every agent gets grounded context from
   memory_heist before it touches anything. No hallucinating about repo state.
2. **Execution is dumb, review is smart** — Droid executes fast and blind;
   Hermes catches mistakes after the fact. Speed + quality without bottleneck.
3. **Learning compounds** — Hermes persists lessons in FTS5. The swarm gets
   better at *this specific project* over time.
4. **Models are disposable** — swap providers, swap models, swap pricing.
   The architecture doesn't care which LLM is behind the API.
5. **Local-first** — no cloud dependencies for context, memory, or learning.
   Everything runs against the local filesystem and local DBs.
```

---

## `GAPS.md`

```
# Ham — Gap Tracker

Gaps between the current codebase and the VISION.md next milestone.
Each item tracks what is missing, why it matters, and what blocks it.

## Active implementation notes (Cursor / hardening)

- The hardening plan is **mostly correct** but **incomplete** until `_extract_prior_summary` is updated **together with** `_format_continuation` (marker coupling); see `docs/HAM_HARDENING_REMEDIATION.md`.
- **`VISION.md` must stay in sync** with real module status after each milestone (see `.cursor/rules/vision-sync.mdc`).
- **Avoid** multiple `ContextBuilder` instances each running a full `ProjectContext.discover()`; prefer one shared snapshot and per-agent render budgets (see `.cursor/skills/agent-context-wiring/SKILL.md`).
- **Prefer config-driven** agent context budgets (`.ham.json` / merged config) over long-term hardcoded magic numbers in `swarm_agency.py`.
- **Test coverage** is required before closing the Context Engine milestone; run `/test-context-regressions`.

## Active Gaps

### 1. Context refresh after Droid mutations

**Status**: Not started
**Impact**: After Droid modifies the repo (creates/deletes files), any previously
captured `ProjectContext` snapshot is stale. Agents making decisions after Droid
runs may reference files that no longer exist or miss newly created ones.
**Blocked by**: Droid executor is still a stub. Address when real subprocess
execution lands.
**Fix**: Add a `ProjectContext.refresh()` method or rebuild `ContextBuilder` after
each Droid execution step.

### 2. Role-specific context shaping

**Status**: Planned (in hardening plan, Phase 2 Fix #5)
**Impact**: All agents currently get identical context strings. The Architect
needs full instruction files; the Commander needs minimal instructions but full
git state; Hermes needs enough to review but not the full tree.
**Blocked by**: `ContextBuilder` token limit params not yet implemented.
**Fix**: Make `MAX_*` constants overridable via `ContextBuilder` constructor and
use different budgets per agent in `swarm_agency.py`.

### 3. LLM-backed session summarization

**Status**: Not started
**Impact**: `SessionMemory._summarize()` is string formatting, not real
summarization. Compacted summaries are verbose timelines that waste tokens.
Repeated compaction causes unbounded nesting growth.
**Blocked by**: Need to decide which model to use for summarization (cheap/fast
via LiteLLM) and whether summarization happens inline or async.
**Fix**: Call `llm_client.get_crew_llm()` from `_summarize()` with a short
system prompt. Add `MAX_SUMMARY_CHARS` hard cap as a safety net.

### 4. Real Hermes integration

**Status**: Stub (`HermesReviewer.evaluate()` returns hardcoded dict)
**Impact**: No actual code review or learning is happening. The Critic agent
exists but produces no real value.
**Blocked by**: hermes-agent client API not yet integrated.
**Fix**: Implement the real client in `hermes_feedback.py`, configure FTS5 DB
path to `.hermes/`, verify `.hermes/` is in `IGNORE_DIRS`.

### 5. Real Droid CLI integration

**Status**: Stub (`droid_executor` returns placeholder string)
**Impact**: No actual parallel execution. Commander agent can delegate but
nothing runs.
**Blocked by**: Factory Droid CLI binary availability and API surface.
**Fix**: Implement real `subprocess.run()` call with timeout, output capture,
and size cap on returned stdout/stderr.

### 6. Test coverage

**Status**: No tests exist
**Impact**: Every behavioral change to `memory_heist.py` is unverified.
Cross-platform path handling, config discovery, and compaction logic are
untested.
**Blocked by**: Nothing. Can be created now.
**Fix**: Run `/test-context-regressions` to generate `tests/test_memory_heist.py`.

## Completed Items

- Rebrand memory_heist.py (Claude -> Ham naming): **Done** (Part 1)
- Add `.sessions` and `.hermes` to IGNORE_DIRS: **Done** (Part 1)
```

---

## `docs/HAM_HARDENING_REMEDIATION.md`

```
# Ham — Context Engine hardening audit & remediation

Canonical reference for the **memory_heist** hardening plan, audit findings, and safe execution order. Align with `VISION.md` and `.cursor/skills/context-engine-hardening/SKILL.md`.

## Next milestone (VISION.md)

Rebrand Context Engine, Ham ignore rules, wire `memory_heist` into `swarm_agency.py` so agents consume grounded repo context. Rebranding and ignore rules are **done** in code; wiring and hardening phases below are **pending** until implemented.

## Audit summary (accurate)

The hardening plan correctly targets: cross-platform `_extract_key_files`, agent-oriented `_format_continuation`, public `has_summary`, capped `git_diff`, configurable instruction/diff budgets on `ContextBuilder`, capped `_summarize` / `_merge_summaries`, and wiring into `swarm_agency.py`.

## Critical gap (must fix with continuation change)

`_extract_prior_summary()` uses hardcoded `end_markers` that must match `_format_continuation()` closing text. Changing continuation phrasing **without** updating markers breaks summary extraction and can cause unbounded summary growth.

**Remediation**: Update `end_markers` in `_extract_prior_summary` whenever `_format_continuation` changes; keep **legacy** markers for old session JSON until migrated.

## Other guidance

- **VISION.md**: Update the "Current State" table and "Next milestone" after each milestone that changes repo reality (see `.cursor/rules/vision-sync.mdc`).
- **Single discover**: Avoid multiple `ContextBuilder()` / `ProjectContext.discover()` calls per crew build; share one snapshot and vary render budgets only (see Agent Context Wiring skill).
- **Config-driven budgets**: Prefer `.ham.json` / merged config for per-agent caps; avoid permanent magic numbers only in `swarm_agency.py`.
- **Tests**: Add/update tests before closing the milestone; cover marker parsing (new + legacy), diff caps, and key-file extraction.

## Remediation order (dependency-safe)

1. Quick wins: `_extract_key_files`, `_format_continuation` + **sync `_extract_prior_summary` markers**, `has_summary` / `with_memory`.
2. Safety caps: `MAX_DIFF_CHARS` + `git_diff`, budget params threaded through `ContextBuilder` / `render`, `MAX_SUMMARY_CHARS` + timeline cap + `_merge_summaries` cap.
3. Wire `swarm_agency.py` with **one** `ProjectContext.discover`, per-agent `render` budgets.
4. Tests + `VISION.md` status update.

## Deferred (not in this milestone)

- LLM-backed session summarization.
- Context refresh immediately after Droid writes (until Droid is real).
- CrewAI callbacks for `SessionMemory` (separate integration task).
```

---

