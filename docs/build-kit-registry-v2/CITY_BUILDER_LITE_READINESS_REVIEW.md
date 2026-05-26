# City Builder Lite Readiness Review

> **Readiness/ambiguity gate only · Not recipe approval · Not routing approval · Not implementation authorization**

Ambiguity and routing-risk review before authoring a potential **`game.city-builder-lite`** Game Pack recipe — the likely **final planned DOM-native game kit** before DOM-native phase closeout and website/design-system work. This document evaluates prompt boundaries, scope limits, generated-quality expectations, and sibling-recipe collisions. It does **not** add a recipe, routing, templates, or runtime changes.

**Review date:** 2026-05-26 (UTC)  
**Baseline:** `origin/main` at `9b2e037a` — fifteen recipes, 349 indexed modules, all routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`, reference checker **0 errors / 0 warnings**, [GAMEPLAY_QUALITY_PRINCIPLES.md](GAMEPLAY_QUALITY_PRINCIPLES.md) landed, **`game.turn-based-tactics-lite`** generated gate **Pass**.

For Wave 4 direction see [WAVE_4_STRATEGY_SIM_DIRECTION.md](WAVE_4_STRATEGY_SIM_DIRECTION.md). For routing policy see [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md). For gameplay doctrine see [GAMEPLAY_QUALITY_PRINCIPLES.md](GAMEPLAY_QUALITY_PRINCIPLES.md).

---

## 1. Executive summary

**`game.city-builder-lite` is the likely final planned DOM-native game kit** before HAM moves from generative game-kit work to website/design-system extraction. It is an attractive capstone because it combines grid placement, resource pools, progression, and goal/result state in one recognizable browser game shape.

**It is also high-risk.** City-builder prompts routinely drift into analytics dashboards, resource-management apps without placement, map/level editors, colony/factory automation sims, or open-ended SimCity-scale systems. Generated scaffolds often ship static layout shells with disconnected resource labels and no playable build loop.

**This review does not add a recipe or routing.**

**Recommended posture:** **Ready to author schema-only next** only if scope remains very small (fixed grid, few building types, few resources, simple turn/day tick, one clear goal). **Routing must stay deferred** until schema validates, reference checker stays clean, and explicit human approval follows [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md). A **`/tmp/` generated gate review** is required before declaring the recipe complete after future routing.

---

## 2. Current baseline

| Dimension | State |
|-----------|--------|
| **Recipes** | **15** |
| **Indexed modules** | **349** |
| **Routing** | All fifteen Game Pack recipes route narrowly behind `HAM_BUILD_REGISTRY_V2_ENABLED` |
| **Default lane** | v1 Builder Kit JSON when flag off or unset |
| **Reference checker** | `scripts/check_build_registry_references.py` — **0 errors, 0 warnings**; local/manual only; not CI-blocking |
| **Scaffold quality repair guard** | Active — post-output inspection + optional one-pass repair (`HAM_SCAFFOLD_QUALITY_REPAIR=false` disables repair) |
| **Gameplay quality doctrine** | [GAMEPLAY_QUALITY_PRINCIPLES.md](GAMEPLAY_QUALITY_PRINCIPLES.md) — FSM-lite/reducer default; ECS deferred |
| **Wave 4 tactics** | **`game.turn-based-tactics-lite`** authored, routed, generated gate **Pass** — [outcome report](outcome-reports/game.turn-based-tactics-lite.wave4-gate-review.md) |
| **Canvas / physics** | **Deferred** — separate ADR/design track |
| **Templates / starter files** | None — generative playbooks only |
| **Public kit picker / default v2** | None |

**Relevant sibling recipes (registry index):**

| Recipe | Shared surface with city-builder-lite |
|--------|--------------------------------------|
| `game.resource-management-sim` | Resources, turn/tick, allocation, goals — **not** spatial building placement on a city grid |
| `game.daily-puzzle-grid` | Fixed grid, cell rules — **not** building production or population loops |
| `game.turn-based-tactics-lite` | Grid, turn phases, win/loss — **not** construction or economy placement |
| `game.deck-builder-lite` | Progression, run result, restart — **not** tile placement or resource production |
| `game.idle-incremental` | Resource tick, upgrades — **not** grid placement or city layout |

---

## 3. Candidate recipe intent

Safe intended shape for **`game.city-builder-lite`** (schema authoring target — **not yet implemented**):

| Area | Intended behavior |
|------|-------------------|
| **Platform** | DOM-native, local-only, single-player browser game |
| **Grid** | Small fixed grid (e.g. 5×5 or 6×6); visible board; cells accept building placement |
| **Buildings** | 3–5 simple building types (e.g. house, farm, power, water, shop) with placement rules |
| **Resources** | 2–4 tracked pools (e.g. gold, food, power, population/happiness-lite) |
| **Loop** | Player selects building → places on valid cell → **End Day/Turn** → production rules apply |
| **Production** | Buildings modify resources each tick/day via simple rules (not multi-hop chains) |
| **Population / happiness** | Optional lightweight rule (e.g. housing vs population, happiness threshold) |
| **Upgrades / choices** | Simple build/upgrade choice from palette — **no tech tree** |
| **Goal** | One clear win condition (e.g. reach population N or happiness target by day D) |
| **Failure / constraint** | Optional fail/stalemate (e.g. bankruptcy, happiness collapse, day limit miss) |
| **Result / restart** | Visible result panel; **New City** reseeds grid, resources, buildings, day, and result |
| **Out of scope** | Backend, accounts, multiplayer, Canvas, physics, map editor, pathfinding, automation belts, factory graphs, real-time sim |

---

## 4. Why this is attractive

| Factor | Rationale |
|--------|-----------|
| **Natural DOM-native capstone** | Combines grid, resources, progression, and goals — the main remaining archetype after tactics, sim, puzzle, card, and word families |
| **Builds on Wave 2–4 lessons** | Resource ticks from `game.resource-management-sim`; grid cells from `game.daily-puzzle-grid`; turn/result/restart from tactics and deck-builder gates |
| **Bridge to future app/site patterns** | Tests layout + canonical state + progression — useful precursor to website/design-system work **after** game-kit phase closes |
| **Operator-facing demo value** | “Place buildings, end day, watch resources grow, hit city goal” is legible without engine risk |
| **Reference checker headroom** | Siblings post-trim sit ~8.5k–11k chars; a disciplined lite playbook can target **under 11.4k** if module count is controlled |
| **Doctrine alignment** | Fits [GAMEPLAY_QUALITY_PRINCIPLES.md](GAMEPLAY_QUALITY_PRINCIPLES.md) FSM-lite reducer model and minimum playable loop |

---

## 5. Why this is risky

| Risk | Detail |
|------|--------|
| **Scope balloon** | SimCity, Factorio, Anno, or full colony sim prompts exceed `-lite` in one recipe |
| **Dashboard drift** | Static resource panels, charts, and KPI cards without placement or tick loop |
| **Map / editor ambiguity** | “Build a map”, “tile editor”, “level designer” are not city-builder games |
| **Placement rule explosion** | Adjacency, zoning, roads, utilities, and multi-tile footprints expand module and scaffold complexity |
| **Production chain creep** | Input/output graphs, warehouses, and belt logic belong in factory sim — not lite city-builder |
| **Shell-only generated output** | Grid renders; palette exists; **End Day** no-ops; resources never change — same failure class Wave 3–4 guards address |
| **Disconnected state** | `resources` object vs grid cell payloads vs building catalog drift |
| **Vague win/loss** | “Grow your city” without measurable goal or result transition |
| **Render budget pressure** | Grid + palette + resource panel + action bar + event log + validators + recovery playbooks approaches 12k quickly |
| **Sibling false positives** | Must not steal resource-management, puzzle-grid, tactics, or dashboard prompts |
| **Quality guard gap** | No city-builder-specific detectors in `scaffold_quality.py` yet — gate will rely on doctrine + manual review until repeated failures justify detectors |

---

## 6. Ambiguity classes

| Class | Examples | Routing posture |
|-------|----------|-----------------|
| **Resource dashboard / analytics** | KPI dashboard, metrics panel, analytics app, inventory report | **Never route** to city-builder |
| **Resource-management sim** | allocate budget, production chain, colony management without building placement | **Preserve `game.resource-management-sim`** unless explicit **building placement on city grid** appears |
| **Map editor / level editor** | map editor, tile painter, level designer, place tiles tool | **Never route initially** |
| **Base builder / colony sim** | colony sim, base building survival, outpost management | **Require strict lite scope** (small grid, few buildings, simple tick) or **v1 fallback** |
| **Factory / automation sim** | factory game, conveyor belts, crafting graph, Factorio-like | **Defer** — out of `-lite` scope |
| **Tower defense / RTS** | tower defense, real-time strategy, build towers, wave spawns | **Never route** |
| **Puzzle grid / daily puzzle** | Sudoku, logic grid, daily puzzle, cell constraints | **Preserve `game.daily-puzzle-grid`** |
| **Tactics grid** | select units, move, attack, enemy turn, battle win/loss | **Preserve `game.turn-based-tactics-lite`** |
| **Real estate / urban planning dashboard** | property listing, zoning dashboard, urban planning tool, GIS map | **Never route** |
| **Generic “city app” / “grid builder”** | city app, builder app, grid builder (alone) | **Weak signal — no route alone** |

---

## 7. Strong positive signals for future routing

Future routing (deferred until explicit approval) should require **combined** signals such as:

- city-building game / city builder game
- place buildings on a grid / build structures on tiles
- houses, farms, power, water on a **city grid**
- buildings produce resources each turn or each day
- grow population or happiness / housing for citizens
- build or upgrade structures / building palette
- meet a city goal by day N or turn N
- local browser city-builder game
- small grid city sim with win/loss/restart / new city

Single keywords from §8 are insufficient alone.

---

## 8. Weak signals that should not route alone

These terms need corroborating **placement + tick + goal** signals before any future city-builder route:

- city
- builder
- grid
- resources
- buildings
- population
- map
- planning
- simulation
- dashboard
- management

---

## 9. Explicit exclusions

Do **not** route to `game.city-builder-lite` when prompts emphasize:

- analytics / dashboard / KPI / reporting
- resource-management **only** with no building placement on a grid
- spreadsheet / planner / budget tool
- urban planning tool / civic planning app
- real estate app / property marketplace
- map editor / level editor / tile painter
- factory automation / crafting graph / conveyor sim
- tower defense / RTS / tactics battle
- puzzle grid / daily logic puzzle
- multiplayer city game / MMO city
- backend / accounts / cloud save requirement
- Canvas / physics / WebGL city renderer
- finance / economy dashboard / trading desk

When exclusions match, prefer **`game.resource-management-sim`**, **`game.daily-puzzle-grid`**, **`game.turn-based-tactics-lite`**, or **v1 fallback** per [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md).

---

## 10. Candidate scope recommendation

Author **only** if the playbook enforces this **lite** contract:

| Constraint | Recommendation |
|------------|----------------|
| **Grid** | One small fixed grid (5×5 or 6×6) |
| **Building types** | 3–5 max |
| **Resources** | 2–4 max |
| **Time loop** | Simple **End Day/Turn** button |
| **Production** | Simple per-building rules (flat +/- per tick) |
| **Placement** | Occupancy + maybe adjacency — **no pathfinding** |
| **Population / happiness** | One simple rule if used |
| **Goal** | One measurable win condition |
| **Failure** | One optional fail/constraint if used |
| **Excluded** | Tech tree, roads network, multi-tile footprints, automation belts, map editor, multiplayer, backend |

DOM-native only. Canvas/physics out of scope.

---

## 11. Generated quality expectations

Future **`/tmp/` gate review** (after routing approval) should verify at minimum:

| Expectation | Pass bar |
|-------------|----------|
| **Non-empty grid** | Seeded or initialized with playable cells |
| **Visible resources** | Canonical resource pools rendered and tracked |
| **Building palette** | Player can select a building type |
| **Placement mutates grid** | Valid placement writes building to cell state |
| **Invalid placement blocked** | Out-of-bounds, occupied, or rule violations rejected with feedback |
| **Turn/day advances production** | End Day/Turn runs production tick |
| **Resources change** | Building effects alter pools immutably |
| **Population/happiness/goal** | Lite metrics update from rules when in scope |
| **Win/fail/result reachable** | Goal or fail condition sets visible result state |
| **Restart reseeds** | New city restores grid, buildings, resources, day, result — not empty/no-op reset |
| **No dashboard shell** | Panels connected to reducer mutations |
| **No no-op reducers** | Primary actions mutate state |
| **No disconnected arrays** | Grid, catalog, and resource pools stay in sync |
| **No import/export mismatch** | Consistent module exports |
| **No drift** | Excluded classes from §9 absent |

Aligns with [GAMEPLAY_QUALITY_PRINCIPLES.md](GAMEPLAY_QUALITY_PRINCIPLES.md) §4–§7. City-builder-specific scaffold detectors are **not** required before schema land; add when gate failures repeat.

**Suggested canonical gate prompt (draft — not binding until recipe authored):**

> Build a browser city-building game on a small fixed grid where the player places a few building types, tracks simple resources, ends each day to apply production rules, grows population or happiness, reaches a clear city goal, can fail a simple constraint, and can restart with a freshly seeded city.

---

## 12. Suggested schema module themes

Possible Game Pack modules (names illustrative — compose/render budget must stay under 12k):

**State / mechanics**

- `city-grid-state` — fixed grid + cell occupancy
- `city-building-catalog` — palette entries (id, cost, production, placement rules)
- `city-placement-rules` — bounds, occupancy, optional adjacency
- `city-resource-pools` — gold/food/power/population/happiness-lite
- `city-production-tick` — end-day application of building effects
- `city-population-happiness` — optional lite citizen rule
- `city-upgrade-choice` — simple build/upgrade selection (not tech tree)
- `city-goal-result-state` — win/fail/result phase + restart

**Components**

- `city-grid-board` — clickable placement grid
- `building-palette` — structure picker
- `resource-status-panel` — visible pools
- `city-action-bar` — End Day + Restart/New City
- `city-event-log` — placement/production feedback
- `city-results-panel` — goal met / failed + restart

**Validators**

- seeded grid non-empty
- valid placement enforced
- production tick mutates resources
- resource bounds / no negative where disallowed
- goal/result detection from next state

**Recovery playbooks**

- empty grid / missing seed
- invalid placement accepted
- stuck production loop (End Day no-op)
- missing goal/result transition
- dashboard drift (panels without reducer wiring)

**Meta**

- progress label + learning hook for city-builder-lite family

Reuse patterns from `mechanic.grid-state`, `mechanic.economy`, resource-management validators, and tactics result/restart modules where references exist — do not duplicate render budget without trim plan.

---

## 13. Readiness decision

| Question | Decision |
|----------|----------|
| **Ready to author schema-only?** | **Yes — conditionally.** Proceed only with §10 lite scope locked. |
| **Ready to route?** | **No.** Routing deferred until schema validates, checker clean, tests added, explicit approval. |
| **Ready to declare complete?** | **No.** Generated gate required after future routing. |
| **Canvas / physics?** | **No.** DOM-native only. |
| **Expand beyond lite?** | **No** in this tranche — no map editor, factory sim, or multiplayer. |

**Summary:** **Ready to author schema-only next** if scope stays very small. **Not ready** for routing, default v2 enablement, or completion claim.

---

## 14. Recommended next step

1. **Author `game.city-builder-lite` schema-only** in `docs/build-kit-registry-v2/game-pack/` following [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md).
2. **Keep render under 12k**, preferably **under 11.4k** (90% headroom rule).
3. **Run** `scripts/validate_game_pack_registry.py`, `scripts/check_build_registry_references.py`, and registry pytest suite.
4. **Do not route** until schema validates and explicit routing approval is recorded.
5. **Add conservative routing** in `src/ham/build_registry/intent.py` only after dedicated intent tests — separate PR from schema.
6. **Run generated gate review** under `/tmp/` with `HAM_BUILD_REGISTRY_V2_ENABLED=true` before declaring the recipe complete.
7. **After city-builder passes**, publish a **DOM-native game-kit completion checkpoint** doc and then begin website/design-system phase per program direction.

---

## 15. Non-goals

This review does **not**:

- Add `game.city-builder-lite` recipe YAML
- Add prompt routing or enable Build Registry v2 by default
- Author Canvas/physics modules
- Approve map editor, RTS, tower defense, or factory automation scope
- Approve multiplayer or backend/account flows
- Commit generated app output from `/tmp/`
- Start website/design-system or Builder Studio work
- Claim CI-blocking generated gates or full-app validation

---

## 16. References

| Document | Relevance |
|----------|-----------|
| [GAMEPLAY_QUALITY_PRINCIPLES.md](GAMEPLAY_QUALITY_PRINCIPLES.md) | Gameplay doctrine; FSM-lite; gate criteria |
| [WAVE_4_STRATEGY_SIM_DIRECTION.md](WAVE_4_STRATEGY_SIM_DIRECTION.md) | City-builder deferred vs tactics-first rationale |
| [TACTICS_GRID_AMBIGUITY_REVIEW.md](TACTICS_GRID_AMBIGUITY_REVIEW.md) | Ambiguity review template; grid routing posture |
| [WAVE_3_COMPLETION_CHECKPOINT.md](WAVE_3_COMPLETION_CHECKPOINT.md) | Wave 3 closeout; quality guard baseline |
| [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md) | Route-after-approval discipline |
| [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md) | Schema authoring rules |
| [STATUS.md](STATUS.md) | Live 15-recipe / 349-module snapshot |
| [outcome-reports/game.turn-based-tactics-lite.wave4-gate-review.md](outcome-reports/game.turn-based-tactics-lite.wave4-gate-review.md) | Wave 4 tactics gate **Pass** |
| [outcome-reports/game.deck-builder-lite.wave3-gate-review.md](outcome-reports/game.deck-builder-lite.wave3-gate-review.md) | Progression/restart gate pattern |
| [GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md](GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md) | Scaffold quality gap narrative |
| [REGISTRY_REFERENCE_CHECKER_PROPOSAL.md](REGISTRY_REFERENCE_CHECKER_PROPOSAL.md) | Checker scope |
| [REFERENCE_CHECKER_IMPLEMENTATION_PLAN.md](REFERENCE_CHECKER_IMPLEMENTATION_PLAN.md) | Checker implementation status |

**Related sibling modules (registry index — inspect before compose):**

- `game.resource-management-sim` — economy/tick/goal vocabulary
- `game.daily-puzzle-grid` — grid cell/state patterns
- `game.turn-based-tactics-lite` — grid + turn + result/restart patterns
- `game.deck-builder-lite` — progression + run result + restart patterns
