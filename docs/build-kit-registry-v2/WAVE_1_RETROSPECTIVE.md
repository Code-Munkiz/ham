# Build Registry v2 Game Pack Wave 1 Retrospective

Practical checkpoint after completing the first five Game Pack recipes. Use this to decide Wave 2 scope, sequencing, and guardrails. For live status see [STATUS.md](STATUS.md).

**Checkpoint:** `origin/main` at `e959dc2f` — five recipes, 93 indexed modules, all routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`.

---

## Executive summary

Wave 1 proved that Build Registry v2 can describe **five meaningfully different browser-game patterns** using the same pack format: app-type recipes, mechanics, component contracts, validators, recovery playbooks, progress labels, and learning hooks.

All Wave 1 recipes **validate, compose, and render** under the 12k default budget. All five are **routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`** with narrow, recipe-specific intent matching. **v1 Builder Kits remain the default path** when the flag is unset or false.

HAM still **does not clone templates or starter source files**. Recipes are generative playbooks only; Lane A scaffolds custom code from composed context when routing succeeds.

---

## Wave 1 inventory

| Recipe id | Pattern tested | Composed modules | Routed? | Routing intent summary | Render length |
|-----------|----------------|------------------|---------|------------------------|---------------|
| `game.idle-incremental` | Idle / incremental / clicker / tycoon | 15 refs (4 mechanics) | Yes (narrow) | Idle, clicker, tycoon, passive income, earn-and-upgrade loops | ~8.8k |
| `game.trivia-timer` | Timed trivia / quiz game | 18 refs (5 mechanics) | Yes (narrow) | Timed trivia/quiz with game-like signals; excludes surveys, flashcards, generic forms | ~9.6k |
| `game.branching-narrative` | Branching story / CYOA | 18 refs (5 mechanics) | Yes (narrow) | Branching story, choices, CYOA, interactive fiction; excludes blogs, chatbots, live AI dungeon | ~10.3k |
| `game.memory-match` | Memory card matching | 20 refs (6 mechanics) | Yes (narrow) | Memory/matching/pair/flip-card games; excludes card battlers, poker, solitaire, flashcards | ~10.0k |
| `game.word-daily` | Daily word guessing / Wordle-style | 22 refs (7 mechanics) | Yes (narrow) | Daily word guessing, Wordle-style, letter feedback; generic “word game” excluded | ~10.9k |

**Pack total:** 93 indexed modules in [game-pack/registry-pack.yaml](game-pack/registry-pack.yaml) (shared stack kit + cross-recipe reuse included).

---

## What Wave 1 proved

- **Recipe format is repeatable** — each app type follows the same YAML shape (safety constraints, composed modules, build phases, acceptance criteria, out of scope).
- **Modules compose cleanly** — loader validates cross-references, dependency order topologically sorts, no orphan YAML in the pack.
- **Render output stays under budget** — all five renders are well under the 12k default cap (~8.8k–10.9k).
- **Routing can remain feature-flagged and narrow** — v2 only applies when `HAM_BUILD_REGISTRY_V2_ENABLED` is truthy **and** intent matches.
- **v1 fallback is available as a safety net** — every app type declares `legacy_v1_fallback: generic`; compose/render failures fall back silently.
- **Authoring and routing are separate lanes** — recipes landed schema-only first; routing was added one recipe at a time with explicit approval and tests.
- **The Game Pack covers different browser-game patterns** — economy loops, timed quizzes, narrative graphs, card grids, and word-guess feedback are distinct mechanic graphs, not one monolithic “game kit.”

---

## Recipe pattern coverage

| Recipe | What it tested |
|--------|----------------|
| **idle-incremental** | Economy, upgrades, passive income ticks, save/load, resource counters |
| **trivia-timer** | Static question set, countdown timer, answer validation, score and progression |
| **branching-narrative** | Story node graph, choice resolution, story flags, inventory-lite, ending resolution |
| **memory-match** | Card pair deck, flip state, interaction lock, match detection, move counter, victory |
| **word-daily** | Fixed-length guesses, keyboard input, duplicate-letter feedback, daily seed, attempt limit, win/loss |

All recipes reuse **`stack.dom-game-minimal`** and **`component.game-shell`** where appropriate — DOM-native React, no Canvas/Phaser in Wave 1.

---

## Routing lessons

- **Routing must stay conservative** — when in doubt, do not route; v1 is always acceptable.
- **Recipe-specific negatives matter** — each archetype needs exclusions so it does not steal prompts from siblings (e.g. trivia vs idle vs memory match).
- **Generic game prompts should not route** — `\bgame\b` alone is never sufficient.
- **Global negatives are useful but can block new signals** — `wordle` was initially in global negatives; word-daily routing required moving it to recipe-specific handling so Wordle-style prompts could route correctly.
- **Precedence order matters** — first match wins after global negatives.

**Current precedence:**

```txt
global negatives → trivia → idle → branching narrative → memory match → word daily
```

- **Tests are mandatory for every routed recipe** — positive prompts, negative prompts, cross-exclusion, flag off/on metadata, end-to-end scaffold context (`tests/test_build_registry_intent.py` and related scaffold tests).

Policy reference: [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md).

---

## What worked well

- **Schema-only first, routing second** — kept PRs reviewable and prevented accidental live routing.
- **Per-recipe validation** — `validate_game_pack_registry.py --app-type <id> --check` after every pack edit.
- **STATUS.md updates after each meaningful step** — handoff doc stayed aligned with `main`.
- **Warning-only CI** — registry tests and selected app-type pack validation surface signal without blocking merges during the pilot.
- **Manual smoke tests before routing** — scaffold context path verified before intent wiring landed.
- **Authoring Guide** — kept module kinds, indexing, and non-template language consistent across recipes.
- **Routing strategy doc** — explicit approval criteria prevented “recipe landed ⇒ automatically routed” drift.

---

## Pain points / friction

- **YAML volume grows quickly** — Wave 1 went from one recipe to 93 modules; indexing in `registry-pack.yaml` is manual.
- **Module indexing is manual** — easy to forget a new file in `module_index`; tests catch orphans but upkeep cost is real.
- **Render budget should be watched** — word-daily is ~10.9k; adding modules without tightening prose could breach 12k.
- **Routing tests are growing large** — `test_build_registry_intent.py` now covers five recipes × flag/metadata/e2e paths.
- **STATUS.md needs frequent upkeep** — every recipe and routing land requires a docs pass.
- **No JSON Schema yet** — YAML conventions are documented but not machine-schema’d beyond loader validation.
- **Validators/recovery are still conceptual** — `runner: conceptual`; not executed at build time.
- **Routing remains regex/pattern-based** — not semantic; false positives/negatives require human review of prompt fixtures.

---

## Risks to watch

- **Over-expanding recipe count** before feedback from real operator builds on routed recipes.
- **False-positive routing** — broad patterns that send SaaS/dashboard/education prompts to game recipes.
- **Prompt/context bloat** — composed playbook context competing with other scaffold instructions near 12k.
- **Stale docs** — STATUS, routing strategy, and this retrospective drifting from `intent.py` reality.
- **Recipe modules becoming too verbose** — guidance fields that inflate render size without improving generation quality.
- **Treating conceptual validators as executable** — implying live validation/recovery before runners exist.
- **Adding routing without explicit approval** — violates Wave 1 policy; recipe creation does not imply routing.
- **Letting Hermes evolution imply autonomous mutation** — ADR-0018 is future-facing; YAML changes remain human-reviewed commits only.

---

## Wave 2 candidate recipes

Possible next patterns (not approved; brainstorming only):

| Candidate | Notes |
|-----------|--------|
| `game.word-builder` / spelling challenge | Extends word-game family; letter/slot mechanics, different from daily guess grid |
| `game.daily-puzzle-grid` | Sudoku/nonogram-style grid state; tests spatial puzzle logic distinct from word-daily |
| `game.typing-speed-racer` | Typing WPM/challenge; must stay separate from word-daily negatives |
| `game.hangman-lite` | Classic hangman; small mechanic set, word-family adjacency |
| `game.card-deck-turn-based` | Turn-based card play; **not** memory match — higher false-positive risk with card routing |
| `game.resource-management-sim` | Expands idle into allocation/tradeoffs; closer to sim/dashboard UX |
| `game.educational-progression` | Lesson/quiz progression; high overlap risk with trivia unless carefully scoped |
| `game.ai-npc-story` | Live/generated narrative — **defer** until static-story Wave 1 patterns are stable in production |

### Recommended Wave 2 starters

1. **`game.hangman-lite` or `game.word-builder`** — extends the word-game family with low new engine risk; reuses keyboard/letter feedback patterns from word-daily where sensible.
2. **`game.daily-puzzle-grid`** — tests grid/state logic and daily-seed patterns without another word-guess clone.
3. **`game.resource-management-sim`** — stretches beyond idle into simulation loops; useful proof that the pack is not only arcade-minigame shaped.

Land each as **schema-only first**; route one at a time after the Wave 1 routing checklist passes.

---

## Recommended next steps

1. **Run a manual outcome report example** for one routed non-idle recipe — suggest starting with `game.trivia-timer` ([OUTCOME_FACTS.md](OUTCOME_FACTS.md), [examples/outcome-facts/](examples/outcome-facts/)).
2. **Consider CI ratchet** from warning-only to blocking only after confidence increases (registry tests + multi app-type validation).
3. **Add Wave 2 recipe #1 schema-only** — pick from recommended candidates above; follow [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md).
4. **Route Wave 2 recipes one at a time** after explicit approval — separate PR from schema landing.
5. **Consider lightweight JSON Schema / reference-checking** once YAML growth justifies formal schema beyond the Python loader.
6. **Keep v1 default** until an explicit product decision to enable `HAM_BUILD_REGISTRY_V2_ENABLED` broadly.

---

## Non-goals going forward

- No default Build Registry v2 enablement yet (`HAM_BUILD_REGISTRY_V2_ENABLED` stays off unless operator sets it).
- No public kit picker for registry v2 app types.
- No generic “game” router — every recipe stays narrowly matched.
- No templates or starter file cloning.
- No auto-generated Hermes PRs yet.
- No executable validator/recovery runners yet.
- No Canvas/Phaser/game-engine recipes until DOM-native Wave 1 patterns stabilize in operator use.

---

## References

| Doc | Purpose |
|-----|---------|
| [STATUS.md](STATUS.md) | Live handoff — recipes, routing, validation commands |
| [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md) | How to add recipes and modules |
| [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md) | Routing approval policy and checklist |
| [OUTCOME_FACTS.md](OUTCOME_FACTS.md) | Build outcome capture format (future Hermes loop) |
| [ADR-0016](../adr/0016-generative-build-kit-registry-v2.md) | Registry design |
| [ADR-0017](../adr/0017-build-registry-v2-opt-in-scaffold-wiring.md) | Opt-in scaffold wiring |
| [ADR-0018](../adr/0018-build-kit-evolution-loop-with-hermes.md) | Future Hermes evolution loop |
| [game-pack/README.md](game-pack/README.md) | Game Pack pilot layout and composition examples |
