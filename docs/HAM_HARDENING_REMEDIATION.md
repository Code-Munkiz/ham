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
