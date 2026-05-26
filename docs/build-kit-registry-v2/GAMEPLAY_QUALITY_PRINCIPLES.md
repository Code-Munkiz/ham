# Gameplay Quality Principles for Build Registry v2

> **Persistent doctrine · DOM-native game-kit phase · Not a template · Not a recipe**

This document defines how HAM evaluates **generated gameplay quality** for Build Registry v2 DOM-native game recipes. It complements recipe YAML, routing strategy, scaffold quality guards, the reference checker, and per-recipe generated gate reviews. It does **not** replace those mechanisms and does **not** authorize new recipes, routing, or default v2 enablement.

**Doctrine date:** 2026-05-26 (UTC)  
**Baseline:** Wave 3 closed; Wave 4 strategy/sim lane open; **`game.turn-based-tactics-lite`** authored, routed, and generated-gate **Pass** on `origin/main` (latest known: `4e532c2d`).

---

## 1. Purpose

Build Registry v2 recipes are **generative playbooks**, not checked-in starter apps. Quality therefore depends on what the scaffold produces under a representative prompt, not on schema validity alone.

This document provides **persistent doctrine** for:

- What “playable” means for DOM-native generated games
- Which anti-patterns are unacceptable in generated output
- How recipe families differ in loop expectations
- How generated gate reviews, tests, and `scaffold_quality.py` relate to one another

Use this doc when:

- Authoring or reviewing a recipe family
- Writing readiness/ambiguity reviews before schema land
- Interpreting `/tmp/` generated gate outcomes
- Deciding whether a new detector belongs in `scaffold_quality.py`

This is **not** a template, not a recipe YAML file, and not runtime configuration.

---

## 2. Current posture

| Dimension | Posture |
|-----------|---------|
| **Primary kit focus** | **DOM-native** React/Vite-style games (grid, cards, timers, text, buttons, panels) |
| **Deferred** | Canvas rendering, physics engines, entity-component-system (ECS) as a hard requirement |
| **Registry v2** | **Opt-in** behind `HAM_BUILD_REGISTRY_V2_ENABLED` |
| **Default lane** | **v1** Builder Kit JSON when flag is off or unset |
| **Starter templates** | **None** — recipes are playbooks only |
| **Recipe inventory** | **15 recipes / 349 modules** (Game Pack) |
| **Reference checker** | Local/manual; **0 errors / 0 warnings** on current registry; not CI-blocking |
| **Generated output** | Must be reviewed in **`/tmp/`** before a routed recipe is considered complete; **never commit** generated app trees |
| **Downstream work** | Website/design-system polish comes **after** the DOM-native game-kit phase |

A recipe is not “done” when YAML validates and routing merges. It is done when a **generated gate review** shows a playable core loop under the canonical Wave prompt for that family.

---

## 3. Architecture default

Prefer **FSM-lite / reducer-style** gameplay loops over ad hoc component state for core rules.

### Canonical model

```text
state + action → nextState
```

- Keep **gameplay state canonical and observable** (reducer, context store, or equivalent single source of truth).
- Model **explicit phases** where helpful: `idle`, `playing`, `enemyTurn`, `reward`, `result`, etc.
- **Dispatch** primary player actions from UI controls; every meaningful reducer case should be reachable.
- Derive **win/loss/result** from **next** state values, not stale closures.
- Prefer **immutable updates** (`map`, `filter`, spread) over in-place mutation of nested units, HP, or deck arrays.

### What to avoid

- Scattering core rules across disconnected `useState` hooks with no shared reducer
- “Shell” components that render UI labels but never mutate canonical state
- Parallel copies of deck/hand/grid data that drift from reducer state

### ECS stance

**ECS is not required** for current DOM-native recipes. Small grid tactics, card hands, timers, and word slots fit reducer/FSM-lite models well.

ECS may be reconsidered later for **Canvas/physics/entity-heavy** games on a separate design track. Do not import ECS complexity into DOM-native doctrine prematurely.

---

## 4. Minimum playable loop

Every generated DOM-native game should satisfy this baseline unless the prompt explicitly scopes narrower (and the gate review documents the exception):

| Requirement | Expectation |
|-------------|-------------|
| **Seeded initial state** | Non-empty starting units, deck, grid, timer, or equivalent; seed/install paths must actually apply |
| **Visible primary state** | Player can see grid, hand, score, timer, or other core state driving decisions |
| **Wired player controls** | Buttons, cells, keys, or inputs dispatch actions that reach the reducer |
| **Meaningful transitions** | Primary actions change canonical state (not logs-only handlers) |
| **Feedback** | Moves, hits, misses, draws, allocations, etc. produce visible or logged feedback |
| **Result state** | Win/loss/completion/summary when the prompt requires it |
| **Restart / new run** | Resets **and reseeds** — not empty arrays, not no-op `INIT` |

If any row fails on a generated gate rerun, the recipe remains **Conditional pass** or **Hold** until repair guards or playbook guidance close the gap.

---

## 5. Anti-pattern taxonomy

These patterns are unacceptable in generated **primary gameplay** paths. Several are partially enforced by `src/ham/scaffold_quality.py`; all belong in doctrine regardless of detector coverage.

| Anti-pattern | Symptom | Why it fails |
|--------------|---------|--------------|
| **Component shell only** | UI layout renders; no canonical game state | Non-playable scaffold |
| **No-op reducers** | `return state` / `{...state}` stubs for primary actions | Actions exist but do nothing |
| **Reducer never dispatched** | `SELECT_UNIT`, `PLAY_CARD`, `ATTACK_UNIT`, etc. implemented but UI never calls them | Player cannot act |
| **Empty seeded state** | `units: []`, `deck: []`, empty grid with no mount-time init | Prompt promises content that is missing |
| **Seed declared, not installed** | `INIT_GAME` case or initial arrays exist but canonical state stays empty | False completeness |
| **Buttons without handlers** | Primary controls are inert | Broken affordances |
| **Log-only handlers** | `console.log` without state mutation | Fake interactivity |
| **In-place mutation** | `target.hp -= 1` on objects still referenced by state | Stale UI, broken time-travel/debug, inspector flags |
| **Stale closure result checks** | Win/loss read pre-mutation HP/score | Wrong outcomes |
| **Result UI without transition** | Panel exists; reducer never sets result phase | Misleading UX |
| **Restart clears without reseed** | `RESTART` → empty state or noop `INIT` | New run is broken |
| **Disconnected reward pools** | `rewards = []` never wired to post-encounter choice | Deck-builder loop incomplete |
| **Missing enemy/opponent turn** | Player turns only; prompt asked for opponent phase | Incomplete tactics/card/sim loop |
| **Missing win/loss path** | Combat/resource loop with no terminal condition | Unbounded or confusing play |
| **Prompt-family drift** | Chess logic on tactics prompt, dashboard on sim prompt, etc. | Wrong recipe archetype |

Gate reviews should name the anti-pattern, cite file evidence, and map to inspector codes when available.

---

## 6. Recipe-family expectations

Concise expectations for routed DOM-native families. See linked ambiguity/readiness reviews for gate prompts and exclusion notes.

### Card / deck battle games (`game.card-deck-turn-based`)

- Non-empty shuffled deck and starting hand
- Draw/play/discard mutate canonical piles
- Card effects change HP or resources
- Visible win when enemy HP reaches zero (or stated goal)
- Restart resets deck, hand, discard, and result

### Deck-builder games (`game.deck-builder-lite`)

- Starter deck + playable opening hand
- Encounters consume cards; rewards append to deck
- Discard pile tracked on play
- Run/encounter progress visible
- Post-win reward choice wired to deck mutation
- Restart/new run reseeds deck, discard, and run state

### Timing / reaction / rhythm games (`game.reaction-time-challenge`, `game.rhythm-tap-lite`)

- Explicit timer or cue window (not unbounded elapsed counters when prompt specifies duration)
- Miss/false-start feedback beyond silent streak reset
- Final score/metrics derived from canonical tallies at round end
- Result panel + retry/play-again

### Word games (`game.word-daily`, `game.hangman-lite`, `game.word-builder`, `game.typing-speed-racer`)

- Prompt-specific core mechanic wired (guess feedback, letter reveals, slot validation, WPM/accuracy)
- Invalid input handled without breaking state
- Win/loss or summary when prompt requires it
- Avoid routing-family drift (Wordle vs hangman vs typing tutor)

### Resource / sim games (`game.resource-management-sim`, `game.idle-incremental`)

- Allocations and ticks change resources meaningfully
- Production/conversion rules affect totals over time
- Win/survival/goal or run summary when prompt requires it
- Reject dashboard/inventory-app shells without game loop

### Grid / tactics games (`game.turn-based-tactics-lite`, `game.daily-puzzle-grid`, `game.memory-match`)

- **Tactics:** fixed grid, seeded player + enemy units, selection, constrained move/attack, enemy turn, battle result, restart reseed
- **Daily/grid puzzle:** cell rules, clue/progress state, completion result
- **Memory match:** deck/grid of pairs, flip/match mutations, completion detection

Family-specific gate reviews live under [outcome-reports/](outcome-reports/). **`game.turn-based-tactics-lite`** reference: [game.turn-based-tactics-lite.wave4-gate-review.md](outcome-reports/game.turn-based-tactics-lite.wave4-gate-review.md) (**Pass**).

---

## 7. Generated gate criteria

Each **routed** recipe requires a **local generated gate review** before the family is treated as complete. Reviews use existing scaffold APIs with `HAM_BUILD_REGISTRY_V2_ENABLED=true` and write artifacts only under **`/tmp/`**.

### Checklist

| Criterion | Pass expectation |
|-----------|------------------|
| **Route correctness** | `select_registry_v2_app_type_for_prompt` returns intended recipe id |
| **v2 context used** | Scaffold context source is v2; v1 fallback not used for matched prompt |
| **Core loop present** | Minimum playable loop (§4) materially present |
| **Controls wired** | Primary actions dispatched from UI |
| **State mutates** | No no-op primary reducers; immutable updates preferred |
| **Result / restart** | Win/loss/result and restart/new-run reseed when prompt requires |
| **No drift** | Excluded prompt families absent (dashboard, wrong genre, etc.) |
| **Inspector** | `inspect_generated_scaffold_quality()` clean, or remaining issues documented as false positives with evidence |
| **Artifact hygiene** | Generated files stay local; not committed |

### Gate decisions

| Decision | Meaning |
|----------|---------|
| **Pass** | Checklist satisfied; inspector clean or documented false positives only |
| **Conditional pass** | Material loop improved; known gaps remain — not production-ready claim |
| **Hold** | Shell/non-playable or wrong route/context — block recipe completion claim |

Generated gates are **manual/local** today — not CI-blocking (see §10).

---

## 8. Test-first influence

Quality improves when tests and reviews **lead** implementation rather than chase LLM output.

1. **Readiness / ambiguity reviews** should define gate prompts, exclusions, and acceptance rows **before** recipe YAML lands where practical ([TACTICS_GRID_AMBIGUITY_REVIEW.md](TACTICS_GRID_AMBIGUITY_REVIEW.md) is the reference pattern).
2. **Observed generated failures** should become **detector + test candidates** in `tests/test_scaffold_quality.py` when repeated or high-risk ([GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md](GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md)).
3. **Tests pin intended behavior**, not merely mirror one LLM artifact — fixtures should encode family rules (e.g. Manhattan move range, immutable attack, restart reseed) independent of a single `/tmp/` run.

Routing tests (`tests/test_build_registry_intent.py`, etc.) prove **prompt → recipe** discipline. Scaffold quality tests prove **output → playable** discipline. Both are required; neither replaces generated gate review.

---

## 9. Scaffold quality guard relationship

| Layer | Role |
|-------|------|
| **This document** | Broad doctrine — architecture, families, gate criteria, deferrals |
| **`src/ham/scaffold_quality.py`** | Automated post-output inspection + optional one-pass repair prompt |
| **Generated gate reviews** | Human-readable evidence bundle per recipe/prompt |
| **Reference checker** | Registry/schema/module reference integrity — not gameplay |

### How they interact

- `inspect_generated_scaffold_quality()` enforces a **subset** of §5 anti-patterns (no-op reducers, empty seeds, tactics/card/deck/rhythm/timer families, import/export mismatches, etc.).
- `maybe_repair_generated_scaffold()` runs when `HAM_SCAFFOLD_QUALITY_REPAIR` is not disabled; **`HAM_SCAFFOLD_QUALITY_REPAIR=false`** preserves inspect-only behavior.
- **Not every principle needs immediate detector support.** Add detectors when failures are **repeated**, **high-severity**, or **cheap to signal** without excessive false positives.
- Doctrine may ahead of code; detectors should cite doctrine sections when new codes are added.

When doctrine and inspector diverge, fix **false positives** with evidence (as in the tactics `type: 'player'` / `CELL_CLICK` attack-range pass) rather than weakening family rules.

---

## 10. What not to overbuild yet

Explicit deferrals — do not treat absence as a gap to close in this phase:

| Deferred | Rationale |
|----------|-----------|
| **Hard ECS requirement** | DOM-native recipes fit reducer/FSM-lite; ECS is for a future Canvas/physics track |
| **Canvas / VLM testing** | DOM-native focus; visual ML evaluation is out of scope |
| **Pixel-perfect visual regression** | Gameplay correctness precedes cosmetic baselines |
| **CI-blocking generated gates** | Gates are local/manual; CI runs registry + scaffold unit tests only |
| **Full app validator claim** | No assertion that every generated file is production-shippable without review |

Website polish, design-system extraction, and Builder Studio surfacing follow **after** DOM-native game-kit quality is trustworthy recipe-by-recipe.

---

## 11. References

| Document | Relevance |
|----------|-----------|
| [WAVE_3_COMPLETION_CHECKPOINT.md](WAVE_3_COMPLETION_CHECKPOINT.md) | Wave 3 closeout; quality guard + reference checker baseline |
| [WAVE_4_STRATEGY_SIM_DIRECTION.md](WAVE_4_STRATEGY_SIM_DIRECTION.md) | Wave 4 strategy/sim lane; tactics-first; Canvas/physics deferred |
| [TACTICS_GRID_AMBIGUITY_REVIEW.md](TACTICS_GRID_AMBIGUITY_REVIEW.md) | Readiness/gate pattern for grid tactics |
| [GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md](GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md) | Scaffold quality gap closure narrative |
| [outcome-reports/game.turn-based-tactics-lite.wave4-gate-review.md](outcome-reports/game.turn-based-tactics-lite.wave4-gate-review.md) | Wave 4 tactics generated gate (**Pass**) |
| [REGISTRY_REFERENCE_CHECKER_PROPOSAL.md](REGISTRY_REFERENCE_CHECKER_PROPOSAL.md) | Reference checker scope |
| [REFERENCE_CHECKER_IMPLEMENTATION_PLAN.md](REFERENCE_CHECKER_IMPLEMENTATION_PLAN.md) | Checker implementation status |
| [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md) | Prompt routing approval discipline |
| [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md) | Recipe YAML authoring rules |
| [STATUS.md](STATUS.md) | Live registry/routing/checker snapshot |

**Related code (read-only context — not modified by this doctrine):**

- `src/ham/scaffold_quality.py` — generated output inspectors + repair prompts
- `src/ham/build_registry/intent.py` — narrow v2 routing
- `scripts/check_build_registry_references.py` — local reference checker
