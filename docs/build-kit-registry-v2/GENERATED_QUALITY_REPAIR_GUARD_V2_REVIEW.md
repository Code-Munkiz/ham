# Generated Quality Repair Guard v2 Review

> **Local/manual generated-output review · Not production telemetry · Guard tightening trial**

**Review date:** 2026-05-26 (UTC)

Prior baseline: [GENERATED_QUALITY_BASELINE_AFTER_REPAIR_GUARD.md](./GENERATED_QUALITY_BASELINE_AFTER_REPAIR_GUARD.md)

---

## 1. What changed

Extended `src/ham/scaffold_quality.py` with lightweight pattern detectors (not a full static analyzer):

| Detector | Code | Purpose |
|----------|------|---------|
| Dispatch vs reducer | `dispatch_reducer_mismatch` | Primary `dispatch({ type })` calls with missing or no-op reducer cases |
| Empty / log-only handlers | `empty_primary_handler` | Primary handlers that only `console.log` or empty `onClick`/`onChange` |
| Stale win/loss checks | `stale_state_win_check` | HP win checks reading closure state right after `setHp` / named `checkWin*` |
| Timer duration | `timer_duration_mismatch` | Prompt mentions 60 seconds but timer code lacks explicit 60s init |
| Existing | `noop_reducer_action`, `stub_placeholder`, `import_export_mismatch` | Unchanged behavior |

`inspect_generated_scaffold_quality()` now accepts optional `plan` for timer checks. `build_scaffold_repair_prompt()` adds wiring/stale-state/timer/loop guidance. `maybe_repair_generated_scaffold()` passes `plan=plan` (no change to `builder_llm_scaffold.py` wiring).

**Preserved:** `HAM_SCAFFOLD_QUALITY_REPAIR=false` opt-out, v1 fallback, no routing/recipe/registry/API/frontend/CI changes.

---

## 2. Tests run

```bash
pytest tests/test_scaffold_quality.py -q
# 15 passed

pytest tests/test_builder_llm_scaffold_registry_manual_smoke.py \
  tests/test_build_registry.py tests/test_build_registry_intent.py \
  tests/test_build_registry_scaffold_context.py \
  tests/test_builder_llm_scaffold_registry_context.py -q
# 435 passed
```

New/updated unit coverage: dispatch mismatch, log-only handler, stale win check, timer 60s mismatch, clean typing sample not overflagged, repair prompt wiring/stale-state/timer language.

---

## 3. Three-sample matrix (repair guard v2 rerun)

Output root: `/tmp/ham-generated-quality-baseline-repaired-v2/`

| Recipe | Route OK | Quality | Inspector (post-output) | vs prior repair guard | Improved? |
|--------|----------|---------|---------------------------|----------------------|-----------|
| `game.typing-speed-racer` (v2) | yes | **Partially playable** | `timer_duration_mismatch` on `App.tsx` | Still elapsed counter (`>= 59`), not `useState(60)` countdown | **Partial** — input/WPM preserved; 60s still approximate |
| `game.resource-management-sim` (v2) | yes | **Partially playable** | clean | Reducer + day/win/loss hooks; allocation still shallow (`COLLECT` spend-food only) | **Stable** |
| `game.card-deck-turn-based` (v2) | yes | **Partially playable** | clean | Deck/hand/discard/effects in `Game.tsx`; **no win/result state** this run; draw/play uses stale `deck`/`hand` closures | **Mixed** — zones/effects kept; win/loss worse than prior stale-closure run |

**Regression check:** None of the three samples regressed to **Shell only**.

**Routing / safety:** All three matched expected v2 recipes (~10.4–10.9k context chars). No gambling/marketplace/backend drift observed in static review.

---

## 4. Per-sample notes

### Typing speed racer

- **Kept:** Prompt list, input wiring, WPM/accuracy/mistakes, finish + results panel.
- **Gap:** Timer uses `elapsedTime` increment ending at `>= 59`, not explicit 60-second countdown init. Repair pass ran but left mismatch (LLM variance + single pass limit).
- **Guard signal:** New `timer_duration_mismatch` detector correctly flags final output.

### Resource management sim

- **Kept:** `useReducer` with `COLLECT` / `WIN` / `LOSE`, day counter, food loss → lose, 10-day win hook.
- **Gap:** Worker assignment / gather / storage upgrade loop still simplified; allocation button only spends food.

### Card deck turn-based

- **Kept:** Shuffled deck, hand panel, discard pile, card effects (damage/heal), turn bar, zone layout.
- **Gap:** No `enemyHp <= 0` win handling in this rerun; `drawCards` / `playCard` read stale `deck`/`hand` from closure (non-reducer pattern — inspector does not flag yet).
- **Note:** Prior repair-guard baseline had win panel with stale-closure bug; this run dropped win state entirely (variance).

---

## 5. Remaining gaps — did they improve?

| Gap | Improved? | Detail |
|-----|-----------|--------|
| Typing 60s timer | **Partially** | Detector + repair prompt now target it; this rerun still elapsed-based |
| Card-deck win/loss state | **No (this run)** | Win logic absent; stale-closure pattern not present to trigger new detector |
| Resource loop depth | **Stable** | Still shallow; no regression |
| Non-reducer wiring bugs | **Partial** | Log-only/empty handlers covered; closure bugs in `useState` handlers still missed |

---

## 6. Recommendation

**Keep and commit** the v2 guard tightening (detectors + tests + repair prompt language). One repair pass remains a variance-limited safety net — not deterministic quality.

**Next (optional, out of this scope):**

1. Re-run card-deck + typing 2–3 times to see if win state / `useState(60)` stabilize under repair prompt.
2. Add a narrow heuristic for `setHand(hand.filter…)` / `deck.slice` immediately after async state set (closure stale reads) if false-positive rate stays low.
3. Do **not** enable Build Registry v2 by default or change routing/recipes for these gaps.

---

## 7. Non-goals confirmed

- No generated app output committed (`/tmp/` only)
- No routing, recipe YAML, registry YAML, API, frontend, Builder Studio, CI, v1 JSON, or template changes
- No commit performed as part of this review task
