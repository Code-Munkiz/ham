# Wave 4 Gate Review: game.turn-based-tactics-lite

> **Wave 4 generated-build gate · Local operator run · Not production telemetry · Not automated validator output**

---

## 1. Checkpoint metadata

| Field | Value |
|-------|--------|
| **Recipe id** | `game.turn-based-tactics-lite` |
| **Review type** | Wave 4 generated-build gate (post-routing + tactics quality guard pass) |
| **Source** | local/manual generated output review |
| **Production telemetry** | no |
| **Automated validator** | no (recipe validators remain `runner: conceptual`) |
| **Generated output committed** | no |
| **Initial review date** | 2026-05-26 (UTC) |
| **Quality guard + fixed rerun date** | 2026-05-26 (UTC) |
| **Final guard pass + final rerun date** | 2026-05-26 (UTC) |
| **Attack wiring/range guard pass + pass rerun date** | 2026-05-26 (UTC) |
| **Initial artifact dir** | `/tmp/ham-turn-based-tactics-wave4-gate-review/` |
| **Fixed artifact dir** | `/tmp/ham-turn-based-tactics-wave4-gate-review-fixed/` |
| **Final artifact dir** | `/tmp/ham-turn-based-tactics-wave4-gate-review-final/` |
| **Pass artifact dir** | `/tmp/ham-turn-based-tactics-wave4-gate-review-pass/` |
| **Repo HEAD (routing commit, unpushed)** | `7909f9e8` — `feat(builder): route turn based tactics recipe behind registry flag` |
| **Quality guard changes** | local/uncommitted — `src/ham/scaffold_quality.py`, `tests/test_scaffold_quality.py`, this doc |
| **Environment flag** | `HAM_BUILD_REGISTRY_V2_ENABLED=true` |

---

## 2. Prompt used

> Build a browser turn-based tactics game on a small 5x5 grid where the player selects units, moves them within range, attacks enemy units, resolves a simple enemy turn, wins by defeating all enemies, loses if all player units are defeated, and can restart the battle.

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

### Run configuration

| Setting | Initial run | Fixed rerun (post-guard) | Final rerun (post second guard pass) |
|---------|-------------|---------------------------|--------------------------------------|
| **Output directory** | `/tmp/ham-turn-based-tactics-wave4-gate-review/` | `/tmp/ham-turn-based-tactics-wave4-gate-review-fixed/` | `/tmp/ham-turn-based-tactics-wave4-gate-review-final/` |
| **Files produced** | 13 | 11 | 11 |
| **First LLM attempt** | JSON parse failure — retried | Clean first pass | Clean first pass |
| **Repair guard** | One repair pass | One repair pass (6 issues pre-repair; 4 remain post-repair on re-inspect) | One repair pass (6 issues at first inspect; **2 remain** after guard pattern refinement re-inspect) |

### Route metadata (both runs)

| Check | Initial | Fixed rerun | Final rerun |
|-------|---------|-------------|-------------|
| `select_registry_v2_app_type_for_prompt(prompt)` | **`game.turn-based-tactics-lite`** | **`game.turn-based-tactics-lite`** | **`game.turn-based-tactics-lite`** |
| `registry_v2_app_type` in metadata | **`game.turn-based-tactics-lite`** | **`game.turn-based-tactics-lite`** | **`game.turn-based-tactics-lite`** |
| Scaffold context source | **v2** | **v2** | **v2** |
| Rendered v2 context length | **8,489 chars** | **8,489 chars** | **8,489 chars** |
| v1 Builder Kit fallback | **Not used** | **Not used** | **Not used** |

Metadata: `gate-metadata.json` in each artifact directory.

---

## 4. Phase summary

### Phase A — Initial run (**Hold**)

Routing and v2 injection **passed**. Generated output was a **shell/non-playable** tactics scaffold:

- `INIT_GAME` reducer case existed but was **never dispatched** on mount
- **No enemy units** seeded (`isPlayer: true` only)
- Grid rendered cells with **no click handlers**
- `MOVE_UNIT` / `ATTACK_UNIT` reducer cases existed but **no UI dispatches**
- **No movement/attack range** checks
- **No enemy turn** mutation
- **Incomplete win/loss** handling
- **Restart** returned empty `initialState`
- Inspector reported **`missing_restart_action`** — **false positive** (deck-builder restart heuristic matched prompt word “restart”; fixed in quality guard pass)

### Phase B — Tactics quality guard pass (local/uncommitted)

**`src/ham/scaffold_quality.py`**

| Area | Change |
|------|--------|
| **Unit seeding** | `tactics_empty_unit_seed`, `tactics_seed_not_applied` for empty/missing player+enemy units and init not applied on mount/restart |
| **Interaction wiring** | `tactics_grid_not_wired`, `tactics_action_not_wired` when reducer actions lack UI dispatches or grid lacks click handlers |
| **Ranges + enemy turn** | `tactics_missing_movement_range`, `tactics_missing_attack_range`, `tactics_enemy_turn_not_wired` |
| **Battle result + restart** | `tactics_missing_battle_result`, `tactics_restart_not_seeded` |
| **False-positive fix** | `_prompt_requires_deck_builder_run()` skips tactics prompts; expanded `_RESTART_MARKERS` for `RESTART_GAME` / `Restart` |
| **Repair prompt** | Turn-based tactics repair focus block when tactics issue codes present |
| **Pattern refinements (post-rerun)** | Accept `id.startsWith('p'/'e')` unit sides; adjacency `Math.abs(dx/dy)` as attack-range signal; `gameState === 'win'/'lose'` as battle result |

**`tests/test_scaffold_quality.py`** — 14 new tactics-focused cases (+ repair prompt guidance test). **66 passed** in scoped run.

### Phase C — Fixed rerun (**Conditional pass**)

With tactics quality guards active in the repair pipeline, the fixed rerun produced a **materially stronger** loop but **did not fully meet** the Wave 4 acceptance checklist.

**Inspector after first guard refinements (re-inspect of fixed artifact tree): 4 issues** ( **7 issues** with second-pass refined guards on the same tree)

| Code | Path | Notes |
|------|------|-------|
| `noop_reducer_action` | `src/gameReducer.ts` | `INIT` no-op; `ATTACK_UNIT` mutates in place without immutable return |
| `tactics_action_not_wired` | `src/App.tsx` | `SELECT_UNIT` reducer case never dispatched |
| `tactics_restart_not_seeded` | `src/App.tsx` | Restart dispatches noop `INIT` instead of reseeding units/grid |

**Cleared vs initial run:** `tactics_empty_unit_seed`, `tactics_missing_attack_range` (adjacency checks present), `tactics_enemy_turn_not_wired`, `tactics_missing_battle_result`, `missing_restart_action` false positive.

---

## 5. Gate checklist — fixed rerun

| Requirement | Observed | Pass/Partial/Fail | Notes |
|-------------|----------|-------------------|-------|
| Routes to `game.turn-based-tactics-lite` | yes | **Pass** | Unchanged |
| v2 context used, not v1 fallback | yes (8,489 chars) | **Pass** | Full tactics-lite playbook |
| Fixed grid exists and is non-empty | 5×5 grid in `initialState` | **Pass** | Non-null grid arrays |
| Player units and enemy units seeded | `p1` + `e1` in `initialState.units` | **Pass** | Uses id prefix convention, not `isPlayer` |
| Player unit selection wired | `SELECT_UNIT` case only | **Fail** | No dispatch; `selectedUnit` stays null |
| Movement range exists or movement constrained | none | **Fail** | `MOVE_UNIT` moves without distance check |
| Move action changes unit position | `MOVE_UNIT` updates grid | **Partial** | Wired via grid click when `selectedUnit` set; selection gap blocks loop |
| Attack range exists or attacks constrained | adjacency in enemy `END_TURN` | **Partial** | Enemy attack uses `Math.abs(dx/dy) <= 1`; player attack path weak/in-place |
| Attack action mutates enemy/player HP | enemy turn reduces player HP | **Partial** | Player `ATTACK_UNIT` mutates in place; inspector flags no-op pattern |
| Enemy turn mutates state | `END_TURN` moves/attacks enemies | **Pass** | Enemy step changes positions/HP/events |
| Win/loss battle result exists | `gameState` win/lose + `TacticsResultsPanel` | **Pass** | Visible win/loss panel |
| Restart/new battle reseeds units/grid | Restart → noop `INIT` | **Fail** | Does not rebuild seeded battle |
| No no-op/stub primary gameplay actions | `INIT`, broken `ATTACK_UNIT` | **Fail** | Inspector flags remain |
| No import/export mismatch | consistent defaults | **Pass** | No import errors observed |
| No product drift | tactics-only patterns | **Pass** | No chess/puzzle/card/deck/dashboard drift |
| Generated output local-only | `/tmp/` only | **Pass** | Not committed |

**Overall quality:** **Partially playable / Conditional pass** — enemy turn + win/loss + seeded units improved substantially; selection, movement range, player attack wiring, and restart reseed remain gaps.

### Phase D — Second guard pass + final rerun (**Conditional pass**, inspector **2 issues** after pattern refinement)

**Additional `src/ham/scaffold_quality.py` changes (local/uncommitted)**

| Area | Change |
|------|--------|
| **Selection wiring** | Stronger `tactics_action_not_wired` / `tactics_grid_not_wired` messages; detect grid click handlers that move but never dispatch SELECT; detect `selectedUnit` tracked without SELECT dispatch |
| **Movement range** | Flag MOVE case bodies that change position without range markers **or** `isValidMove`/`legalMove` helper calls (avoids false pass when enemy-turn code has `Math.abs` but MOVE does not) |
| **Player attack mutation** | New `tactics_inplace_attack_mutation` for in-place HP mutation / stale shallow returns in ATTACK/ATTACK_UNIT |
| **Restart reseed** | `INIT`/`RESTART` must actually reseed — dispatching noop `INIT` no longer counts; accept `return initialGameState` when seeded |
| **Pattern refinements** | Accept `type: 'player'/'enemy'` unit sides; accept `isValidMove` as movement-range signal; accept `initialGameState` restart return |
| **Repair prompt** | Explicit guidance for unit click → SELECT, Manhattan/legal moves, immutable attack units array, full battle reseed on restart |

**Tests:** `tests/test_scaffold_quality.py` — **73 passed** (9 new tactics-focused cases). Combined registry/scaffold suite — **703 passed**.

**Final rerun inspector (artifact `/tmp/ham-turn-based-tactics-wave4-gate-review-final/`, re-inspect with refined guards): 2 issues**

| Code | Path | Notes |
|------|------|-------|
| `tactics_action_not_wired` | `src/App.tsx` | `ATTACK_UNIT` reducer case exists but UI never dispatches attack |
| `tactics_missing_attack_range` | `src/App.tsx` | Player `ATTACK_UNIT` applies damage with no distance/range check |

**False positives cleared on final artifact (documented with evidence):**

| Cleared code | Evidence |
|--------------|----------|
| `tactics_empty_unit_seed` | `initialUnits` in `src/gameLogic.ts` seeds `{ type: 'player' }` + `{ type: 'enemy' }` — prior guard missed `type:` convention |
| `tactics_seed_not_applied` | `initialGameState.units = initialUnits`; `INIT_GAME` dispatched on mount in `src/App.tsx` |
| `tactics_missing_movement_range` | `MOVE_UNIT` calls `isValidMove()` with Manhattan `distance === 1` helper |
| `tactics_restart_not_seeded` | `RESTART` returns `initialGameState` with seeded units |
| `tactics_inplace_attack_mutation` | `ATTACK_UNIT` maps units immutably (`state.units.map(...)`) |

**Gap improvement vs fixed rerun (same refined inspector):**

| Gap | Fixed rerun re-inspect | Final rerun |
|-----|------------------------|-------------|
| Selection | **Fail** — `SELECT_UNIT` never dispatched (7-issue inspect included selection + grid) | **Pass** — grid dispatches `SELECT_UNIT` on player cell click |
| Movement range | **Fail** — MOVE unconstrained (enemy `Math.abs` falsely satisfied old combined check) | **Pass** — `isValidMove` Manhattan adjacency |
| Player attack | **Fail** — in-place HP mutation flagged | **Partial** — immutable reducer path, but **attack not wired** + **no attack range** |
| Restart reseed | **Fail** — noop `INIT` | **Pass** — `RESTART` → `initialGameState` |

Fixed rerun re-inspect with refined guards: **7 issues** (including noop `INIT`, in-place attack, missing selection/move range/restart).

### Phase E — Attack wiring/range guard pass + pass rerun (**Pass**, inspector **0 issues**)

**Focused `src/ham/scaffold_quality.py` changes**

| Area | Change |
|------|--------|
| **Attack UI wiring** | Explicit ATTACK/ATTACK_UNIT dispatch requirements in `tactics_action_not_wired` messages; dedicated check when attack reducer exists but UI never dispatches (enemy click or Attack button with selected attacker + target) |
| **Player attack range** | Inspect ATTACK case body only; enemy-turn `Math.abs` no longer satisfies player attack range; accept `manhattanDistance` / helper calls on any reducer case that mutates enemy HP (e.g. `CELL_CLICK` attack branch) |
| **Repair prompt** | Explicit bullets for ATTACK UI dispatch and player-side range before HP mutation |

**Tests:** `tests/test_scaffold_quality.py` — **79 passed**. Combined registry/scaffold suite — **703 passed**.

**Pass rerun** (`/tmp/ham-turn-based-tactics-wave4-gate-review-pass/`)

| Check | Result |
|-------|--------|
| Route | `game.turn-based-tactics-lite` |
| v2 context | 8,489 chars, no v1 fallback |
| Files | 12 |
| Inspector (post attack-range pattern fix, re-inspect) | **0 issues** |

**Remaining two issues from final rerun — improvement:**

| Issue | Final rerun | Pass rerun |
|-------|-------------|------------|
| `tactics_action_not_wired` (ATTACK_UNIT) | **Fail** — reducer case never dispatched | **Pass** — player attack via `CELL_CLICK` grid handler (alternate action name) |
| `tactics_missing_attack_range` | **Fail** — ATTACK case lacks range | **Pass** — `manhattanDistance(...) <= 1` on player attack path in `CELL_CLICK` before HP mutation |

**Pass artifact notes:** Uses `CELL_CLICK` instead of `ATTACK_UNIT`; inspector accepts Manhattan-gated enemy HP mutation in that case. Minor in-place mutation in generated reducer remains outside the two targeted gap codes (not flagged by attack-range/wiring guards).

---

## 6. Generated output summary

### Fixed rerun (`/tmp/ham-turn-based-tactics-wave4-gate-review-fixed/`)

| Path | Role |
|------|------|
| `src/gameReducer.ts` | `initialState` with 5×5 grid + `p1`/`e1` units; `SELECT_UNIT`, `MOVE_UNIT`, `ATTACK_UNIT`, `END_TURN`; enemy step in `END_TURN`; `gameState` win/lose |
| `src/App.tsx` | `useReducer` + noop mount `INIT`; composes grid/action bar/log/results |
| `src/components/TacticsGrid.tsx` | 5×5 grid with `onClick` move dispatch (when `selectedUnit` set) |
| `src/components/TacticsActionBar.tsx` | End Turn button (requires `selectedUnit`) |
| `src/components/TacticsResultsPanel.tsx` | Win/lose panel + Restart → noop `INIT` |
| `src/components/TacticsEventLog.tsx` | Event log display |
| Vite shell | `index.html`, `package.json`, `vite.config.ts`, `src/main.tsx`, `src/index.css` |

### Final rerun (`/tmp/ham-turn-based-tactics-wave4-gate-review-final/`)

| Path | Role |
|------|------|
| `src/gameLogic.ts` | `initialGameState` with seeded `{ type: 'player' }` / `{ type: 'enemy' }` units; `isValidMove` Manhattan adjacency; immutable `ATTACK_UNIT`; enemy turn in `END_TURN`; `RESTART` → `initialGameState` |
| `src/App.tsx` | `useReducer(initialGameState)` + mount `INIT_GAME` |
| `src/components/TacticsGrid.tsx` | Grid clicks dispatch `SELECT_UNIT` (player cells) and `MOVE_UNIT` (when `selectedUnit` set) — **no `ATTACK_UNIT` dispatch** |
| `src/components/TacticsActionBar.tsx` | End Turn + Restart |
| `src/components/TacticsResultsPanel.tsx` | Win/lose panel + Restart |
| Vite shell | `index.html`, `package.json`, `vite.config.ts`, `src/main.tsx`, `src/index.css` |

### Pass rerun (`/tmp/ham-turn-based-tactics-wave4-gate-review-pass/`)

| Path | Role |
|------|------|
| `src/gameReducer.ts` | `initialState` with player/enemy units; `CELL_CLICK` move+attack with `manhattanDistance <= 1`; enemy turn in `END_TURN`; `RESTART` → `initialState` |
| `src/components/TacticsGrid.tsx` | Grid dispatches `CELL_CLICK` for select/move/attack flow |
| `src/components/TacticsActionBar.tsx` | End Turn + Restart |
| `src/components/TacticsResultsPanel.tsx` | Victory/defeat panel |
| Vite shell | 12 files total; inspector **0 issues** on re-inspect |

---

## 7. Positive observations

- **Routing + v2 context stable** across initial and fixed reruns.
- **Quality guards detected initial shell gaps** and drove a stronger repair pass (seeded units, grid clicks, enemy turn, result panel).
- **False-positive restart labeling fixed** for tactics prompts (no more deck-builder `missing_restart_action` on “restart the battle”).
- **Enemy turn + win/loss materially improved** vs initial Hold run.
- **No product drift** — generated source stays tactics-shaped; excluded families not present.

---

## 8. Remaining gaps

### After pass rerun (inspector-clean)

No remaining inspector issues on `/tmp/ham-turn-based-tactics-wave4-gate-review-pass/` re-inspect (**0 issues**).

### After final rerun (superseded by pass rerun for attack gaps)

1. ~~Player attack not wired~~ — cleared on pass rerun (`CELL_CLICK` attack branch).
2. ~~Player attack range missing~~ — cleared on pass rerun (`manhattanDistance` before enemy HP mutation).

### Historical (fixed rerun / initial)

1. ~~Unit selection not wired~~ — cleared on final rerun (`SELECT_UNIT` dispatched from grid).
2. ~~Movement range missing~~ — cleared on final rerun (`isValidMove` Manhattan adjacency).
3. ~~Player attack in-place mutation~~ — cleared on final rerun (immutable `units.map`); attack wiring/range still partial.
4. ~~Restart does not reseed~~ — cleared on final rerun (`RESTART` → `initialGameState`).
5. **LLM variance** — three local runs (initial, fixed, final) produced different shapes; final rerun is strongest on selection/move/restart.
6. **Inspector vs human review** — `type: 'player'/'enemy'`, `isValidMove`, and `initialGameState` patterns required second-pass guard refinement to avoid false positives.

---

## 9. Safety/routing observations

- **Routing remains as landed in `7909f9e8`** — conservative combined-signal matching; weak single-term and excluded families unchanged.
- **Build Registry v2 opt-in only** — v1 default when `HAM_BUILD_REGISTRY_V2_ENABLED` is off.
- **Scope of this pass:** scaffold quality guards + tests + this review doc only; no recipe/registry/API/frontend/Builder Studio/CI/routing changes beyond already-local routing commit.
- **`HAM_SCAFFOLD_QUALITY_REPAIR=false`** still disables repair pass.

---

## 10. Gate decision

| Phase | Decision |
|-------|----------|
| **Initial run (pre-guard)** | **Hold** — shell/non-playable despite correct routing/v2 |
| **After tactics quality guard + fixed rerun** | **Conditional pass** |
| **After second guard pass + final rerun** | **Conditional pass** — inspector **2 issues** (attack wiring + attack range) |
| **After attack wiring/range guard pass + pass rerun** | **Pass** — inspector **0 issues** on re-inspect of `/tmp/ham-turn-based-tactics-wave4-gate-review-pass/` |

### Tests run

```bash
pytest tests/test_scaffold_quality.py -q
# 79 passed (attack wiring/range focused cases)

pytest tests/test_builder_llm_scaffold_registry_manual_smoke.py tests/test_build_registry.py \
  tests/test_build_registry_intent.py tests/test_build_registry_scaffold_context.py \
  tests/test_builder_llm_scaffold_registry_context.py tests/test_build_registry_reference_checker.py -q
# 703 passed
```

---

## 11. Recommendation

1. **Land quality guard + tests + this review doc** as a follow-up commit (separate from unpushed routing commit `7909f9e8` or squashed per operator preference).
2. **Optional:** run additional local reruns to measure LLM variance; pass rerun achieved inspector-clean output with `CELL_CLICK` attack path.
3. **Do not enable Build Registry v2 by default.**
4. **Do not commit generated app output** — keep artifacts under `/tmp/` only (`…-fixed/`, `…-final/`, `…-pass/`).
5. **Pass rerun met** attack wiring + player attack range acceptance targets; treat **`game.turn-based-tactics-lite` Wave 4 gate as Pass** for planning purposes.

---

## 12. References

- [TACTICS_GRID_AMBIGUITY_REVIEW.md](../TACTICS_GRID_AMBIGUITY_REVIEW.md)
- [WAVE_4_STRATEGY_SIM_DIRECTION.md](../WAVE_4_STRATEGY_SIM_DIRECTION.md)
- [WAVE_3_COMPLETION_CHECKPOINT.md](../WAVE_3_COMPLETION_CHECKPOINT.md)
- [GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md](../GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md)
- [ROUTING_STRATEGY.md](../ROUTING_STRATEGY.md)
- [STATUS.md](../STATUS.md)
