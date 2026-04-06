# Ham — Gap Tracker

Gaps between the current codebase and the VISION.md next milestone.
Each item tracks what is missing, why it matters, and what blocks it.

## Active implementation notes (Cursor / hardening)

- Context Engine hardening and **Phase 1** (Hermes-aligned scanning, tool-output pruning, config-driven compaction thresholds) are **complete** in `src/memory_heist.py`; **Phase 3** guardrail tests are in `tests/test_memory_heist.py` (18 cases).
- **Phase 2** Critic MVP is **complete** in `src/hermes_feedback.py` (LLM-backed `HermesReviewer.evaluate()`, stable schema, conservative fallback); **Phase 3** tests in `tests/test_hermes_feedback.py` (7 cases). **`python -m pytest tests/test_memory_heist.py tests/test_hermes_feedback.py` — 25 passed** (verify locally after edits).
- Keep `_extract_prior_summary` marker parsing coupled with `_format_continuation` wording on future edits (see `docs/HAM_HARDENING_REMEDIATION.md`).
- **`VISION.md` must stay in sync** with real module status after each milestone (see `.cursor/rules/vision-sync.mdc`).
- **Avoid** multiple `ContextBuilder` instances each running a full `ProjectContext.discover()`; prefer one shared snapshot and per-agent render budgets (see `.cursor/skills/agent-context-wiring/SKILL.md`).
- **Prefer config-driven** agent context budgets (`.ham.json` / merged config) over long-term hardcoded magic numbers in `swarm_agency.py`.
- **Deferred (unchanged direction):** no second orchestration harness, no FTS5 learning persistence yet, no Phase 4 Droid execution-safety work until Droid is real.

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

### 2. Role-specific context shaping (follow-up refinement)

**Status**: Baseline implemented; further refinement optional
**Impact**: All agents currently get identical context strings. The Architect
needs full instruction files; the Commander needs minimal instructions but full
git state; Hermes needs enough to review but not the full tree.
**Follow-up**: Current wiring already uses per-agent render budgets on a shared
`ProjectContext` snapshot. Additional shaping (role-specific section filtering,
different tree/config emphasis) is a next-phase quality improvement.

### 3. LLM-backed session summarization

**Status**: Not started
**Impact**: `SessionMemory._summarize()` is string formatting, not real
summarization. Compacted summaries are verbose timelines that waste tokens.
Repeated compaction causes unbounded nesting growth.
**Blocked by**: Need to decide which model to use for summarization (cheap/fast
via LiteLLM) and whether summarization happens inline or async.
**Fix**: Call `llm_client.get_crew_llm()` from `_summarize()` with a short
system prompt. Add `MAX_SUMMARY_CHARS` hard cap as a safety net.

### 4. Critic learning persistence (FTS5 / external Hermes client)

**Status**: Deferred (not started)
**Impact**: `HermesReviewer.evaluate()` is a **minimal LLM-backed critic MVP**
(via `src/llm_client.py`); there is still no FTS5 persistence, no external
hermes-agent-only client, and no durable “institutional memory” from reviews.
**Blocked by**: Product choice and follow-up milestone after Droid + task
graph are farther along.
**Fix (later):** Add FTS5-backed persistence under `.hermes/` (with `.hermes/`
already in `IGNORE_DIRS`), or integrate a dedicated hermes-agent API if required;
wire reviewer into crew tasks explicitly if not already.

### 5. Real Droid CLI integration

**Status**: Stub (`droid_executor` returns placeholder string)
**Impact**: No actual parallel execution. Commander agent can delegate but
nothing runs.
**Blocked by**: Factory Droid CLI binary availability and API surface.
**Fix**: Implement real `subprocess.run()` call with timeout, output capture,
and size cap on returned stdout/stderr.

### 6. Test coverage (follow-up after Droid / crew wiring)

**Status**: Phase 3 guardrail suite **complete** for current Context Engine + critic MVP
**Impact**: `tests/test_memory_heist.py` and `tests/test_hermes_feedback.py`
cover hardening, Phase 1–2 behavior, and follow-up guardrails (tail preservation,
config precedence, repeated compaction bounds, reviewer schema/fallback). Further
expansion waits on real Droid execution and crew-level integration tests.
**Next (when Droid is real):** refresh-after-tool semantics, subprocess/output caps,
optional end-to-end crew smoke without orchestration redesign.

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
