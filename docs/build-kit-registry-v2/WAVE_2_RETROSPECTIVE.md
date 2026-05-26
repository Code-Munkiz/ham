# Build Registry v2 Game Pack Wave 2 Retrospective

Practical checkpoint after completing the second five Game Pack recipes. Use this to decide Wave 3 scope, sequencing, and guardrails. For live status see [STATUS.md](STATUS.md). For Wave 1 context see [WAVE_1_RETROSPECTIVE.md](WAVE_1_RETROSPECTIVE.md).

**Checkpoint:** `origin/main` at `20372372` — ten recipes, 219 indexed modules, all routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`.

---

## Executive summary

Wave 2 extended the DOM-native Game Pack beyond Wave 1’s core loops into **grid logic**, **resource simulation**, **hangman-style reveal state**, **typing-speed timing**, and **word-building mechanics**.

All Wave 2 recipes **validate, compose, and route** behind `HAM_BUILD_REGISTRY_V2_ENABLED` with narrow, recipe-specific intent matching. **v1 Builder Kits remain the default path** when the flag is unset or false.

HAM still **does not clone templates or starter source files**. Recipes are generative playbooks only; Lane A scaffolds custom code from composed context when routing succeeds.

Wave 2 followed the **schema-first, route-after-approval** rhythm established in Wave 1 — each recipe landed as validated schema before routing was added in a separate explicit step.

---

## Wave 2 inventory

| Recipe id | Pattern tested | Composed modules | Routed? | Routing intent summary | Render length |
|-----------|----------------|------------------|---------|------------------------|---------------|
| `game.daily-puzzle-grid` | Daily grid logic puzzle | 23 refs (7 mechanics) | Yes (narrow) | Daily/grid/logic/cell/rule/clue signals; excludes dashboard grids, CSS layouts, data tables, crossword, word search | ~11.4k |
| `game.resource-management-sim` | Resource management simulation game | 25 refs (8 mechanics) | Yes (narrow) | Resource/allocation/production/colony/factory/farm sim with game signals; excludes SaaS dashboards, inventory apps, finance/trading/spreadsheets | ~10.9k |
| `game.hangman-lite` | Hangman / hidden-word guessing | 19 refs (6 mechanics) | Yes (narrow) | Hangman / hidden-word / letter-guessing; Wordle/daily-word routes to `game.word-daily`; excludes crossword, word search, typing, flashcards | ~8.8k |
| `game.typing-speed-racer` | Typing speed / WPM challenge | 24 refs (8 mechanics) | Yes (narrow) | Typing speed / WPM / accuracy / timer / streak challenge; excludes typing tutor, generic typing app, text editor, dashboard | ~10.4k |
| `game.word-builder` | Word building / spelling challenge | 25 refs (8 mechanics) | Yes (narrow) | Word-building / spelling / letter-pool / letter-tile / word-slot signals; generic “word game” alone excluded | ~11.2k |

**Pack total:** 219 indexed modules in [game-pack/registry-pack.yaml](game-pack/registry-pack.yaml) (Wave 1: 93 modules; Wave 2 added ~126 modules across five recipes plus shared reuse).

**Full Game Pack (Wave 1 + Wave 2):**

| Wave | Recipes |
|------|---------|
| Wave 1 | `game.idle-incremental`, `game.trivia-timer`, `game.branching-narrative`, `game.memory-match`, `game.word-daily` |
| Wave 2 | `game.daily-puzzle-grid`, `game.resource-management-sim`, `game.hangman-lite`, `game.typing-speed-racer`, `game.word-builder` |

---

## What Wave 2 proved

- **DOM-native recipes can cover deeper state/rule systems** — grid constraints, resource pools, reveal state, timed input streams, and letter-pool validation all fit the same pack format without Canvas or physics.
- **Grid/constraint logic can fit under the render budget** — `game.daily-puzzle-grid` at ~11.4k shows spatial puzzle guidance is viable near the 12k cap with careful prose.
- **Sim/resource-management logic fits the registry without dashboard/app semantics** — `game.resource-management-sim` describes allocation, production chains, and goals as a playable sim, not a SaaS dashboard.
- **Word-family recipes can remain distinct through routing negatives and adaptive policy** — daily word guessing, hangman, typing speed, and word-building coexist with explicit cross-recipe exclusions and separate mechanic graphs.
- **Routing scale is possible but the intent test suite is getting large** — ten routed recipes × positive/negative/cross-exclusion/flag/metadata/e2e paths is manageable but no longer trivial.
- **Schema-first / routing-second process still works after ten recipes** — no recipe was routed at schema landing; each routing land was a separate reviewed commit with tests.

---

## Recipe pattern coverage

| Recipe | What it tested |
|--------|----------------|
| **daily-puzzle-grid** | Grid state, cell interaction, constraint rules, mistake tracking, hint system, completion detection, daily seed |
| **resource-management-sim** | Resource pools, capacity limits, allocation decisions, production chains, turn/tick loop, upgrades, event modifiers, goal/failure state |
| **hangman-lite** | Hidden word, letter guessing, duplicate-guess prevention, reveal state, wrong guess limit, win/loss resolution |
| **typing-speed-racer** | Prompt set, timer/race clock, typing input stream, mistake tracking, accuracy scoring, WPM calculation, streak combo, result state |
| **word-builder** | Letter pool, word-slot construction, word validation, submission attempts, duplicate submission blocking, scoring, hint reveal, level progression, result state |

All Wave 2 recipes reuse **`stack.dom-game-minimal`** and **`component.game-shell`** where appropriate — DOM-native React, no Canvas/Phaser in Wave 2.

---

## Routing lessons from Wave 2

- **Recipe-specific negatives are now essential** — with ten recipes, each archetype needs explicit exclusions so siblings do not steal prompts (especially within the word-family cluster).
- **Lowest-precedence routing helped prevent broad newer recipes from stealing earlier ones** — word-builder and typing-speed-racer land last so they cannot preempt hangman, word-daily, or resource sim matches.
- **Generic prompts should still fall back to v1** — `\bgame\b`, `\bword game\b`, `\bgrid\b`, `\bpuzzle\b`, and `\bmanagement app\b` alone are never sufficient.
- **Word-family overlap requires careful separation:**
  - **`game.word-daily`** — daily word guessing / Wordle-style / letter feedback
  - **`game.hangman-lite`** — hidden word / letter guessing / reveal state
  - **`game.typing-speed-racer`** — WPM / accuracy / timed typing challenge
  - **`game.word-builder`** — letter pool / word slots / valid submissions / spelling challenge
- **Dashboard/app prompts must not route to `game.resource-management-sim`** — finance dashboards, inventory apps, spreadsheets, and trading platforms need global and recipe-specific negatives.
- **Grid/layout/data-table prompts must not route to `game.daily-puzzle-grid`** — CSS grids, dashboard layouts, and data tables are excluded unless cell/constraint/clue signals appear.
- **Tests are now the main guardrail** — `tests/test_build_registry_intent.py` plus scaffold context tests are the primary defense against routing drift; regex alone is not enough at this scale.

**Current precedence:**

```txt
global negatives → trivia → idle → branching narrative → memory match → word daily
→ daily puzzle grid → resource management sim → hangman lite → typing speed racer → word builder
```

Policy reference: [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md).

---

## What worked well

- **Schema-first then routing approval** — kept PRs reviewable; recipe creation never implied routing.
- **Adaptive policy fields on every app type** — hard constraints, soft defaults, user-overridable knobs, clarification triggers, and conflict policy documented per recipe (schema only until a runtime interpreter lands).
- **STATUS.md updates after each meaningful step** — handoff doc stayed aligned with `main` through schema and routing lands.
- **Conservative negatives and cross-recipe tests** — each routing land added sibling exclusions and parametrized cross-exclusion fixtures.
- **Keeping Wave 2 DOM-native** — no Canvas/physics dependency; all recipes use `stack.dom-game-minimal`.
- **Avoiding card-deck ambiguity until later** — `game.card-deck-turn-based` was explicitly deferred rather than rushed into Wave 2.
- **Explicit non-template language** — every app type repeats that output is custom-generated, not cloned from starter trees.

---

## Pain points / friction

- **Registry grew to 219 modules** — manual indexing in `registry-pack.yaml` scales poorly; orphan detection helps but upkeep cost is real.
- **Render sizes for grid and word-builder are near the 12k cap** — `game.daily-puzzle-grid` (~11.4k) and `game.word-builder` (~11.2k) leave little headroom for module growth without tightening prose.
- **Routing tests are much larger** — `tests/test_build_registry_intent.py` now covers ten recipes × flag/metadata/e2e paths (~324 intent/scaffold tests combined).
- **Manual registry-pack indexing continues to be overhead** — easy to forget a new YAML file in `module_index`.
- **STATUS.md update cadence is useful but repetitive** — every recipe and routing land requires a docs pass.
- **No JSON Schema / reference checker yet** — YAML conventions are documented and loader-validated but not formally schema’d beyond Python validation.
- **Validators/recovery still conceptual** — `runner: conceptual`; not executed at build time.
- **No real outcome reports yet from actual generated builds** — idle success example exists; no Wave 2 routed recipe has a manual outcome report from a real operator build.

---

## Risks to watch

- **Context bloat** — composed playbook context for grid and word-builder recipes competes with other scaffold instructions near the 12k render cap.
- **False-positive routing** — broad patterns that send SaaS/dashboard/education prompts to game recipes; worsens as recipe count grows.
- **Word-family overlap** — new word-adjacent recipes (crossword, word search, scrabble-like) could collide with four existing word-family routes.
- **App/dashboard prompts accidentally routing to game recipes** — especially resource sim and daily puzzle grid.
- **Wave 3 taking on Canvas/physics too early** — DOM-native patterns are not yet validated in real operator builds; jumping to physics stacks adds engine risk.
- **Schema growth without generated-build feedback** — adding modules without outcome reports from actual scaffolds may inflate context without improving generation quality.
- **Treating conceptual validators as executable** — implying live validation/recovery before runners exist.
- **Too many regexes before considering a clearer intent model** — ten recipes × dozens of patterns is maintainable today but may need a structured intent layer before Wave 3 doubles the count.

---

## Wave 3 candidate directions

Possible next patterns (not approved; brainstorming only):

### Card / deck systems

| Candidate | Notes |
|-----------|--------|
| `game.card-deck-turn-based` | Turn-based card play; **high false-positive risk** with memory match and generic “card game” prompts — requires ambiguity review first |
| `game.deck-builder-lite` | Deck construction + run loop; distinct from memory match but card-family overlap |

### Strategy / sim

| Candidate | Notes |
|-----------|--------|
| `game.turn-based-tactics-lite` | Grid movement + turn order; overlaps daily-puzzle-grid spatial signals |
| `game.city-builder-lite` | Extends resource sim into placement/building; dashboard/placement UX risk |

### Arcade DOM-lite

| Candidate | Notes |
|-----------|--------|
| `game.reaction-time-challenge` | Simple DOM timing/reflex; low engine risk |
| `game.rhythm-tap-lite` | Tap timing + score; audio/timing edge cases |

### Canvas / physics prep

| Candidate | Notes |
|-----------|--------|
| `game.canvas-arcade-lite` | First Canvas recipe; needs stack kit decision |
| `game.physics-bounce-lite` | Simple physics loop; needs physics stack ADR |
| `game.physics-slingshot` | Later; higher complexity |

### Not yet

- Fluid simulation / Where’s My Water-style mechanics
- Multiplayer or live services
- Live AI NPC story generation

### Recommendations

1. **Do not jump straight to physics yet** — DOM-native Wave 1 + Wave 2 patterns have no real outcome reports from operator builds.
2. **If staying DOM-native, next candidate should be `game.card-deck-turn-based` only after ambiguity review** — card-family routing overlap with memory match and generic card prompts is the highest-risk near-term addition.
3. **If preparing for physics, first create a separate Physics Game Pack ADR or design doc** before adding recipes — Canvas/physics stack, render budget, and safety constraints need their own design lane.

Land any Wave 3 recipe as **schema-only first**; route one at a time after explicit approval.

---

## Recommended next steps

1. **Create one manual outcome report example for a routed Wave 2 recipe** — suggest starting with `game.resource-management-sim` or `game.typing-speed-racer` ([OUTCOME_FACTS.md](OUTCOME_FACTS.md), [examples/outcome-facts/](examples/outcome-facts/)).
2. **Consider adding a lightweight reference-checker / JSON Schema for registry modules** — formalize YAML conventions beyond the Python loader as module count grows.
3. **Consider CI ratchet from warning-only to blocking** after confidence increases (registry tests + multi app-type validation).
4. **Decide Wave 3 direction:**
   - card/deck DOM-native (after ambiguity review)
   - deeper sim/strategy
   - Canvas/physics design work (ADR first)
5. **Keep v1 default** until an explicit product decision to enable `HAM_BUILD_REGISTRY_V2_ENABLED` broadly.

---

## Non-goals going forward

- No default Build Registry v2 enablement yet (`HAM_BUILD_REGISTRY_V2_ENABLED` stays off unless operator sets it).
- No public kit picker for registry v2 app types.
- No generic game router — every recipe stays narrowly matched.
- No templates or starter file cloning.
- No auto-generated Hermes PRs yet.
- No executable validator/recovery runners yet.
- No physics/fluid simulation without a dedicated stack/design doc.
- No multiplayer/live services until scoped separately.

---

## References

| Doc | Purpose |
|-----|---------|
| [STATUS.md](STATUS.md) | Live handoff — recipes, routing, validation commands |
| [WAVE_1_RETROSPECTIVE.md](WAVE_1_RETROSPECTIVE.md) | Wave 1 checkpoint — first five recipes and lessons |
| [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md) | How to add recipes and modules |
| [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md) | Routing approval policy and checklist |
| [OUTCOME_FACTS.md](OUTCOME_FACTS.md) | Build outcome capture format (future Hermes loop) |
| [ADR-0016](../adr/0016-generative-build-kit-registry-v2.md) | Registry design |
| [ADR-0017](../adr/0017-build-registry-v2-opt-in-scaffold-wiring.md) | Opt-in scaffold wiring |
| [ADR-0018](../adr/0018-build-kit-evolution-loop-with-hermes.md) | Future Hermes evolution loop |
| [game-pack/README.md](game-pack/README.md) | Game Pack pilot layout and composition examples |
