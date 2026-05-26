# Wave 3 Gate Review: game.reaction-time-challenge

> **Wave 3 generated-build gate · Local operator run · Not production telemetry · Not automated validator output**

---

## 1. Checkpoint metadata

| Field | Value |
|-------|--------|
| **Recipe id** | `game.reaction-time-challenge` |
| **Review type** | Wave 3 generated-build gate |
| **Source** | local/manual generated output review |
| **Production telemetry** | no |
| **Automated validator** | no |
| **Generated output committed** | no |
| **Review date** | 2026-05-26 (UTC) |
| **Local artifact dir** | `/tmp/ham-reaction-time-wave3-gate-review/` |
| **Repo HEAD** | `7b2181ce` — `feat(builder): route reaction time recipe behind registry flag` |

---

## 2. Prompt used

> Build a browser reaction-time game where the player waits for the screen to turn green, clicks as fast as possible, sees their reaction time in milliseconds, gets a false-start warning if they click too early, tracks their best score, and can play again.

---

## 3. Generation path

### APIs used

| Component | Path / function |
|-----------|-----------------|
| Intent routing | `enrich_plan_metadata_with_registry_v2`, `select_registry_v2_app_type_for_prompt` |
| Scaffold context | `resolve_scaffold_context` |
| LLM scaffold | `generate_scaffold()` in `src/ham/builder_llm_scaffold.py` |
| Post-output inspect | `inspect_generated_scaffold_quality()` in `src/ham/scaffold_quality.py` |

No new repo script. Single operator Python invocation of established public APIs.

### Run configuration

| Setting | Value |
|---------|--------|
| **Environment flag** | `HAM_BUILD_REGISTRY_V2_ENABLED=true` |
| **OpenRouter key** | Loaded from repo-root `.env` (not recorded) |
| **Output directory** | `/tmp/ham-reaction-time-wave3-gate-review/` |
| **Files produced** | 10 |
| **Assertions** | 5 |

### Route metadata

| Check | Result |
|-------|--------|
| `select_registry_v2_app_type_for_prompt(prompt)` | `game.reaction-time-challenge` |
| `registry_v2_app_type` in plan metadata | `game.reaction-time-challenge` |
| Scaffold context source | **v2** |
| Rendered v2 context length | **11,174 chars** |
| v1 Builder Kit fallback | **Not used** |

### Repair guard

Standard `generate_scaffold()` repair path ran (default pipeline). Post-output inspector: **0 issues — clean**.

Metadata captured in `/tmp/ham-reaction-time-wave3-gate-review/gate-metadata.json`.

---

## 4. Gate checklist

| Requirement | Observed | Pass/Partial/Fail | Notes |
|-------------|----------|-------------------|-------|
| Routes to `game.reaction-time-challenge` | yes | **Pass** | Intent match confirmed |
| v2 context used, not v1 fallback | yes (`v2`, ~11.2k chars) | **Pass** | No Builder Kit fallback |
| ready/wait/go state exists | `idle` → `waiting` → `ready` → `result` in `App.tsx` | **Pass** | Phase machine via `useState` |
| randomized delay exists | `Math.floor(Math.random() * 4000) + 1000` before `ready` | **Pass** | 1–5 s random delay |
| false-start handling exists | `handleFalseStart` + alert when click during `waiting` | **Pass** | Early click resets to `idle` |
| click/tap/key response wired | panel `onClick` → `handleReaction` when `ready` | **Partial** | Click wired; no keyboard/space handler |
| reaction time measured in milliseconds | `Date.now() - signalAt` displayed with `ms` suffix | **Pass** | Current + best scores in ms |
| best score or score history exists | `bestScore` state updated on valid reaction | **Pass** | `ReactionScoreTracker` shows best + current |
| result state exists | `phase === 'result'` + `ReactionResultsPanel` | **Pass** | Result panel renders reaction ms |
| play-again/retry action exists | `Play Again` button → `playAgain()` → `startGame()` | **Pass** | Full round restart |
| no no-op/stub primary gameplay actions | handlers mutate phase/scores | **Pass** | No empty reducer stubs |
| no import/export mismatch | default imports consistent | **Pass** | Inspector clean on import/export |
| no Pomodoro/stopwatch/typing/rhythm/medical/dashboard/gambling/physics drift | none observed in generated source | **Pass** | Reaction-time game only |
| generated output local-only | `/tmp/` only | **Pass** | Not committed |

**Overall quality:** **Playable (single-run)** — core wait → green signal → click → ms result → best score → play again loop is implemented without inspector flags on this run.

---

## 5. Generated output summary

| Path | Role |
|------|------|
| `src/App.tsx` | Phase state machine, random delay, reaction ms calc, false-start alert, best score, play again |
| `src/components/ReactionSignalPanel.tsx` | Red wait panel / green click panel with click handlers |
| `src/components/ReactionRoundControls.tsx` | Start + Play Again buttons |
| `src/components/ReactionScoreTracker.tsx` | Best + current reaction time (ms) |
| `src/components/ReactionResultsPanel.tsx` | Result-phase reaction time display |
| `src/App.tsx` shell | Vite + React entry via `main.tsx`, `index.html`, `package.json` |

---

## 6. Positive observations

- **Routing and v2 context are stable** — correct recipe after Wave 3 routing commit; no v1 fallback on this prompt.
- **DOM-native timing loop is coherent** — simpler state model than reducer-heavy recipes; aligns with Wave 3 checkpoint recommendation.
- **False-start + random delay + ms scoring present** — matches recipe semantics without Pomodoro/stopwatch/productivity drift.
- **Post-output inspector clean** — 0 playability issues on first gate run (contrast with early card-deck baseline).
- **Safety posture unchanged** — no typing, rhythm, medical, dashboard, gambling, or physics patterns in generated source.

---

## 7. Remaining gaps

1. **Keyboard/space input not wired** — prompt emphasizes click; recipe modules include input-response variants but this run is click-only.
2. **Result-phase signal panel UX** — `ReactionSignalPanel` prop type omits `result`; panel shows misleading “Idle” on red during result phase.
3. **False-start UX is alert-based** — no dedicated false-start panel component from recipe catalog (functional but coarse).
4. **LLM variance** — single run; reruns may differ in component split or keyboard support.

---

## 8. Safety/routing observations

- **Routing:** Conservative reaction-time intent gate matched; typing-speed and timer prompts would route elsewhere or fall back per intent tests.
- **Flag behavior:** v2 opt-in only (`HAM_BUILD_REGISTRY_V2_ENABLED`); v1 default preserved when flag unset.
- **Safety:** No Pomodoro/stopwatch, typing/WPM, rhythm/music, medical/clinical assessment, dashboard/analytics, gambling/betting, or physics/collision patterns observed.
- **Scope:** No runtime/API/frontend/Builder Studio/routing/recipe YAML changes required for this review artifact.

---

## 9. Gate decision

**Pass** — routing, v2 context, and core reaction-time gameplay loop meet Wave 3 gate criteria on this single generated run. Minor UX gaps (keyboard input, result-phase panel copy) are acceptable backlog items, not blockers.

---

## 10. Recommendation

1. **Accept `game.reaction-time-challenge` as Wave 3 routed + gated** — schema + routing + this generated baseline are sufficient for planning next workstreams.
2. **Do not enable Build Registry v2 by default** based on this gate alone.
3. **Optional follow-up** — 2–3 reruns to measure LLM variance on keyboard support and false-start panel polish; treat as local evidence, not telemetry.
4. **Keep v1 default** — flag-off behavior unchanged.

---

## 11. References

- [WAVE_3_POST_QUALITY_REPAIR_CHECKPOINT.md](../WAVE_3_POST_QUALITY_REPAIR_CHECKPOINT.md)
- [GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md](../GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md)
- [ROUTING_STRATEGY.md](../ROUTING_STRATEGY.md)
- [STATUS.md](../STATUS.md)
