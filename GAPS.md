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
