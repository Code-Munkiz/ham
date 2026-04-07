# Ham — Cursor setup handoff (human guide)

This document explains the project’s Cursor rules, skills, subagents, and command prompts. It does not replace the source files; read [`AGENTS.md`](AGENTS.md) for the canonical index and [`CURSOR_EXACT_SETUP_EXPORT.md`](CURSOR_EXACT_SETUP_EXPORT.md) for verbatim copies.

## For new contributors

1. Read [`VISION.md`](VISION.md) for architecture and current pillar status.
2. Read [`AGENTS.md`](AGENTS.md) for first-class paths (pillar modules, entrypoint, docs).
3. Skim [`GAPS.md`](GAPS.md) for active gaps and implementation notes.
4. Use the **slash commands** in Cursor (documented in `.cursor/rules/commands.mdc`) when you are doing structured audits or wiring work.
5. When editing Python, the **code-quality** rule applies when `*.py` files are in scope; **memory-heist-conventions** applies when `src/memory_heist.py` is in scope.
6. After work that changes integration or milestone status, follow **vision-sync** and update `VISION.md` (status table, next milestone, architecture text/diagrams if wiring changed).

## Rules (always-on vs scoped)

| File | Always apply? | Purpose (from rule text) |
|------|---------------|---------------------------|
| `ham-architecture.mdc` | yes | Core architecture fixed unless explicitly approved; Hermes supervisory ownership and Droid execution ownership are enforced; no bypassing `ContextBuilder.build()` for repo context; no model names outside `llm_client.py`; see `VISION.md`. |
| `minimal-diffs.mdc` | yes | Scope changes narrowly; avoid unrelated refactors; >3 files → impact map + justification before editing; preserve public APIs unless breakage intended. |
| `no-hallucinated-state.mdc` | yes | Read files; use `git status` / `git diff`; no invented paths; quote real constants; do not claim tests passed without running them; do not claim files updated without a diff. |
| `role-boundaries.mdc` | yes | Supervisory-vs-execution boundaries are enforced: Hermes supervises/critiques, Droid executes; tiny bounded Hermes self-handling only; ambiguous execution defaults to Droid. |
| `vision-sync.mdc` | yes | After milestones: update `VISION.md` status table, next milestone, and stale architecture prose/diagrams; use `/refresh-swarm-contract` when unsure. |
| `commands.mdc` | yes | Defines slash workflows `/audit-context-engine`, `/wire-agent-context`, `/review-role-boundaries`, `/test-context-regressions`, `/rebrand-memory-heist`, `/refresh-swarm-contract`. |
| `code-quality.mdc` | `**/*.py` only | Public APIs; hard caps on growth-prone data; cross-platform paths; config-driven context budgets where possible; tests on behavior change; `SWARM.md`. |
| `memory-heist-conventions.mdc` | `src/memory_heist.py` only | Ham naming; `.ham` config; ignores; continuation/parser coupling between `_format_continuation` and `_extract_prior_summary`; tests after changes. |

**Subagent** rule files (`subagent-*.mdc`) are not always-on; they apply when the globs match (e.g. `swarm_agency.py`, `memory_heist.py`, `droid_executor.py`, `hermes_feedback.py`). Each file states a narrow “Do this / Do not” charter.

## Skills (`.cursor/skills/*/SKILL.md`)

| Skill | When it applies (from description / body) |
|-------|-----------------------------------------------|
| `context-engine-hardening` | Checklist for hardening `memory_heist.py`: ignores, Ham config, caps, cross-platform key files, **continuation/parser marker coupling**, tests. |
| `agent-context-wiring` | Wire repo context into the active orchestration path: **one** `ProjectContext.discover`, per-role render budgets only; avoid N full scans; prefer config-driven budgets. |
| `prompt-budget-audit` | Estimate prompts vs context window; audit `MAX_*`; flag red flags (diff size, timeline, merge caps). |
| `repo-context-regression-testing` | Six test categories for `memory_heist.py`; `pytest` + `tmp_path`; marker parsing old + new. |
| `hermes-review-loop-validation` | Hermes supervisory review path → `evaluate()` → learning signal contract; do not collapse Droid execution into review flow; `.hermes/` ignored. |

## Subagents (charter files)

| Subagent rule | Scope file | Intent (from charter) |
|---------------|------------|-------------------------|
| Architect Auditor | `swarm_agency.py` | Architect role/tools/tasks; planning only; shared context + budgets; do not redesign other agents or edit `memory_heist` / `llm_client`. |
| Context Engine Auditor | `memory_heist.py` | Naming, ignores, caps, diff, compaction, markers, public `with_memory`; do not redesign compaction LLM or `swarm_agency`. |
| Execution Safety Auditor | `droid_executor.py` | Invocation shape, subprocess safety, output cap, execution ownership on Droid; do not touch Context Engine. |
| Reviewer Loop Auditor | `hermes_feedback.py` | `evaluate` contract, supervisory review boundaries, `.hermes/` ignore; do not redesign orchestration graph or Droid. |

## Commands (what each runs)

Defined in `commands.mdc`; summarized here for discoverability:

| Command | Flow |
|---------|------|
| `/audit-context-engine` | Read `memory_heist.py` → hardening skill checklist (including marker coupling) → pass/fail table → no auto-fix. |
| `/wire-agent-context` | Wiring skill + `swarm_agency.py` + `memory_heist.py` → single discover, per-role budgets from config when possible → prompt/backstory surfaces → lint → diff; update `VISION.md` if milestone completes. |
| `/review-role-boundaries` | Role-boundaries rule + `swarm_agency.py` → violation table. |
| `/test-context-regressions` | Regression-testing skill → create/extend `tests/test_memory_heist.py` → `pytest -v`. |
| `/rebrand-memory-heist` | Grep Claude/Claw/stolen in `memory_heist.py` → fix per conventions or report clean. |
| `/refresh-swarm-contract` | `VISION.md` + all pillar modules → alignment table → memory_heist usage + roles → optionally patch `VISION.md` per vision-sync. |

## First-class repo context (also in `AGENTS.md`)

- `VISION.md`, `GAPS.md`, `AGENTS.md`
- `docs/HAM_HARDENING_REMEDIATION.md` — hardening audit, marker coupling, remediation order
- Pillar modules and entry/config paths are listed in `AGENTS.md`

## Regenerating the verbatim export

From repo root:

```bash
python scripts/build_cursor_export.py
```

writes [`CURSOR_EXACT_SETUP_EXPORT.md`](CURSOR_EXACT_SETUP_EXPORT.md).
