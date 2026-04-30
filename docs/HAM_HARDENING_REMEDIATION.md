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
- Context refresh immediately after Droid writes (not wired yet; subprocess backend exists — see `GAPS.md` gap 2).
- Supervisory-flow callbacks/hooks for `SessionMemory` (separate integration task).
- Critic **learning** persistence (FTS5 / durable review store) — not started; no second harness layer.
- Phase 4 Droid execution-safety hardening — deferred until mutating mission scope and policy milestones (bounded executor already ships; see `GAPS.md` gap 6).
