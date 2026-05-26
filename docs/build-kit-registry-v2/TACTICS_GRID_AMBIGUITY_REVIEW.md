# Tactics Grid Ambiguity Review

> **Readiness/ambiguity gate only · Not recipe approval · Not routing approval · Not implementation authorization**

Ambiguity and routing-risk review before authoring a potential **`game.turn-based-tactics-lite`** Game Pack recipe. This document evaluates prompt boundaries, scope limits, generated-quality expectations, and sibling-recipe collisions. It does **not** add a recipe, routing, templates, or runtime changes.

**Review date:** 2026-05-26 (UTC)  
**Baseline:** `origin/main` at `5426a2ef` — fourteen recipes, 323 indexed modules, all routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`, reference checker **0 errors / 0 warnings**.

For Wave 4 direction see [WAVE_4_STRATEGY_SIM_DIRECTION.md](WAVE_4_STRATEGY_SIM_DIRECTION.md). For routing policy see [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md).

---

## 1. Executive summary

**`game.turn-based-tactics-lite` is a plausible Wave 4 candidate** — the natural next strategy/sim lane after puzzle-grid, resource-management, and card/deck systems proved the schema-first rhythm at 323 modules.

**It should not be authored until ambiguity, scope, routing posture, and generated-quality risks are documented.** This review satisfies the ambiguity gate called for in [WAVE_4_STRATEGY_SIM_DIRECTION.md](WAVE_4_STRATEGY_SIM_DIRECTION.md).

**No recipe or routing should be added from this review alone.**

**Recommended posture if Wave 4 proceeds:** author **schema-only** next, keep scope small (fixed grid, few units, simple Manhattan move/attack), **defer routing** until schema validates and human approval follows [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md), then run a **`/tmp/` generated gate review** before declaring the recipe complete.

---

## 2. Current baseline

| Dimension | State |
|-----------|--------|
| **Recipes** | 14 |
| **Indexed modules** | 323 |
| **Routing** | All 14 recipes route narrowly behind `HAM_BUILD_REGISTRY_V2_ENABLED` |
| **Default lane** | v1 Builder Kit JSON when flag off |
| **Reference checker** | `scripts/check_build_registry_references.py` — **0 errors, 0 warnings**; local/manual only |
| **Scaffold quality repair guard** | Active — post-output inspection + optional one-pass repair (`HAM_SCAFFOLD_QUALITY_REPAIR=false` disables repair) |
| **Wave 3** | Closed — card-deck, reaction-time, rhythm-tap, deck-builder generated gates **Pass** |
| **Templates / starter files** | None — generative playbooks only |
| **Public kit picker / default v2** | None |

**Relevant sibling recipes (registry index):**

| Recipe | Shared surface with tactics-lite |
|--------|----------------------------------|
| `game.daily-puzzle-grid` | Grid cells, constraints, completion — **not** unit combat or turn phases |
| `game.resource-management-sim` | Turn/tick loops, goals — **not** spatial unit battle |
| `game.card-deck-turn-based` | Turn order, opponent step, win/loss — **not** grid movement |
| `game.deck-builder-lite` | Encounter loops, run result — **not** tile-based unit positioning |

---

## 3. Candidate recipe intent

Safe intended shape for **`game.turn-based-tactics-lite`** (schema authoring target — **not yet implemented**):

| Area | Intended behavior |
|------|-------------------|
| **Platform** | DOM-native, local-only, single-player browser game |
| **Grid board** | Small fixed rectangular grid (e.g. 5×5 or 6×6); cells addressable; visible board UI |
| **Units** | 1–3 player units and 1–3 enemy units seeded on the board with positions and HP |
| **Turn loop** | Player turn → select unit → move and/or attack → end turn → enemy turn → repeat |
| **Selection** | Selectable player units during player phase; selected unit drives action bar |
| **Movement** | Simple Manhattan movement within a fixed **movement range**; no pathfinding beyond range highlighting |
| **Attack** | Simple attack within fixed **attack range**; reduces HP or removes defeated units |
| **Enemy response** | Simple scripted enemy actions (move toward nearest player unit, attack if in range, or skip) — not full AI |
| **Health / damage** | HP on units; damage on attack; remove or mark defeated units |
| **Win / loss** | Win when all enemies defeated (or objective met); loss when all player units defeated |
| **Restart** | New battle resets grid, units, turn phase, selection, and result state |
| **Out of scope** | Backend, accounts, multiplayer, Canvas, physics, campaign map, inventory, terrain effects |

---

## 4. Why this is attractive

| Factor | Rationale |
|--------|-----------|
| **Natural Wave 4 lane** | Strategy/sim was deferred from Wave 3; puzzle-grid and resource-management provide grid and loop vocabulary without city-builder breadth |
| **Grid + turn state** | Tests grid state, turn order, unit selection, enemy response, and win/loss — distinct from puzzle completion and card hand zones |
| **DOM-native demo value** | “Select unit, move, attack, end turn” is recognizable tactics gameplay without engine risk |
| **Bridge to deeper strategy** | Bounded skirmish proves the lane before any city-builder or 4X expansion |
| **Builds on proven patterns** | Turn alternation from `mechanic.card-turn-loop` / `validator.turn-loop-alternation`; grid cells from `mechanic.grid-state` / `component.puzzle-grid`; result/restart from Wave 1–3 recipes |
| **Reference checker headroom** | Siblings post-trim sit ~9.5k–10.7k chars; a tightly scoped tactics playbook can target **under 11.4k** with discipline |

---

## 5. Why this is risky

| Risk | Detail |
|------|--------|
| **Grid / pathing ambiguity** | “Grid game”, “tile map”, “board” overlaps daily-puzzle-grid and dashboard layout language |
| **Movement / attack range complexity** | Range highlighting, occupancy rules, and diagonal vs Manhattan choices can balloon module count and scaffold logic |
| **Enemy AI scope creep** | Simple enemy response can drift into pathfinding, threat maps, or multi-step AI planning |
| **Genre drift** | RPG campaign, map editor, chess/checkers, tower defense, and RTS prompts pull toward excluded lanes |
| **Shell-only generated output** | Grid UI without move/attack handlers, stuck turn phase, or no-op reducers — same failure class Wave 3 guard addressed |
| **Disconnected state** | Board array vs unit roster mismatch; selected unit id not synced with grid positions |
| **Render budget pressure** | Grid + units + turn indicator + action bar + event log + validators approaches 12k faster than hangman or reaction-time |
| **Sibling false positives** | Must not steal daily-puzzle, resource-management, or card-deck prompts |

---

## 6. Ambiguity classes

| Class | Examples | Routing posture |
|-------|----------|-----------------|
| **Chess / checkers / board-game clone** | chess, checkers, Go, Othello, full board-game rules | **Never route** unless explicit tactics-lite semantics appear (small grid, HP units, move+attack range, player/enemy turns) — prefer v1 fallback |
| **Puzzle grid / daily puzzle** | Sudoku, logic grid, daily puzzle, cell constraints, Wordle-style grid | **Preserve `game.daily-puzzle-grid`** — no unit combat or turn phases |
| **City builder / sim management** | city builder, colony sim, production chain, population, resource allocation dashboard | **Never route to tactics** — preserve `game.resource-management-sim` or v1 |
| **Tower defense / RTS** | tower defense, real-time strategy, build towers, wave spawns, continuous time | **Never route initially** — out of `-lite` scope |
| **RPG campaign / story battle** | RPG campaign, story battles, inventory, equipment, skill tree, quest map | **Require clarification or v1 fallback** — campaign scope excluded |
| **Map editor / level editor** | map editor, level editor, tile painter, place tiles tool | **Never route** |
| **Physics / collision combat** | physics combat, collision damage, Canvas arcade, slingshot | **Defer to physics ADR** — not Wave 4 |
| **Generic “grid game”** | grid game, tile game, board game (alone) | **Weak signal — no route alone** |
| **“Tactics game” alone** | tactics, strategy game, turn-based (alone) | **Weak unless** grid + units + turns + move/attack signals combine |

---

## 7. Strong positive signals for future routing

Future routing (deferred until explicit approval) may require combinations such as:

- turn-based tactics game
- grid with units on a board
- move units then attack enemies
- player turn / enemy turn
- movement range and attack range
- defeat all enemies to win
- tactical battle on a small grid
- select a unit, move it, attack an enemy
- health bars on units
- restart battle

Require **game + grid + units + turns + move/attack** semantics — not bare “tactics” or “grid” alone.

---

## 8. Weak signals that should not route alone

These must **not** route to `game.turn-based-tactics-lite` without stronger combined signals:

- tactics
- strategy
- grid
- units
- enemies
- battle
- turns
- move
- attack
- board game

Weak signals should fall back to **v1** or, when unambiguous, to sibling recipes:

- **`game.daily-puzzle-grid`** — logic/daily/cell-constraint puzzles without unit combat
- **`game.resource-management-sim`** — economy/allocation sim without battle grid
- **`game.card-deck-turn-based`** — draw/hand/discard card battle without spatial grid

---

## 9. Explicit exclusions

Do **not** interpret future tactics routing or schema as supporting:

- chess
- checkers
- Go
- Sudoku / puzzle grid (→ `game.daily-puzzle-grid` or v1)
- city builder
- resource management sim (→ `game.resource-management-sim` or v1)
- tower defense
- RTS
- RPG campaign
- map editor
- level editor
- physics combat
- multiplayer tactics
- online PvP
- card battle / deck builder (→ card-family recipes or v1)
- dashboard grid / data table / kanban / sprint board

Prompts matching these families should **fall back to v1** unless unambiguous tactics-lite game signals dominate.

---

## 10. Candidate scope recommendation

Keep **Wave 4 v1 schema scope minimal**:

| In scope | Out of scope (defer) |
|----------|----------------------|
| One small fixed grid (5×5 or 6×6) | Large maps, scrolling world, fog of war |
| 1–3 player units | Party RPG rosters, inventory, equipment |
| 1–3 enemy units | Wave spawns, tower defense lanes |
| Simple Manhattan movement | Diagonal movement, terrain costs, A* pathfinding |
| Simple attack range (adjacent or fixed radius) | Line-of-sight, cover, elevation |
| No terrain effects initially | Water/mountain/wall tile rules |
| Range highlighting only — no pathfinding library | External pathfinding deps |
| Simple scripted enemy response | Multi-step AI, behavior trees |
| No campaign / map editor | Node graphs, level select, save slots |
| No inventory / equipment | Loot, shops, stat gear |
| No multiplayer | Hotseat, online PvP |
| No Canvas requirement | Physics/collision rendering |
| DOM-native components only | WebGL, game engine embed |
| Win/loss + restart required | Meta-progression across sessions |

**Render budget target:** stay under **12k** chars (Game Pack default); **prefer under 11.4k** (~95% cap) to leave headroom for reference-checker warnings.

---

## 11. Generated quality expectations

Any future **`/tmp/` generated gate review** for this recipe should require at minimum:

| Requirement | Rationale |
|-------------|-----------|
| **Non-empty grid** | Board renders with correct dimensions |
| **Units seeded on board** | Player and enemy units have positions and HP at start |
| **Selectable player units** | Click/tap selects a player unit during player phase |
| **Move action changes position** | Valid moves update grid state; invalid moves rejected |
| **Attack action changes HP / removes enemy** | Combat mutates unit HP or removes defeated units |
| **Enemy turn mutates state** | Enemy phase is not a no-op — move, attack, or explicit skip |
| **Win / loss state** | Clear terminal state when all enemies or all player units defeated |
| **Restart** | New battle resets grid, units, turn phase, selection, result |
| **No no-op reducers** | `MOVE`, `ATTACK`, `END_TURN`, `ENEMY_TURN` must mutate state when valid |
| **No disconnected board/unit arrays** | Unit positions consistent with grid occupancy |
| **No import/export mismatch** | Reducer actions match dispatched action types |
| **No drift into excluded classes** | Output is a small tactics skirmish, not chess, TD, RTS, or city sim |

First gate may be **Conditional pass** or **Hold** — plan for scaffold prompt/guard iteration (same rhythm as card-deck and deck-builder Wave 3 gates).

**Operator constraint:** generated apps stay under **`/tmp/`** only — never commit scaffold output.

---

## 12. Suggested schema module themes

Proposed module ids for schema authoring (names only — **not yet in registry**):

**Mechanics**

- `mechanic.tactics-grid-board-state`
- `mechanic.tactics-unit-roster`
- `mechanic.tactics-turn-loop`
- `mechanic.tactics-selection-state`
- `mechanic.tactics-movement-range`
- `mechanic.tactics-attack-resolution`
- `mechanic.tactics-enemy-response`
- `mechanic.tactics-battle-result-state`

**Components**

- `component.tactics-grid-board`
- `component.unit-status-panel`
- `component.tactics-action-bar`
- `component.tactics-event-log`
- `component.tactics-results-panel`

**Validators (conceptual — `runner: conceptual`)**

- seeded units on grid
- valid movement within range and occupancy
- attack resolution and HP bounds
- enemy response mutates state
- battle win/loss detection
- turn phase alternation (player ↔ enemy)

**Recovery playbooks**

- empty grid / missing units
- stuck turn phase
- invalid movement accepted
- missing win/loss result
- disconnected unit positions

Reuse patterns where sensible: `mechanic.grid-state` and `component.puzzle-grid` inform board layout but tactics modules must add **unit positions, selection, and combat** — do not route puzzle-grid prompts to tactics via shared grid vocabulary alone.

---

## 13. Readiness decision

| Question | Answer |
|----------|--------|
| Is ambiguity documented enough to author schema? | **Yes** — this review completes the gate requested by Wave 4 direction |
| Ready to author schema-only next? | **Yes, if scope remains small** and routing stays deferred |
| Ready to route? | **No** — routing requires separate explicit approval + tests |
| Ready for generated gate? | **Only after future routing** — or optional pre-routing `/tmp/` smoke during schema iteration |
| Is city-builder ready? | **No** — remains deferred beyond Wave 4 |

**Decision:** **Ready to author `game.turn-based-tactics-lite` schema-only next**, provided scope matches §10 and routing is **not** added in the same step. Generated gate review is **required** after future routing before declaring Wave 4 recipe complete.

---

## 14. Recommended next step

1. **Author `game.turn-based-tactics-lite` schema-only** — app type YAML + mechanics/components/validators/recovery/progress/learning modules; index in `registry-pack.yaml`.
2. **Keep render under 12k, preferably under 11.4k** — validate with `scripts/validate_game_pack_registry.py --app-type game.turn-based-tactics-lite --check` and reference checker `--check-render-budget`.
3. **Do not add routing in the same step** — schema land and validation tests first per [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md).
4. **Add conservative routing only after explicit human approval** — intent fixtures from §7–§9, tests, and [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md) checklist.
5. **Run generated gate review before declaring Wave 4 recipe complete** — `/tmp/` operator run → outcome report under `outcome-reports/`; extend scaffold quality guard if new failure classes appear.

---

## 15. Non-goals

This review does **not** authorize:

- Landing `game.turn-based-tactics-lite` YAML from this review alone
- Routing or `intent.py` changes
- Default Build Registry v2 enablement (`HAM_BUILD_REGISTRY_V2_ENABLED` stays opt-in)
- Canvas / physics recipes or physics ADR bypass
- `game.city-builder-lite` authoring
- RTS / tower defense / RPG campaign scope
- Multiplayer or backend / accounts
- Templates or starter source files
- Committing generated app output from `/tmp/`
- Autonomous Hermes PRs or recipe mutation
- API, frontend, Builder Studio, CI, or scaffold behavior changes

---

## 16. References

| Doc | Purpose |
|-----|---------|
| [WAVE_4_STRATEGY_SIM_DIRECTION.md](WAVE_4_STRATEGY_SIM_DIRECTION.md) | Wave 4 direction; tactics vs city-builder deferral |
| [WAVE_3_COMPLETION_CHECKPOINT.md](WAVE_3_COMPLETION_CHECKPOINT.md) | Wave 3 closeout; generated gate rhythm |
| [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md) | Route-after-approval policy |
| [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md) | Recipe authoring rules |
| [STATUS.md](STATUS.md) | Live handoff — 14 recipes, checker, flag posture |
| [outcome-reports/game.deck-builder-lite.wave3-gate-review.md](outcome-reports/game.deck-builder-lite.wave3-gate-review.md) | Progression-loop generated gate example |
| [outcome-reports/game.card-deck-turn-based.wave3-gate-fix-review.md](outcome-reports/game.card-deck-turn-based.wave3-gate-fix-review.md) | Turn-loop generated gate example |
| [GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md](GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md) | Scaffold quality guard context |
| [REGISTRY_REFERENCE_CHECKER_PROPOSAL.md](REGISTRY_REFERENCE_CHECKER_PROPOSAL.md) | Reference checker rationale |
| [REFERENCE_CHECKER_IMPLEMENTATION_PLAN.md](REFERENCE_CHECKER_IMPLEMENTATION_PLAN.md) | Checker usage before/after schema land |
| [game-pack/registry-pack.yaml](game-pack/registry-pack.yaml) | Current module index — puzzle-grid, resource-sim, card-deck, deck-builder patterns |
