# Build Registry v2 Wave 4 Strategy/Sim Direction

> **Direction/readiness gate only · Not recipe approval · Not routing approval · Not implementation authorization**

Planning checkpoint before any Wave 4 strategy/sim recipe authoring. This document evaluates **`game.turn-based-tactics-lite`** as the likely first Wave 4 candidate, compares it against **`game.city-builder-lite`**, and records deferrals and prerequisites. It does **not** add a recipe, routing, templates, runtime changes, or default v2 enablement.

**Direction date:** 2026-05-26 (UTC)  
**Baseline:** `origin/main` at `09922982` — fourteen recipes, 323 indexed modules, all routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`, reference checker **0 errors / 0 warnings** on full orphan + render-budget pass.

For live status see [STATUS.md](STATUS.md). For Wave 3 closeout see [WAVE_3_COMPLETION_CHECKPOINT.md](WAVE_3_COMPLETION_CHECKPOINT.md).

---

## 1. Executive summary

**Wave 3 is closed.** The Game Pack now has fourteen DOM-native recipes, scaffold quality repair guard coverage, and a local reference checker with clean results after near-budget trims. **Do not add another recipe immediately** — but if expansion resumes, the next lane should be **strategy/sim**, not card/deck, arcade timing, or physics.

**Recommended Wave 4 first candidate:** `game.turn-based-tactics-lite` — small grid, turn order, simple unit actions, win/loss — **not** full 4X, not multiplayer, not Canvas/physics.

**Explicitly deferred:** `game.city-builder-lite` — broader sim scope, stronger dashboard/placement UX drift, and heavier render-budget pressure. Wait **beyond Wave 4** or until sim generated outputs are better understood.

**Physics / Canvas:** remains on a **separate ADR/design track** — no physics-family recipes in Wave 4.

**This document does not authorize schema, routing, or enablement.** If Wave 4 proceeds, follow the established rhythm: **schema-first → validate/compose/render → explicit routing approval → `/tmp/` generated gate review → outcome report**.

---

## 2. Current baseline (post Wave 3 + registry hardening)

| Dimension | State |
|-----------|--------|
| **Recipes** | 14 |
| **Indexed modules** | 323 |
| **Routing** | All 14 recipes route narrowly behind `HAM_BUILD_REGISTRY_V2_ENABLED` |
| **Default lane** | v1 Builder Kit JSON when flag off |
| **Templates / starter files** | None — generative playbooks only |
| **Scaffold quality guard** | Active — post-output inspection + optional one-pass repair (`HAM_SCAFFOLD_QUALITY_REPAIR=false` disables repair) |
| **Reference checker** | `scripts/check_build_registry_references.py` — local/manual; **0 errors, 0 warnings**; not CI-blocking |
| **Render budget headroom** | All fourteen recipes below 90% of 12k cap after near-budget trim |
| **Generated gate reviews (Wave 3)** | card-deck, reaction-time, rhythm-tap, deck-builder — all **Pass** |
| **Public kit picker / default v2** | None |

**Wave inventory:**

| Wave | Recipes | Lane |
|------|---------|------|
| Wave 1 | idle-incremental, trivia-timer, branching-narrative, memory-match, word-daily | Core DOM patterns |
| Wave 2 | daily-puzzle-grid, resource-management-sim, hangman-lite, typing-speed-racer, word-builder | Grid/sim/word expansion |
| Wave 3 | card-deck-turn-based, reaction-time-challenge, rhythm-tap-lite, deck-builder-lite | Card/deck + arcade timing |
| Wave 4 (proposed) | **turn-based-tactics-lite only if approved after this doc** | Strategy/sim — bounded grid tactics |

---

## 3. Why Wave 4 strategy/sim now

Wave 3 proved the operating model at higher complexity:

| Proof from Wave 3 | Implication for Wave 4 |
|-------------------|------------------------|
| Schema-first + route-after-approval scales to 323 modules | Strategy/sim can land schema-only without breaking registry discipline |
| Generated gate reviews are mandatory | Tactics grid/turn loops need the same `/tmp/` gate bar — routing alone is insufficient |
| Scaffold quality guard catches shell-only / no-op reducers | Grid movement and turn actions are high-risk for stub handlers — guard may need tactics-specific extensions |
| Reference checker catches drift at 14 recipes | A fifteenth recipe increases orphan/budget risk — run checker before and after schema land |
| Card/deck ambiguity review pattern worked | Tactics needs a **grid/strategy ambiguity review** before routing — overlap with daily-puzzle-grid and planning tools |

Wave 3 **explicitly deferred** strategy/sim (`WAVE_3_COMPLETION_CHECKPOINT.md`). Registry hardening (reference checker, near-budget trim) is now in place. The next expansion lane is **bounded tactics**, not another card or timing recipe.

---

## 4. Candidate comparison: tactics-lite vs city-builder-lite

| Dimension | `game.turn-based-tactics-lite` | `game.city-builder-lite` |
|-----------|-------------------------------|---------------------------|
| **Core loop** | Grid positions, turn order, move/attack/end-turn, win/loss | Placement, production chains, population/capacity growth |
| **Extends existing recipes** | Grid cells from daily-puzzle-grid; turn/state from card-deck | Extends resource-management-sim into spatial placement |
| **State complexity** | Moderate — units, positions, HP/actions, turn phase | High — buildings, tiles, production, population, upgrades |
| **Render budget risk** | Moderate — grid + unit list + action buttons | High — many sim modules already near budget in Wave 2 |
| **Routing ambiguity** | Grid/tactics overlaps puzzle grids, chess tutors, project planning | Strong overlap with dashboards, GIS, city planning SaaS, SimCity-like scope creep |
| **Generated quality risk** | Move validation, turn order, action handlers, win detection | Placement rules, production ticks, economy loops, map expansion |
| **Evidence from generated gates** | No tactics recipe yet; grid sim from Wave 2 still mostly manual-outcome only | Same — resource-management-sim has manual outcome only, no Wave 3-style generated gate |
| **Wave 4 fit** | **Preferred first strategy/sim recipe** | **Defer beyond Wave 4** |

**Decision:** Pursue **`game.turn-based-tactics-lite` first** if Wave 4 authoring is approved. Keep **`game.city-builder-lite` deferred** until at least one Wave 2 sim/grid recipe has a generated gate review at Pass bar and tactics-lite (if landed) proves the strategy/sim lane.

---

## 5. Why `game.turn-based-tactics-lite` is the likely Wave 4 first recipe

### Benefits

| Factor | Rationale |
|--------|-----------|
| **Natural Wave 4 lane** | Wave 3 closed card/deck and arcade timing; strategy/sim was the deferred Option B from [WAVE_3_DIRECTION_CHECKPOINT.md](WAVE_3_DIRECTION_CHECKPOINT.md) |
| **DOM-native and bounded** | Small grid (e.g. 5×5–8×8), few units, discrete turns — no Canvas, physics, or pathfinding library assumptions |
| **Distinct product demo** | “Move units, take turns, win battle” is recognizable without sim-economy breadth |
| **Builds on proven patterns** | Turn order and phased state from card-deck; cell/grid vocabulary from daily-puzzle-grid; win/loss/result from Wave 1–3 recipes |
| **Lower scope than city-builder** | Avoids placement economies, population simulation, and multi-system production chains in one recipe |
| **Reference checker headroom** | Starting from ~10k-char siblings, a tightly scoped tactics playbook has a realistic path under 12k |

### Risks

| Risk | Detail |
|------|--------|
| **Grid ambiguity** | “Grid game”, “tile map”, “cell board” overlaps `game.daily-puzzle-grid` (logic/daily puzzle) and generic layout/dashboard language |
| **Chess / board-game drift** | Full chess, checkers, or go prompts may exceed lite scope or need different rules modules |
| **Planning / GIS / project-tool drift** | “Sprint board”, “roadmap grid”, “territory planning”, “GIS map” — must fall back to v1 |
| **RPG / 4X scope creep** | Inventory, fog-of-war, tech trees, multiplayer — out of scope for `-lite` |
| **Generated shell-only grids** | UI grid without move validation, stale turn state, or no-op `MOVE_UNIT` reducers — same class Wave 3 guard addressed |
| **Render budget** | Grid + units + action log + turn indicator approaches 12k faster than hangman or reaction-time |
| **Sibling precedence** | Routing must not steal daily-puzzle or resource-management prompts |

### Recommendation

**Viable as Wave 4 first recipe** — but **only after**:

1. This direction doc is accepted (planning gate — not implementation gate).
2. A **`TACTICS_GRID_AMBIGUITY_REVIEW.md`** (or equivalent) documents positive/negative fixtures and cross-recipe exclusions.
3. Schema lands **without routing**; validate, compose, render, and reference-check pass.
4. Human approval for routing per [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md).
5. **`/tmp/` generated gate review** reaches **Pass** with scaffold quality guard active.

---

## 6. Why `game.city-builder-lite` stays deferred

| Reason | Detail |
|--------|--------|
| **Broader sim surface** | Placement + production + population is multiple interacting systems — higher module count and scaffold failure modes |
| **Wave 2 evidence gap** | [game.resource-management-sim.manual-outcome.md](outcome-reports/game.resource-management-sim.manual-outcome.md) warns about city-builder scope drift; **no generated gate review** exists for resource-management-sim yet |
| **Dashboard / SaaS drift** | “City dashboard”, “urban analytics”, “facility management” — stronger false-positive family than tactics battle language |
| **Render budget** | resource-management-sim already trimmed to ~10k chars; city-builder would likely exceed comfortable headroom without aggressive scope cuts |
| **Wave 3 lesson** | Deck-builder showed progression loops need dedicated quality detectors — city-builder would need placement/production/run-result guards not yet designed |
| **Explicit Wave 3 decision** | Deferred in [WAVE_3_COMPLETION_CHECKPOINT.md](WAVE_3_COMPLETION_CHECKPOINT.md) — wait until sim outputs are better understood |

**Defer until:** `game.turn-based-tactics-lite` (if landed) passes generated gate **and** at least one Wave 2 sim/grid recipe has a generated gate at Pass bar.

---

## 7. Candidate recipe intent — `game.turn-based-tactics-lite`

Safe intended shape for schema authoring (target only — **not yet implemented**):

| Area | Intended behavior |
|------|-------------------|
| **Platform** | DOM-native, local-only, single-player browser game |
| **Grid** | Small rectangular grid (e.g. 5×5–8×8); cells addressable; no infinite map |
| **Units** | Small fixed roster (e.g. 1–3 player units vs 1–3 enemies); HP or elimination win condition |
| **Turn order** | Explicit phases: player turn → enemy turn (simple AI or scripted actions) |
| **Actions** | Move to adjacent cell, basic attack/action, end turn — no inventory/skills tree |
| **Win/loss** | Eliminate enemies or reach objective cell; clear result screen |
| **Restart** | New game resets grid, units, turn phase, and result state |
| **Out of scope** | Fog of war, tech trees, multiplayer, pathfinding libraries, Canvas, physics, full chess rules |

**Differentiators vs siblings:**

| Sibling | Tactics-lite must require | Tactics-lite must exclude |
|---------|---------------------------|---------------------------|
| `game.daily-puzzle-grid` | Units, turns, combat/move actions | Daily puzzle, logic clues, Wordle-style feedback |
| `game.resource-management-sim` | Grid battle, turn combat | Resource bars, production chains, colony economy |
| `game.memory-match` | Spatial tactics, turn order | Flip pairs, concentration |
| `game.card-deck-turn-based` | Grid movement, unit positions | Draw/hand/discard card battle (unless hybrid prompt — fall back to v1) |

---

## 8. Routing posture (future — not authorized here)

If routing is later approved, expect **conservative** matching similar to Wave 3:

### Strong positive signals (future routing design)

- turn-based tactics game
- grid battle with units
- move units on a tile grid each turn
- small tactics skirmish / battle on a board
- enemy units, player turn, end turn
- fire emblem-like / advance wars-like browser game *(routing/tests only — no third-party IP in generated copy)*

Require **game + grid + turn + unit/action** semantics — not bare “grid” or “strategy” alone.

### Weak signals that should not route alone

- grid
- tile map
- board game
- strategy game
- tactics
- turn-based
- chess
- battlefield
- planning board
- sprint board
- roadmap grid

Weak signals should fall back to **v1** or, when unambiguous, to **`game.daily-puzzle-grid`** (logic/daily puzzle) or **`game.resource-management-sim`** (economy sim without battle grid).

### Negative families (must stay blocked)

- SaaS dashboards, analytics grids, data tables
- GIS / map dashboards, urban planning tools
- Project management / kanban / sprint boards
- Chess tutors, chess engines, full chess apps
- 4X strategy, grand strategy, multiplayer lobby
- Physics / Canvas arcade (separate ADR track)
- Generic “game” or “simulator” without tactics/grid/turn signals

**Routing precedence (draft):** tactics-lite would likely sit **after** daily-puzzle-grid and resource-management-sim and **before** any future city-builder — exact order requires ambiguity review + tests, not this doc.

---

## 9. Generated quality and scaffold guard expectations

Wave 3 established that **routing + v2 context ≠ playable output**. Tactics-lite will likely need:

| Failure mode | Mitigation |
|--------------|------------|
| Shell grid UI, no move logic | Existing no-op reducer / empty handler detection; tactics-specific move/attack validation in prompt + guard |
| Turn phase stuck | Turn-order / end-turn wiring checks (similar to card-deck turn phase) |
| Units overlap or off-grid | Grid bounds validation in playbook + optional guard hints |
| Win condition never fires | Result-state detection (pattern from rhythm/card-deck gates) |
| Enemy turn no-op | Scripted enemy action or skip — guard against empty enemy phase |
| Stale closure on result | Same class as rhythm-tap `setFinalScore` fix |

**Expectation:** First generated gate may be **Conditional pass** or **Hold** — plan for one guard/prompt iteration before declaring Pass, same as card-deck and deck-builder.

**Operator constraint:** Generated apps stay under **`/tmp/`** only — never commit scaffold output.

---

## 10. Prerequisites before schema authoring

| Prerequisite | Status | Action if Wave 4 proceeds |
|--------------|--------|---------------------------|
| Wave 3 closed | Done | — |
| Reference checker clean | Done (0/0) | Re-run after any schema edit |
| Direction doc (this file) | **This artifact** | Accept before authoring |
| Grid/strategy ambiguity review | **Not started** | Author `TACTICS_GRID_AMBIGUITY_REVIEW.md` with prompt fixtures |
| Resource-management generated gate | **Missing** | Optional but recommended — one `/tmp/` gate for sim baseline |
| Daily-puzzle-grid generated gate | **Missing** | Optional — helps grid playbook patterns |
| Physics ADR | **Not required for tactics** | Keep Canvas/physics deferred |

---

## 11. Recommended Wave 4 rhythm (if approved)

Do **not** skip steps. Order matches Wave 3 and [DECK_BUILDER_LITE_READINESS_REVIEW.md](DECK_BUILDER_LITE_READINESS_REVIEW.md):

| Step | Action | Routing? | Commit scope |
|------|--------|----------|--------------|
| 1 | Accept this direction doc | No | docs only |
| 2 | Author `TACTICS_GRID_AMBIGUITY_REVIEW.md` | No | docs only |
| 3 | Author `game.turn-based-tactics-lite` schema + modules | No | docs/YAML + tests |
| 4 | Validate compose/render + reference checker | No | — |
| 5 | **Explicit approval** for routing | — | human gate |
| 6 | Add narrow intent logic + routing tests | Yes (flag-gated) | code + tests |
| 7 | `/tmp/` generated gate review → outcome report | — | docs under outcome-reports/ |
| 8 | Scaffold guard extensions if gate finds new failure class | Maybe | code if needed |
| 9 | Update STATUS.md | — | docs only |

**One recipe per Wave 4 initial tranche:** do not land city-builder-lite in the same wave.

---

## 12. Physics / Canvas — separate track (unchanged)

Physics and Canvas recipes remain **out of Wave 4 scope**:

| Candidate | Status |
|-----------|--------|
| `game.canvas-arcade-lite` | Deferred — needs Physics/Canvas ADR |
| `game.physics-bounce-lite` | Deferred — needs Physics Game Pack design |
| `game.physics-slingshot` | Later |
| Fluid simulation, multiplayer, live AI NPC | Not near-term |

See [WAVE_3_DIRECTION_CHECKPOINT.md](WAVE_3_DIRECTION_CHECKPOINT.md) Option D. Author **`PHYSICS_GAME_PACK_ADR_DRAFT.md`** (or formal ADR) before any Canvas recipe — independent of Wave 4 tactics work.

---

## 13. Readiness decision

| Question | Answer |
|----------|--------|
| Is Wave 4 strategy/sim the right next lane? | **Yes** — after Wave 3 closeout and registry hardening |
| Is `game.turn-based-tactics-lite` the right first candidate? | **Yes, conditionally** — bounded grid tactics before city-builder |
| Is `game.city-builder-lite` ready? | **No** — defer beyond Wave 4 |
| Does this doc authorize schema or routing? | **No** |
| Does this doc change default v2 posture? | **No** — `HAM_BUILD_REGISTRY_V2_ENABLED` stays opt-in; v1 default preserved |

**Next artifact (recommended):** `TACTICS_GRID_AMBIGUITY_REVIEW.md` — positive/negative prompt fixtures; daily-puzzle-grid vs tactics vs planning-tool exclusions.

**Next implementation step (only after ambiguity review + explicit approval):** schema-only `game.turn-based-tactics-lite` — **not** in this commit unless separately requested.

---

## 14. Non-goals

This direction doc does **not** authorize:

- Landing `game.turn-based-tactics-lite` or `game.city-builder-lite` YAML
- Routing or intent.py changes
- Default Build Registry v2 enablement
- Public kit picker or Builder Studio registry UX
- API, frontend, or CI changes
- Templates or starter source files
- Committing generated app output from `/tmp/`
- Physics / Canvas recipes
- Multiplayer, accounts, or backend persistence
- Autonomous Hermes recipe mutation
- Reference checker CI enforcement (remains local/manual; phase-two polish is a separate optional workstream)

---

## 15. References

| Doc | Purpose |
|-----|---------|
| [STATUS.md](STATUS.md) | Live handoff — 14 recipes, checker, flag posture |
| [WAVE_3_COMPLETION_CHECKPOINT.md](WAVE_3_COMPLETION_CHECKPOINT.md) | Wave 3 closeout; deferred tactics/city-builder |
| [WAVE_3_DIRECTION_CHECKPOINT.md](WAVE_3_DIRECTION_CHECKPOINT.md) | Original strategy/sim Option B analysis |
| [WAVE_2_RETROSPECTIVE.md](WAVE_2_RETROSPECTIVE.md) | Grid/sim candidate notes |
| [DECK_BUILDER_LITE_READINESS_REVIEW.md](DECK_BUILDER_LITE_READINESS_REVIEW.md) | Readiness review template |
| [CARD_DECK_AMBIGUITY_REVIEW.md](CARD_DECK_AMBIGUITY_REVIEW.md) | Ambiguity review pattern to mirror for tactics/grid |
| [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md) | Route-after-approval policy |
| [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md) | Recipe authoring rules |
| [REFERENCE_CHECKER_IMPLEMENTATION_PLAN.md](REFERENCE_CHECKER_IMPLEMENTATION_PLAN.md) | Checker usage before/after schema land |
| [outcome-reports/game.resource-management-sim.manual-outcome.md](outcome-reports/game.resource-management-sim.manual-outcome.md) | Sim/city-builder drift warnings |
| [ADR-0016](../adr/0016-generative-build-kit-registry-v2.md) | Registry design |
| [ADR-0017](../adr/0017-build-registry-v2-opt-in-scaffold-wiring.md) | Opt-in scaffold wiring |
| [ADR-0018](../adr/0018-build-kit-evolution-loop-with-hermes.md) | Future Hermes evolution loop |
