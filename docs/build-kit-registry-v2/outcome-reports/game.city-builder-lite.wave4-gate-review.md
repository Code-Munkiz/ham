# Wave 4 Gate Review: game.city-builder-lite

> **Wave 4 generated-build gate · Local operator run · Not production telemetry · Not automated validator output**

---

## 1. Checkpoint metadata

| Field | Value |
|-------|--------|
| **Recipe id** | `game.city-builder-lite` |
| **Review type** | Wave 4 generated-build gate (post-routing + city-builder quality guard passes) |
| **Source** | local/manual generated output review |
| **Production telemetry** | no |
| **Automated validator** | no (recipe validators remain `runner: conceptual`) |
| **Generated output committed** | no |
| **Initial review date** | 2026-05-26 (UTC) |
| **First guard pass date** | 2026-05-26 (UTC) |
| **Happiness/production guard pass date** | 2026-05-26 (UTC) |
| **Final happiness derivation pass date** | 2026-05-26 (UTC) |
| **Initial artifact dir** | `/tmp/ham-city-builder-wave4-gate-review/` |
| **Fixed artifact dir** | `/tmp/ham-city-builder-wave4-gate-review-fixed/` |
| **Pass artifact dir** | `/tmp/ham-city-builder-wave4-gate-review-pass/` |
| **Final artifact dir** | `/tmp/ham-city-builder-wave4-gate-review-final/` |
| **Repo HEAD (routing commit, unpushed)** | `62d6bdc6` — `feat(builder): route city builder recipe behind registry flag` |
| **Quality guard changes** | local/uncommitted — `src/ham/scaffold_quality.py`, `tests/test_scaffold_quality.py`, this doc |
| **Environment flag** | `HAM_BUILD_REGISTRY_V2_ENABLED=true` |

---

## 2. Prompt used

> Build a browser city-building game on a small 5x5 grid where the player places houses, farms, wells, and power buildings, advances days to produce food and coins, grows population and happiness, wins by reaching a population goal by day 10, loses if food runs out, and can restart the city.

---

## 3. Generation path

### APIs used

| Component | Path / function |
|-----------|-----------------|
| Intent routing | `enrich_plan_metadata_with_registry_v2`, `select_registry_v2_app_type_for_prompt` |
| Scaffold context | `resolve_scaffold_context` |
| LLM scaffold | `generate_scaffold()` in `src/ham/builder_llm_scaffold.py` |
| Post-output inspect | `inspect_generated_scaffold_quality()` in `src/ham/scaffold_quality.py` |
| Repair guard | `maybe_repair_generated_scaffold()` (default enabled; `HAM_SCAFFOLD_QUALITY_REPAIR=false` preserved) |

No new repo script. Operator Python invocations of established public APIs only (local `/tmp/` runners).

### Route metadata (all runs)

| Check | Result |
|-------|--------|
| `select_registry_v2_app_type_for_prompt(prompt)` | **`game.city-builder-lite`** |
| `registry_v2_app_type` in metadata | **`game.city-builder-lite`** |
| Scaffold context source | **v2** |
| Rendered v2 context length | **8,928 chars** |
| v1 Builder Kit fallback | **Not used** |

---

## 4. Phase summary

### Phase A — Initial run (**Hold**)

Routing and v2 injection **passed**. Generated output was shell/partial (hardcoded house, no palette, static population/happiness, no population-goal win). Inspector reported **0 issues** because city-builder guards did not exist yet.

**Re-inspect with first guard pass:** 6 issues on initial artifact (`city_missing_building_palette`, `city_single_building_only`, `city_invalid_placement_not_blocked`, `city_population_not_wired`, `city_happiness_not_wired`, `city_goal_not_wired`).

### Phase B — First guard pass (**Conditional pass** on fixed rerun)

Added city-builder palette, placement, production, population/happiness, goal/fail/restart detectors + repair focus block.

**Fixed rerun** (`/tmp/ham-city-builder-wave4-gate-review-fixed/`): repair JSON parse failed; kept first-pass output (11 files). Materially improved palette/placement/goal/restart, but human review found happiness absent and production not grid-derived. **Re-inspect with first guards:** 0 issues (blind spots for useState `endDay()` and absent happiness).

### Phase C — Happiness/production guard strengthening (this pass)

**`src/ham/scaffold_quality.py`**

| Area | Change |
|------|--------|
| **Happiness required** | Flag when prompt requests happiness but field/counter absent, static, or not mutated from wells/power/food/buildings/grid on day ticks |
| **Grid-derived production** | Inspect reducer `END_DAY`, useState `endDay()`, and delegated helpers (`produceDayResults`); reject population-only food formulas without grid counts |
| **Unused catalogs** | Flag `BUILDING_PRODUCTION` / catalog constants not applied on day tick |
| **UI placement guard** | Accept grid click guards + invalid-placement feedback even when reducer case lacks occupied-cell check |
| **Helper expansion** | Follow `return produceDayResults(state)` into helper bodies for production/population/happiness checks |
| **Repair prompt** | JSON-only output reminder; explicit happiness canonical state + grid-derived food/coins/production guidance |

**`tests/test_scaffold_quality.py`** — 8 additional focused cases (102 total scaffold-quality tests).

**Pass rerun** (`/tmp/ham-city-builder-wave4-gate-review-pass/`):

| Setting | Value |
|---------|--------|
| Files | 6 |
| First LLM attempt | JSON parse failure — retried |
| Repair guard | Ran; 4 issues remained immediately post-repair |
| **Re-inspect with strengthened guards** | **1 issue** — `city_happiness_not_wired` |

**Fixed rerun re-inspect with strengthened guards:** **2 issues** — `city_production_not_wired` (population-only `endDay` food drain), `city_happiness_not_wired` (happiness field absent).

### Phase D — Final happiness derivation guard pass (**Pass** on happiness; final rerun)

**`src/ham/scaffold_quality.py` (happiness-only tightening)**

| Area | Change |
|------|--------|
| **Hardcoded delta detection** | Flag `happinessChange = 1`, `happiness: state.happiness + 1`, `setHappiness(happiness + 1)`; allow derived intermediates (`happinessDelta` from wells/food/grid) |
| **Derived happiness acceptance** | Accept reducer `happiness:` updates and `newHappiness`/`happinessDelta` tied to grid wells/power/farms, food shortage, or population/resource pressure |
| **Issue message** | Explicit that happiness must be canonical, visible, tick-mutated, and grid/building/resource-derived — not static or hardcoded |
| **Repair prompt (city-builder)** | General block: wells/power improve happiness; food shortage and housing pressure lower it; no `happinessChange = 1` |
| **Repair prompt (happiness issue)** | Dedicated block when `city_happiness_not_wired`: replace hardcoded deltas; count wells/power from grid; factor food/resource/population pressure; compute next happiness with day production; JSON-only output |

**`tests/test_scaffold_quality.py`** — 5 additional happiness-focused cases (107 total scaffold-quality tests).

**Pass artifact re-inspect (final guards):** still **1 issue** — `city_happiness_not_wired` (`happinessChange = 1` in `produceDayResults`) — confirms guard catches hardcoded delta.

**Final rerun** (`/tmp/ham-city-builder-wave4-gate-review-final/`):

| Setting | Value |
|---------|--------|
| Files | 3 (`src/App.tsx`, `src/components/CityGrid.tsx`, `src/components/ResourceStatusPanel.tsx`) |
| Repair guard | Ran; 1 issue remained post-repair (`city_restart_not_seeded`) |
| **Re-inspect with final guards** | **0 happiness issues** — `city_happiness_not_wired` cleared |
| Happiness derivation | **Pass** — `endDay` computes `newHappiness` from well count × 5 minus food-shortage penalty |
| Remaining inspector issue | `city_restart_not_seeded` — **documented false positive** (see §6) |

---

## 5. Gate checklist — final rerun (re-inspect with final guards)

| Requirement | Observed | Pass/Partial/Fail | Notes |
|-------------|----------|-------------------|-------|
| Routes to `game.city-builder-lite` | yes | **Pass** | Unchanged |
| v2 context used | yes (8,928 chars) | **Pass** | |
| Fixed city grid | 5×5 in `initialState.grid` | **Pass** | |
| Building palette | `selectedBuilding` + palette in `CityGrid` | **Partial** | Minimal 3-file scaffold |
| Placement uses selected type | `placeBuilding` uses `selectedBuilding` | **Pass** | |
| Invalid placement blocked | not fully verified | **Partial** | No occupied-cell guard in final artifact |
| Resource counters | food/coins/population/happiness/day | **Pass** | |
| Day/turn production from grid | farms/houses counted on `endDay` | **Pass** | |
| Food/coins from building effects | farms drain food; houses grow population | **Pass** | |
| Population mutates | houses → population on `endDay` | **Pass** | |
| Happiness mutates from buildings/resources | wells boost; low food penalizes | **Pass** | No hardcoded `happinessChange = 1` |
| Goal/win | population ≥ 20 by day 10 | **Partial** | Threshold differs from prompt (20 vs typical 10) |
| Food-loss fail | `newResources.food < 0` | **Pass** | |
| Result state | `hasWon` / `hasLost` + results panel | **Pass** | |
| Restart reseed | `setState(initialState)` | **Pass (human)** / **Fail (inspector)** | Inspector false positive — see §6 |
| Inspector happiness | 0 `city_happiness_not_wired` | **Pass** | Happiness gate closed |
| Inspector overall | 1 issue (`city_restart_not_seeded`) | **Partial** | Documented false positive |
| Product drift | city-builder shape | **Pass** | |

### Pass rerun checklist (prior artifact — for comparison)

| Requirement | Observed | Pass/Partial/Fail | Notes |
|-------------|----------|-------------------|-------|
| Routes to `game.city-builder-lite` | yes | **Pass** | Unchanged |
| v2 context used | yes (8,928 chars) | **Pass** | |
| Fixed city grid | 5×5 in `cityState` | **Pass** | |
| Building palette | `selectedBuilding` default + palette path | **Partial** | Palette wiring split across provider/components |
| Placement uses selected type | reducer uses `state.selectedBuilding` | **Pass** | |
| Invalid placement blocked | UI `!cell` guard + alert | **Pass** | Accepted via UI guard |
| Resource counters | food/coins/population/happiness | **Pass** | |
| Day/turn production from grid | `produceDayResults` counts farms/houses | **Pass** | Grid-derived food/coins/population |
| Food/coins from building effects | farms → food, houses → population | **Pass** | |
| Population mutates | `newPopulation` from house count | **Pass** | |
| Happiness mutates from buildings | `happinessChange = 1` constant | **Fail** | Superseded by final rerun |
| Goal/win | population ≥ 10 by day 10 | **Pass** | |
| Food-loss fail | `newFood <= 0` | **Pass** | |
| Result state | win/loss via `gameOver`/`win` | **Pass** | |
| Restart reseed | provider reset path | **Partial** | Not fully verified in pass artifact |
| Inspector (final guards) | 1 issue | **Partial** | `city_happiness_not_wired` — hardcoded `happinessChange = 1` |
| Product drift | city-builder shape | **Pass** | |

---

## 6. Happiness / production gap improvement

| Gap | Initial | Fixed (1st guard) | Fixed re-inspect (final guards) | Pass rerun (final guards) | Final rerun (happiness guards) |
|-----|---------|-------------------|----------------------------------|----------------------------|--------------------------------|
| Happiness absent | Fail | Fail | Fail (no field) | **Partial** — field present, hardcoded +1 | **Pass** — derived from wells + food pressure |
| Grid-derived production | Fail | Partial (unused farms) | Fail (population-only food) | **Pass** — `produceDayResults` counts grid | **Pass** — `endDay` counts farms/houses |
| Inspector happiness | 0 issues (no guard) | 0 on fixed (blind spot) | 2 issues | 1 issue (`city_happiness_not_wired`) | **0 happiness issues** |

**Pass rerun remaining issue (superseded):** `src/state/cityState.tsx` `produceDayResults` sets `const happinessChange = 1` — legitimate `city_happiness_not_wired`; final guards correctly flag it on re-inspect.

**Final rerun happiness evidence** (`/tmp/ham-city-builder-wave4-gate-review-final/src/App.tsx`):

```javascript
const newHappiness = Math.max(
  0,
  state.happiness
    + (state.grid.flat().filter(b => b === 'well').length * 5)
    - (state.resources.food < 5 ? 10 : 0)
);
```

Wells improve happiness; food shortage lowers it — no hardcoded `happinessChange = 1`.

**Final rerun restart inspector note (false positive):** `restartGame = () => setState(initialState)` resets the full `GameState` object (grid, resources, day, population, happiness, win/loss). `_restart_reseeds_city()` only accepts reducer `RESTART` cases or `setGrid`/`setResources`/`setDay(1)` patterns, so it misses monolithic `setState(initialState)`. Human review: restart **does** reseed; inspector miss is out of scope for this happiness-only pass.

---

## 7. Tests run

```bash
pytest tests/test_scaffold_quality.py -q
# 107 passed (final happiness derivation pass)

pytest tests/test_builder_llm_scaffold_registry_manual_smoke.py tests/test_build_registry.py \
  tests/test_build_registry_intent.py tests/test_build_registry_scaffold_context.py \
  tests/test_builder_llm_scaffold_registry_context.py tests/test_build_registry_reference_checker.py -q
# 771 passed
```

Focused happiness tests added/updated:

- hardcoded `happinessChange = 1` flagged
- `setHappiness(happiness + 1)` without grid/resource dependency flagged
- happiness from wells/power grid counts accepted
- happiness from food shortage/resource pressure accepted
- repair prompt includes happiness derivation + no hardcoded delta guidance

---

## 8. Safety/routing observations

- **Routing landed in `62d6bdc6`** — unchanged by guard work.
- **Build Registry v2 opt-in only** — v1 default when flag off.
- **Scope:** scaffold quality guards + tests + this review doc only.
- **Generated artifacts remain under `/tmp/`** — not committed.

---

## 9. Gate decision

| Phase | Decision |
|-------|----------|
| **Initial run** | **Hold** |
| **First guard pass + fixed rerun** | **Conditional pass** |
| **Happiness/production guard pass + pass rerun** | **Conditional pass** — inspector **1 issue** (`city_happiness_not_wired` hardcoded delta) |
| **Final happiness derivation pass + final rerun** | **Pass** (happiness gate closed) — `city_happiness_not_wired` **0** on final artifact; `city_restart_not_seeded` documented false positive |

---

## 10. Recommendation

1. **Land quality guard + tests + this review doc** as a follow-up commit (separate from routing commit `62d6bdc6`).
2. **Happiness gate is closed** — guards + repair prompts now require grid/building/resource-derived happiness; final rerun confirms derived `newHappiness`.
3. **Optional follow-up (out of scope here):** broaden `_restart_reseeds_city()` to accept `setState(initialState)` / `setState(initialGameState)` so monolithic restarts are not false positives.
4. **Do not enable Build Registry v2 by default.**
5. **Do not commit generated app output.**
6. **Treat routing as Pass; generated happiness quality as Pass** on final rerun.

---

## 11. References

- [CITY_BUILDER_LITE_READINESS_REVIEW.md](../CITY_BUILDER_LITE_READINESS_REVIEW.md)
- [GAMEPLAY_QUALITY_PRINCIPLES.md](../GAMEPLAY_QUALITY_PRINCIPLES.md)
- [WAVE_4_STRATEGY_SIM_DIRECTION.md](../WAVE_4_STRATEGY_SIM_DIRECTION.md)
- [WAVE_3_COMPLETION_CHECKPOINT.md](../WAVE_3_COMPLETION_CHECKPOINT.md)
- [GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md](../GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md)
- [ROUTING_STRATEGY.md](../ROUTING_STRATEGY.md)
- [STATUS.md](../STATUS.md)
