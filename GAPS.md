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

## Active Gaps

### 1. Hermes supervisory wiring into execution flow

**Status**: Not started
**Impact**: Architecture target names Hermes as supervisory orchestrator, but
current runtime flow is still transitional scaffold code. This leaves an
architecture-vs-runtime gap that must be closed without collapsing execution
ownership into Hermes.
**Blocked by**: Incremental runtime migration planning and test coverage for
supervisory routing semantics.
**Fix**: Add explicit supervisory routing flow that delegates execution-heavy
work to Droid by default, preserves separation-of-duties, and keeps Hermes
direct execution limited to tiny bounded critic-native tasks.

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

**Status**: Stub (`droid_executor` returns placeholder string)
**Impact**: No actual parallel execution. Supervisory routing can delegate but
nothing runs.
**Blocked by**: Factory Droid CLI binary availability and API surface.
**Fix**: Implement real `subprocess.run()` call with timeout, output capture,
and size cap on returned stdout/stderr.

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
