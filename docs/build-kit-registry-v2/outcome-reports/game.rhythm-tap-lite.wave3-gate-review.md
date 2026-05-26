# Wave 3 Gate Review: game.rhythm-tap-lite

> **Wave 3 generated-build gate · Local operator run · Not production telemetry · Not automated validator output**

---

## 1. Checkpoint metadata

| Field | Value |
|-------|--------|
| **Recipe id** | `game.rhythm-tap-lite` |
| **Review type** | Wave 3 generated-build gate (+ scaffold quality fix pass) |
| **Source** | local/manual generated output review |
| **Production telemetry** | no |
| **Automated validator** | no |
| **Generated output committed** | no |
| **Initial review date** | 2026-05-26 (UTC) |
| **Fix pass date** | 2026-05-26 (UTC) |
| **Initial artifact dir** | `/tmp/ham-rhythm-tap-wave3-gate-review/` |
| **Fixed rerun artifact dir** | `/tmp/ham-rhythm-tap-wave3-gate-review-fixed/` |
| **Repo HEAD (initial run)** | `f10144ff` — `feat(builder): route rhythm tap recipe behind registry flag` |
| **Repo HEAD (fix pass)** | uncommitted local changes to `src/ham/scaffold_quality.py` + tests only |

---

## 2. Prompt used

> Build a browser rhythm tap game where beat cues appear in sequence, the player presses space at the right time, earns perfect/good/miss scores based on timing accuracy, builds a combo streak, sees a final score, and can play again.

---

## 3. Generation path

### APIs used

| Component | Path / function |
|-----------|-----------------|
| Intent routing | `enrich_plan_metadata_with_registry_v2`, `select_registry_v2_app_type_for_prompt` |
| Scaffold context | `resolve_scaffold_context` |
| LLM scaffold | `generate_scaffold()` in `src/ham/builder_llm_scaffold.py` |
| Post-output inspect | `inspect_generated_scaffold_quality()` in `src/ham/scaffold_quality.py` |

No new repo script. Operator Python invocations of established public APIs only.

### Run configuration

| Setting | Initial run | Fixed rerun |
|---------|-------------|-------------|
| **Environment flag** | `HAM_BUILD_REGISTRY_V2_ENABLED=true` | same |
| **OpenRouter key** | Loaded from repo-root `.env` (not recorded) | same |
| **Output directory** | `/tmp/ham-rhythm-tap-wave3-gate-review/` | `/tmp/ham-rhythm-tap-wave3-gate-review-fixed/` |
| **Files produced** | 6 | 11 |
| **Assertions** | 4 | 5 |

### Route metadata (both runs)

| Check | Result |
|-------|--------|
| `select_registry_v2_app_type_for_prompt(prompt)` | `game.rhythm-tap-lite` |
| `registry_v2_app_type` in plan metadata | `game.rhythm-tap-lite` |
| Scaffold context source | **v2** |
| Rendered v2 context length | **9,990 chars** |
| v1 Builder Kit fallback | **Not used** |

### Repair guard

| Run | Inspector after repair |
|-----|------------------------|
| **Initial** | **1 issue** — `missing_result_state` (false positive; result UI existed) |
| **Fixed rerun** | **0 issues — clean** |

Metadata: `gate-metadata.json` in each artifact directory.

---

## 4. Gate checklist

### Initial run (Conditional pass baseline)

| Requirement | Observed | Pass/Partial/Fail | Notes |
|-------------|----------|-------------------|-------|
| Routes to `game.rhythm-tap-lite` | yes | **Pass** | Intent match confirmed |
| v2 context used, not v1 fallback | yes (`v2`, ~10.0k chars) | **Pass** | No Builder Kit fallback |
| Beat/cue sequence exists | `cues` array + sequential timeouts | **Pass** | Sequential cue timing loop |
| Timing window exists | `timingWindows.perfect` / `.good` | **Pass** | Offset compared on tap |
| Space/click/tap input wired | `Space` keydown → `handleTap()` | **Pass** | Prompt space input satisfied |
| Perfect/good/miss scoring exists | perfect +100, good +50, else streak reset | **Partial** | Miss had no explicit counter/panel |
| Combo/streak tracking exists | `streak` state | **Pass** | Streak displayed |
| Miss feedback exists | streak reset only | **Partial** | No dedicated miss panel |
| Final result state exists | `gameState === 'result'` + final score panel | **Partial** | UI present; stale `setFinalScore(score)` risk |
| Play-again/retry action exists | `Play Again` button | **Pass** | Restart path present |
| Inspector | `missing_result_state` | **Fail (false positive)** | Result UI existed; marker gap |

**Initial gate decision:** **Conditional pass**

### Fixed rerun (after scaffold quality guard improvements)

| Requirement | Observed | Pass/Partial/Fail | Notes |
|-------------|----------|-------------------|-------|
| Routes to `game.rhythm-tap-lite` | yes | **Pass** | Unchanged |
| v2 context used, not v1 fallback | yes (`v2`, ~10.0k chars) | **Pass** | Unchanged |
| Beat/cue sequence exists | `generateCues()` + indexed progression | **Pass** | 8-cue sequence |
| Timing window exists | 100 ms perfect / 200 ms good offsets | **Pass** | `judgeCue()` timing check |
| Space/click/tap input wired | `CuePanel` + `Space` handler | **Pass** | Space input wired |
| Perfect/good/miss scoring exists | `score.perfect/good/misses` counters | **Pass** | All three judgments update score object |
| Combo/streak tracking exists | `streak` incremented/reset | **Pass** | Shown on result panel |
| Miss feedback exists | `MissPanel` + `misses` counter | **Pass** | Visible miss label and metric |
| Final result state exists | `gameState === 'result'` + `ResultsPanel` | **Pass** | Score object passed directly (no stale closure capture) |
| Play-again/retry action exists | `Play Again` → `playAgain()` → `startGame()` | **Pass** | Full round restart |
| No no-op/stub primary gameplay actions | `judgeCue`, scoring updates | **Pass** | No empty reducer stubs |
| No import/export mismatch | default imports consistent | **Pass** | Inspector clean |
| No product drift | rhythm tap only | **Pass** | No timer/productivity/medical/gambling drift |
| Inspector | post-repair | **Pass** | **0 issues** |

**Fixed rerun gate decision:** **Pass**

---

## 5. Generated output summary

### Initial run (`/tmp/ham-rhythm-tap-wave3-gate-review/`)

| Path | Role |
|------|------|
| `src/components/RhythmGame.tsx` | Monolithic cue/score/streak/result loop |
| `src/App.tsx` | Shell wrapper |
| `index.html`, `src/main.tsx`, `src/index.css`, `vite.config.ts` | Vite shell |

### Fixed rerun (`/tmp/ham-rhythm-tap-wave3-gate-review-fixed/`)

| Path | Role |
|------|------|
| `src/App.tsx` | Phase machine, cue judging, perfect/good/miss counters, result transition |
| `src/components/CuePanel.tsx` | Beat cue display + space input hook |
| `src/components/MissPanel.tsx` | Visible miss feedback |
| `src/components/ResultsPanel.tsx` | Final perfect/good/miss breakdown + streak + Play Again |
| `src/components/RoundControls.tsx` | Start control |
| `src/gameTypes.ts` | `GameState`, `ScoreState` types |

---

## 6. Positive observations

- **Routing and v2 context remained stable** across initial and fixed runs.
- **Scaffold quality guard improvements resolved the false positive** — initial `gameState === 'result'` output no longer triggers `missing_result_state`.
- **Fixed rerun produced recipe-shaped components** — `CuePanel`, `MissPanel`, `ResultsPanel`, perfect/good/miss counters, streak, play again.
- **Post-output inspector clean on fixed rerun** — 0 playability issues.
- **No product drift** in either run.

---

## 7. Remaining gaps

1. **LLM variance** — single fixed rerun; additional local reruns may differ in timing UX polish.
2. **Initial run artifacts remain as baseline evidence** — useful for before/after guard comparison only.
3. **Timing precision** — generated cue timing is approximate (`Date.now()` offsets); acceptable for Wave 3 DOM gate, not production rhythm engine quality.

---

## 8. Safety/routing observations

- **Routing unchanged** — conservative rhythm-tap intent gate; no routing edits in this fix pass.
- **Flag behavior:** v2 opt-in only; v1 default preserved when flag unset.
- **Scope:** Scaffold quality guard + tests + this review doc only; no API/frontend/Builder Studio/recipe YAML changes.

---

## 9. Fix pass — what changed

| Area | Change |
|------|--------|
| **Result-state markers** | Accept rhythm/timing patterns: `gameState/phase/status === 'result'`, `finalScore`, `showResults`, `Play Again` / `restartGame`, etc. |
| **Rhythm miss detector** | New `rhythm_miss_feedback_weak` when miss prompt + streak-only reset without miss counters/feedback |
| **Rhythm result detector** | New `rhythm_result_state_weak` when `setFinalScore(score)` captures likely stale closure state |
| **Repair guidance** | Rhythm/timing repair focus for miss feedback, final-score capture, result panel, and round-completion ordering |
| **Tests** | +6 focused cases in `tests/test_scaffold_quality.py` |

### Tests run (fix pass)

```bash
pytest tests/test_scaffold_quality.py -q
# 40 passed

pytest tests/test_builder_llm_scaffold_registry_manual_smoke.py \
       tests/test_build_registry.py \
       tests/test_build_registry_intent.py \
       tests/test_build_registry_scaffold_context.py \
       tests/test_builder_llm_scaffold_registry_context.py -q
# 549 passed
```

### Re-inspect of initial artifact (with updated guards)

| Issue | Result |
|-------|--------|
| `missing_result_state` | **Resolved** — no longer flagged |
| `rhythm_miss_feedback_weak` | **Correctly flagged** on initial streak-only miss handling |
| `rhythm_result_state_weak` | **Correctly flagged** on initial `setFinalScore(score)` pattern |

---

## 10. Gate decision

| Phase | Decision |
|-------|----------|
| **Initial generated run** | **Conditional pass** |
| **After scaffold quality fix pass + fixed rerun** | **Pass** |

Miss scoring and result-state gaps **improved**: fixed rerun has explicit miss counter + `MissPanel`, functional score object on result panel, and clean inspector (0 issues). The original `missing_result_state` false positive is **resolved** in the guard logic.

---

## 11. Recommendation

1. **Accept `game.rhythm-tap-lite` as Wave 3 routed + gated (Pass)** after this fix pass and clean fixed rerun.
2. **Do not enable Build Registry v2 by default** based on this gate alone.
3. **Keep v1 default** — flag-off behavior unchanged.
4. **Optional:** 1–2 additional local reruns for LLM variance sampling; not required for Wave 3 closure.

---

## 12. References

- [WAVE_3_PROGRESS_CHECKPOINT.md](../WAVE_3_PROGRESS_CHECKPOINT.md)
- [WAVE_3_POST_QUALITY_REPAIR_CHECKPOINT.md](../WAVE_3_POST_QUALITY_REPAIR_CHECKPOINT.md)
- [GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md](../GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md)
- [ROUTING_STRATEGY.md](../ROUTING_STRATEGY.md)
- [STATUS.md](../STATUS.md)
