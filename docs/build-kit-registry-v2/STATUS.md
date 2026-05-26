# Build Registry v2 — Status & Handoff

Practical snapshot of where Build Kit Registry v2 stands. For authoring rules see [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md). For architecture see [ADR-0016](../adr/0016-generative-build-kit-registry-v2.md), [ADR-0017](../adr/0017-build-registry-v2-opt-in-scaffold-wiring.md), and [ADR-0018](../adr/0018-build-kit-evolution-loop-with-hermes.md).

---

## 1. Current status

- **Build Registry v2 exists and is tested** — loader, composer, renderer, opt-in scaffold wiring, and narrow prompt routing are in place.
- **Game Pack has eleven recipes** — **247 indexed modules** total.
- **Ten current Game Pack recipes are narrowly routable** behind `HAM_BUILD_REGISTRY_V2_ENABLED` when prompt intent clearly matches idle/incremental/clicker/tycoon, timed trivia/quiz game, branching/choice/story, memory card matching, daily word guessing / Wordle-style patterns, daily/grid/logic puzzle patterns, resource-management simulation game patterns, hangman / hidden-word / letter-guessing patterns, typing speed / WPM / typing challenge patterns, or word-building / spelling / letter-pool patterns. **Wave 2 includes** **`game.daily-puzzle-grid`**, **`game.resource-management-sim`**, **`game.hangman-lite`**, **`game.typing-speed-racer`**, and **`game.word-builder`** (schema + routing complete). **Wave 3 candidate:** **`game.card-deck-turn-based`** — schema-only (not routed); see [CARD_DECK_AMBIGUITY_REVIEW.md](CARD_DECK_AMBIGUITY_REVIEW.md).
- **Default behavior remains v1** — when the flag is unset or false, Lane A uses existing Builder Kit JSON (`src/ham/data/builder_kits/`).
- **No templates or starter source files** — recipes are generative playbooks only; HAM does not clone checked-in starter trees per kit.
- **Adaptive policy fields on all Wave 1 app types** — `hard_constraints`, `soft_defaults`, `user_overridable`, `clarify_if_changed`, `out_of_scope_unless_explicit`, and `conflict_policy` document override precedence (schema only; not interpreted at runtime yet).

---

## 2. What exists

| Asset | Location |
|-------|----------|
| **ADRs** | [0016](../adr/0016-generative-build-kit-registry-v2.md) (registry design), [0017](../adr/0017-build-registry-v2-opt-in-scaffold-wiring.md) (opt-in scaffold wiring), [0018](../adr/0018-build-kit-evolution-loop-with-hermes.md) (future Hermes evolution loop) |
| **Authoring Guide** | [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md) |
| **Game Pack** | [game-pack/](game-pack/) — **11 recipes** (10 routed when flag on, 1 schema-only), **247 modules** |
| **Outcome facts / evolution loop docs** | [OUTCOME_FACTS.md](OUTCOME_FACTS.md), [examples/outcome-facts/](examples/outcome-facts/), [examples/hermes-critique-prompt.md](examples/hermes-critique-prompt.md) |
| **Validation script** | `scripts/validate_game_pack_registry.py` |
| **Internal package** | `src/ham/build_registry/` (`loader`, `validate`, `compose`, `render`, `scaffold_context`, `intent`) |
| **Tests** | `tests/test_build_registry.py` (57 cases), `tests/test_build_registry_scaffold_context.py`, `tests/test_builder_llm_scaffold_registry_context.py`, `tests/test_builder_llm_scaffold_registry_manual_smoke.py`, `tests/test_build_registry_intent.py` |
| **CI** | `.github/workflows/ci.yml` — warning-only `pytest tests/test_build_registry.py` + idle app-type validation (`continue-on-error: true`) |

---

## 3. Recipes

| Recipe id | Status | Routed? | Route gate | Render length | Notes |
|-----------|--------|---------|------------|---------------|-------|
| `game.idle-incremental` | Validated | Yes (narrow) | `HAM_BUILD_REGISTRY_V2_ENABLED` + idle/clicker/tycoon prompt match | ~8.8k chars | Pilot recipe; v2 playbook context injected at scaffold when routing succeeds |
| `game.trivia-timer` | Validated | Yes (narrow) | `HAM_BUILD_REGISTRY_V2_ENABLED` + narrow timed trivia/quiz intent | ~9.6k chars | Conservative timed trivia/quiz routing; v1 fallback preserved |
| `game.branching-narrative` | Validated | Yes (narrow) | `HAM_BUILD_REGISTRY_V2_ENABLED` + narrow branching/choice/story intent | ~10.3k chars | Conservative branching narrative / CYOA / interactive-fiction routing; v1 fallback preserved |
| `game.memory-match` | Validated | Yes (narrow) | `HAM_BUILD_REGISTRY_V2_ENABLED` + narrow memory card matching intent | ~10.0k chars | Conservative memory card / pair matching / flip-card routing; v1 fallback preserved |
| `game.word-daily` | Validated | Yes (narrow) | `HAM_BUILD_REGISTRY_V2_ENABLED` + narrow daily word guessing / Wordle-style intent | ~10.9k chars | Conservative daily word / Wordle-style routing; generic “word game” excluded; v1 fallback preserved |
| `game.daily-puzzle-grid` | Validated | Yes (narrow) | `HAM_BUILD_REGISTRY_V2_ENABLED` + narrow daily/grid/logic puzzle intent | ~11.4k chars | Conservative daily/grid/logic/cell/rule/clue routing; generic “grid”, “puzzle”, and “daily game” excluded; v1 fallback preserved |
| `game.resource-management-sim` | Validated | Yes (narrow) | `HAM_BUILD_REGISTRY_V2_ENABLED` + narrow resource-management simulation game intent | ~10.9k chars | Conservative resource/allocation/production/colony/factory/farm management sim routing; dashboards, inventory apps, finance/trading/spreadsheets excluded; v1 fallback preserved |
| `game.hangman-lite` | Validated | Yes (narrow) | `HAM_BUILD_REGISTRY_V2_ENABLED` + narrow hangman / hidden-word / letter-guessing intent | ~8.8k chars | Conservative hangman / hidden-word / letter-guessing routing; Wordle/daily-word routes to `game.word-daily`; crossword, word search, typing, flashcard, trivia, memory, idle, dashboard prompts excluded; v1 fallback preserved |
| `game.typing-speed-racer` | Validated | Yes (narrow) | `HAM_BUILD_REGISTRY_V2_ENABLED` + narrow typing speed / WPM / typing challenge intent | ~10.4k chars | Conservative typing speed / WPM / accuracy / timer challenge routing; generic typing app, typing tutor, and dashboard prompts excluded; v1 fallback preserved |
| `game.word-builder` | Validated | Yes (narrow) | `HAM_BUILD_REGISTRY_V2_ENABLED` + narrow word-building / spelling / letter-pool intent | ~11.2k chars | Conservative word-builder / spelling / letter-pool / letter-tile / word-slot routing; generic “word game” alone excluded; v1 fallback preserved |
| `game.card-deck-turn-based` | Validated | No | — (routing not added; requires explicit approval + tests) | ~11.0k chars | Wave 3 turn-based card battle; draw/hand/discard/turn/card-play; no gambling/casino/marketplace/flashcard/pitch-deck/dashboard; v1 fallback preserved |

Eleven recipe renders are under the 12k default budget.

---

## 4. Runtime behavior

- **v1 Builder Kits remain default** for all Lane A scaffolds unless v2 path is explicitly enabled.
- **Flag off (unset/false):** all prompts remain v1 — no `registry_v2_app_type` metadata is added by routing.
- **Build Registry v2 affects scaffold context only** when **both** are true:
  1. `HAM_BUILD_REGISTRY_V2_ENABLED` is truthy
  2. Plan metadata includes `registry_v2_app_type` (set by routing or manual metadata)
- **Flag on + idle prompt:** routing adds `registry_v2_app_type: game.idle-incremental` when the prompt clearly matches idle/incremental/clicker/tycoon intent (with negative-pattern exclusions for quiz/trivia, SaaS, etc.).
- **Flag on + timed trivia/quiz prompt:** routing adds `registry_v2_app_type: game.trivia-timer` when the prompt clearly matches conservative timed trivia/quiz game intent (surveys, forms, flashcards, and generic quiz without game signals are excluded).
- **Flag on + branching/choice/story prompt:** routing adds `registry_v2_app_type: game.branching-narrative` when the prompt clearly matches conservative branching narrative / CYOA / interactive-fiction intent (blogs, chatbots, generic writing apps, generic RPGs, and live AI dungeon prompts are excluded).
- **Flag on + memory card matching prompt:** routing adds `registry_v2_app_type: game.memory-match` when the prompt clearly matches conservative memory card / pair matching / flip-card intent (card battlers, trading cards, flashcards, poker, solitaire, and generic card games without memory signals are excluded).
- **Flag on + daily word guessing / Wordle-style prompt:** routing adds `registry_v2_app_type: game.word-daily` when the prompt clearly matches conservative daily word guessing / Wordle-style intent (crossword, word search, flashcards, typing games, dictionary apps, and generic “word game” without guessing/feedback signals are excluded).
- **Flag on + daily/grid/logic puzzle prompt:** routing adds `registry_v2_app_type: game.daily-puzzle-grid` when the prompt clearly matches conservative daily/grid/logic puzzle intent (dashboard grids, CSS layouts, data tables, crossword, word search, Tetris, Minesweeper, and generic “grid”, “puzzle”, or “daily game” without cell/rule/clue signals are excluded).
- **Flag on + resource-management simulation game prompt:** routing adds `registry_v2_app_type: game.resource-management-sim` when the prompt clearly matches conservative resource-management / allocation / production-chain / colony / factory / farm sim intent (SaaS dashboards, inventory apps, finance dashboards, trading apps, spreadsheets, live markets, multiplayer economy, idle clickers, and generic “management app” without game/sim signals are excluded).
- **Flag on + hangman / hidden-word / letter-guessing prompt:** routing adds `registry_v2_app_type: game.hangman-lite` when the prompt clearly matches conservative hangman / hidden-word / letter-guessing intent (Wordle/daily-word routes to `game.word-daily`; crossword, word search, typing speed/WPM/challenge, flashcard, trivia, memory, idle, dashboard, dictionary, and writing-app prompts are excluded).
- **Flag on + typing speed / WPM / typing challenge prompt:** routing adds `registry_v2_app_type: game.typing-speed-racer` when the prompt clearly matches conservative typing speed / WPM / accuracy / timer / streak challenge intent (Wordle, hangman, crossword, word search, flashcards, trivia, dictionary apps, writing apps, text editors, typing tutor, generic typing app, and dashboard prompts are excluded).
- **Flag on + word-builder / spelling / letter-pool prompt:** routing adds `registry_v2_app_type: game.word-builder` when the prompt clearly matches conservative word-building / spelling / letter-pool / letter-tile / word-slot intent (Wordle/daily-word routes to `game.word-daily`; hangman, typing speed/WPM/challenge, crossword, word search, flashcards, dictionary apps, writing apps, trivia, memory, idle, dashboard prompts, and generic “word game” without builder signals are excluded).
- **Flag on + non-matching prompt:** no v2 metadata from routing — v1 kit context is used.
- **Bad v2 app types fall back to v1** — load/validate/compose/render failures silently use the app type’s `legacy_v1_fallback` kit (pilot: `generic`).

---

## 5. Validation commands

```bash
pytest tests/test_build_registry.py -q
```

```bash
pytest tests/test_build_registry.py \
       tests/test_build_registry_scaffold_context.py \
       tests/test_builder_llm_scaffold_registry_context.py \
       tests/test_builder_llm_scaffold_registry_manual_smoke.py \
       tests/test_build_registry_intent.py -q
```

```bash
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/game-pack \
  --app-type game.idle-incremental \
  --check
```

```bash
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/game-pack \
  --app-type game.trivia-timer \
  --check
```

```bash
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/game-pack \
  --app-type game.branching-narrative \
  --check
```

```bash
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/game-pack \
  --app-type game.memory-match \
  --check
```

```bash
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/game-pack \
  --app-type game.word-daily \
  --check
```

```bash
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/game-pack \
  --app-type game.daily-puzzle-grid \
  --check
```

```bash
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/game-pack \
  --app-type game.resource-management-sim \
  --check
```

Optional render sample:

```bash
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/game-pack \
  --app-type game.idle-incremental \
  --render-sample /dev/stdout
```

---

## 6. Safety boundaries

- **No template cloning** — recipes guide generation; no checked-in starter file trees.
- **No starter source trees** per app type.
- **No autonomous recipe mutation** — YAML changes are normal human-reviewed git commits only ([ADR-0018](../adr/0018-build-kit-evolution-loop-with-hermes.md)).
- **No auto-merge** of recipe or routing changes.
- **No default v2 routing** — flag off by default; ten current Game Pack recipes are routed when flag is on. **`game.card-deck-turn-based` is schema-only (not routed).** Future recipes still start schema-only until explicitly approved for routing. Recipe creation still does not imply routing.
- **No user-facing kit picker** for registry v2 app types.
- **No validator/recovery execution yet** — validator and recovery modules are conceptual (`runner: conceptual`); not executed at build time.
- **Hermes may critique/propose future changes only** through reviewed patches — no runtime recipe editing today.

---

## 7. How to add a recipe

Follow [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md). Summary:

1. Create an app type YAML under `game-pack/app-types/`.
2. Reuse or add mechanics, component contracts, validators, recovery, progress, and learning modules as needed.
3. Index every YAML file in `game-pack/registry-pack.yaml`.
4. Add or extend tests in `tests/test_build_registry.py` (and routing tests if routing is later approved).
5. Validate **all affected app types** after pack-wide edits.
6. **Do not add routing** unless explicitly requested and approved (separate from schema work).

---

## 8. How routing works today

- **Module:** `src/ham/build_registry/intent.py`
- **`select_registry_v2_app_type_for_prompt(prompt)`** — pure regex; returns `game.idle-incremental`, `game.trivia-timer`, `game.branching-narrative`, `game.memory-match`, `game.word-daily`, `game.daily-puzzle-grid`, `game.resource-management-sim`, `game.hangman-lite`, `game.typing-speed-racer`, `game.word-builder`, or `None`.
- **`enrich_plan_metadata_with_registry_v2(metadata, prompt, env=...)`** — copies metadata and sets `registry_v2_app_type` only when flag + intent match.
- **Routed app types today:** `game.idle-incremental`, `game.trivia-timer`, `game.branching-narrative`, `game.memory-match`, `game.word-daily`, `game.daily-puzzle-grid`, `game.resource-management-sim`, `game.hangman-lite`, `game.typing-speed-racer`, and `game.word-builder` (precedence: trivia → idle → branching narrative → memory match → word daily → daily puzzle grid → resource management sim → hangman lite → typing speed racer → word builder).
- **Trivia routing is conservative** — requires game-like or timed trivia/quiz/challenge signals; avoids survey/forms/flashcards and generic quiz unless clearly game-like/timed trivia.
- **Branching narrative routing is conservative** — requires branching/choice/story/CYOA/interactive-fiction signals; avoids blogs, chatbots, generic writing apps, generic RPGs, and live AI dungeon prompts.
- **Memory match routing is conservative** — requires memory/matching/pair/flip/concentration signals; avoids card battlers, trading cards, flashcards, poker, solitaire, and generic card games.
- **Word daily routing is conservative** — requires daily word guessing / Wordle-style / letter-feedback / attempt-limit signals; avoids crossword, word search, flashcards, typing games, dictionary apps, and generic “word game” without clear guessing intent.
- **Daily puzzle grid routing is conservative** — requires daily/grid/logic/cell/row/column/rule/clue signals; avoids dashboard grids, CSS layouts, data tables, crossword, word search, Tetris, Minesweeper, and generic “grid”, “puzzle”, or “daily game” without clear grid-logic intent.
- **Resource management sim routing is conservative** — requires game/sim signals plus resource/allocation/production/colony/factory/farm management signals; avoids SaaS dashboards, inventory apps, finance dashboards, trading apps, spreadsheets, live markets, multiplayer economy, idle clickers, and generic “management app” without clear simulation-game intent.
- **Hangman lite routing is conservative** — requires hangman / hidden-word / letter-guessing signals; Wordle/daily-word routes to `game.word-daily`; excludes crossword, word search, typing speed/WPM/challenge, flashcard, trivia, memory, idle, dashboard, dictionary, and writing-app prompts.
- **Typing speed racer routing is conservative** — requires typing speed / WPM / accuracy / timer / streak / keyboard-speed / type-prompts-fast challenge signals; generic typing app, typing tutor, text editor, and dashboard prompts do not route to `game.typing-speed-racer`.
- **Word builder routing is conservative** — requires word-building / spelling / letter-pool / letter-tile / word-slot / valid-submission signals; lowest precedence after typing speed racer; generic “word game” alone does not route to `game.word-builder`.
- **All routing remains narrow and flag-gated** — global negative patterns block SaaS, dashboard, trading, etc.; recipe-specific negatives prevent cross-recipe false positives.
- **Adding a recipe does not automatically route it** — new app types require explicit intent logic and approval per [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md), ADR-0017, and Authoring Guide routing policy. Recipe creation still does not imply routing.

Wiring entry point: `src/ham/builder_chat_scaffold.py` calls `enrich_plan_metadata_with_registry_v2()` before LLM scaffold.

---

## 9. Next recommended steps

Outcome facts format, manual example reports, and Hermes critique prompt are **already documented** ([OUTCOME_FACTS.md](OUTCOME_FACTS.md), [examples/](examples/)).

Possible next steps:

1. **Route `game.card-deck-turn-based`** when prompt patterns are approved (separate from schema landing; see [CARD_DECK_AMBIGUITY_REVIEW.md](CARD_DECK_AMBIGUITY_REVIEW.md)).
2. **Manual outcome report** for card-deck after schema validates (optional).
3. **Consider CI ratchet later** if registry usage increases (today warning-only for idle app-type validation + registry tests)
4. **Defer `game.deck-builder-lite`** until turn-based card recipe and routing prove stable
5. **Later:** outcome facts → Hermes critique report → proposed patch workflow (no auto-apply)

Routing policy: [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md).

---

## 10. Recent commits

Build Registry v2–related commits on `main` (newest first):

| Commit | Subject |
|--------|---------|
| `cbac76c8` | feat(builder): route word builder prompts to registry v2 |
| `d118fe34` | docs(builder): add word builder game recipe |
| `ca8c2727` | feat(builder): route typing speed prompts to registry v2 |
| `13e094e9` | docs(builder): add typing speed racer recipe |
| `6d15516e` | feat(builder): route hangman prompts to registry v2 |
| `abf20038` | docs(builder): add hangman lite game recipe |
| `90078363` | feat(builder): route resource management sim prompts to registry v2 |
| `3383ecab` | docs(builder): add resource management sim recipe |
| `9ab97766` | feat(builder): route daily puzzle grid prompts to registry v2 |
| `d294b294` | docs(builder): add daily puzzle grid recipe |
| `47dcfe59` | feat(builder): route daily word prompts to registry v2 |
| `61a128aa` | docs(builder): add daily word game recipe |
| `c9c73c25` | feat(builder): route memory match prompts to registry v2 |
| `9712028f` | docs(builder): update build registry status for narrative routing |
| `07ade6c8` | feat(builder): route branching narrative prompts to registry v2 |
| `a42c0f3d` | docs(builder): update build registry status for trivia routing |
| `1a34f577` | feat(builder): route trivia game prompts to registry v2 |
| `e5e1a2b1` | docs(builder): add build registry routing strategy |
| `4e5da57b` | docs(builder): update build registry status for memory recipe |
| `1ea9f73e` | docs(builder): add memory match game recipe |
| `d800c597` | docs(builder): add branching narrative game recipe |
| `23b76f2e` | docs(builder): add hermes build kit critique prompt |
| `a7c20d88` | docs(builder): add example build outcome facts |
| `082fdfb7` | docs(builder): define build registry outcome facts |
| `548887e7` | docs(builder): add build registry status handoff |
| `aab6e78b` | docs(builder): define hermes build kit evolution loop |
| `fa898adc` | docs(builder): add build kit authoring guide |
| `0dae7995` | docs(builder): add trivia game pack recipe |
| `ce2e6689` | feat(builder): route idle game prompts to registry v2 |
| `37104a45` | test(builder): add registry scaffold opt-in smoke coverage |
| `213771f4` | feat(builder): wire opt-in build registry scaffold context |
| `7bdf1406` | feat(builder): add unwired registry scaffold context resolver |
| `e9c3c00e` | docs(builder): design opt-in build registry wiring |
| `2a456666` | ci(builder): validate game pack registry pilot |
| `97493d70` | feat(builder): add unwired build registry loader |
| `b101b1ad` | tools(builder): validate game pack registry pilot |
| `09591b42` | docs(builder): tighten game pack pilot schema |
| `4fea59f8` | docs(builder): add game pack registry v2 pilot |
| `b0ab86f4` | docs(builder): clarify generative build kit registry direction |

---

## 11. Known non-goals / deferrals

- No recipe marketplace
- No UI kit picker for registry v2
- No default Build Registry v2 enablement (`HAM_BUILD_REGISTRY_V2_ENABLED` stays off unless operator sets it)
- No auto-generated PRs from Hermes yet
- No executable validator runners yet
- No recovery runner yet
- No promotion of registry YAML from `docs/build-kit-registry-v2/` to `src/ham/data/` yet
- No telemetry / outcome-facts capture implementation yet (ADR-0018 future phases)
