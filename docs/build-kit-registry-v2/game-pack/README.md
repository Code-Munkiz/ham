# Game Pack — Build Kit Registry v2 schema pilot

**Status:** Non-runtime schema pilot only. **Schema version:** `0.1`

This directory holds **design data** for the first [Generative Build Kit Registry v2](../../adr/0016-generative-build-kit-registry-v2.md) Game Pack pilot: **`game.idle-incremental`**, **`game.trivia-timer`**, **`game.branching-narrative`**, **`game.memory-match`**, and **`game.word-daily`**.

## Root manifest

**[`registry-pack.yaml`](registry-pack.yaml)** (`pack.game`) is the authoritative index:

- Lists all module ids by kind in `module_index`
- Defines `compose_defaults` (compose order, max modules, default stack kit, validator/recovery policy)
- Defines `render_sections` for future playbook context assembly
- Carries `schema_version: "0.1"` and `non_runtime_notice`

All cross-references should resolve through the pack manifest. See **[CONVENTIONS.md](CONVENTIONS.md)**.

## What this is

- **Generative playbook modules** — app types, mechanics, component contracts, **stack kits**, validators, recovery playbooks, progress labels, and learning hooks.
- **Intended** to guide future registry **composition** (intent → modules → phased plan → generate → validate → recover).
- **Documentation under `docs/`** — not loaded by HAM at runtime today.

## What this is not

- **Not starter templates.** HAM must not clone these YAML files or any checked-in game source tree.
- **Not generated game files.** No `App.tsx`, no asset bundles, no prefab scenes.
- **Not wired.** No loader in `src/ham/`, no changes to v1 `src/ham/data/builder_kits/*.json`, no chat/scaffold integration.
- **Not a claim of implementation.** Registry v2 composition, validation execution, and recovery runners are **proposed** in ADR-0016 only.
- **Validators and recovery remain conceptual.** `runner: conceptual` and `check_type: conceptual` — they describe intent, not live execution.

Use vocabulary: **module**, **playbook**, **contract**, **mechanic**. Avoid “template” except when stating these are **not** templates.

## Build phases ownership

- **`app_type.build_phases`** (`game.idle-incremental`) owns phase structure (ids, order, optional flags).
- **`progress_label`** (`progress.idle-incremental`) maps those phase ids to normie-friendly copy via `phase_message_map` and `source_phase_owner`.
- Progress labels do **not** redefine phases independently.

## Why these app types first

### `game.idle-incremental`

| Reason | Detail |
|--------|--------|
| **DOM-native** | React + Tailwind UI; no canvas/WebGL/physics engine required for MVP proof. |
| **Low technical risk** | Single-page local state; aligns with existing Lane A safety (`no-network-egress`). |
| **Mechanics reuse** | Score, economy, upgrades, and save/load compose cleanly and recur in other casual games. |
| **No asset pipeline** | No spritesheets, audio packs, or level editors in scope. |
| **Strong Game Pack proof** | Exercises composition, validators, tick-loop recovery, and persistence — without Tetris-style monolithic archetype kits. |

### `game.trivia-timer`

| Reason | Detail |
|--------|--------|
| **Second recipe shape** | Proves the pack supports a different mechanic graph (questions, timer, progression) — not only idle loops. |
| **DOM-native quiz UI** | Multiple-choice buttons, countdown HUD, results screen — no canvas or external trivia API for MVP. |
| **Shared reuse** | Reuses `mechanic.score`, `component.game-shell`, `stack.dom-game-minimal`, and score HUD patterns. |
| **Distinct validators** | Timer cleanup, deterministic scoring, and question progression — complementary to idle economy validators. |
| **Explicit MVP bounds** | Static in-memory questions; no multiplayer, accounts, or LLM-generated questions at runtime. |

### `game.branching-narrative`

| Reason | Detail |
|--------|--------|
| **Third recipe shape** | Proves the pack supports choice-based story graphs — not only idle loops or linear quizzes. |
| **DOM-native narrative UI** | Scene panel, choice cards, optional flags/inventory HUD, explicit ending screen. |
| **Shared reuse** | Reuses `component.game-shell`, `stack.dom-game-minimal`. |
| **Distinct validators** | Graph reachability, dead-end prevention, state consistency — complementary to idle/trivia validators. |
| **Explicit MVP bounds** | Static in-memory story nodes; no runtime LLM story, accounts, multiplayer, or external story API. |

### `game.memory-match`

| Reason | Detail |
|--------|--------|
| **Fourth recipe shape** | Proves the pack supports flip-and-match card grids — distinct from idle, quiz, and narrative graphs. |
| **DOM-native card UI** | Grid, flip state, move counter, victory screen — emoji/text symbols only for MVP. |
| **Shared reuse** | Reuses `component.game-shell`, `stack.dom-game-minimal`. |
| **Distinct validators** | Pair integrity, flip-lock third-card prevention, match completion — complementary to other recipes. |
| **Explicit MVP bounds** | Static in-memory deck; no image assets, multiplayer, accounts, or Canvas engines. |

### `game.word-daily`

| Reason | Detail |
|--------|--------|
| **Fifth recipe shape** | Proves the pack supports daily word guessing with per-letter feedback — distinct from idle, quiz, narrative, and card games. |
| **DOM-native word UI** | Guess grid, letter tiles, optional on-screen keyboard, win/loss panel — no external dictionary API for MVP. |
| **Shared reuse** | Reuses `component.game-shell`, `stack.dom-game-minimal`. |
| **Distinct validators** | Duplicate-letter feedback, guess length/attempts, daily seed stability, keyboard guardrails — complementary to other recipes. |
| **Explicit MVP bounds** | Static in-memory word list; date-based daily seed; no accounts, leaderboard, or live word API. |

## Pilot module layout

```txt
docs/build-kit-registry-v2/game-pack/
  README.md
  CONVENTIONS.md
  registry-pack.yaml          # pack.game — root manifest (schema_version 0.1)
  app-types/game.idle-incremental.yaml
  app-types/game.trivia-timer.yaml
  app-types/game.branching-narrative.yaml
  app-types/game.memory-match.yaml
  app-types/game.word-daily.yaml
  stack-kits/dom-game-minimal.yaml
  mechanics/{score,economy,upgrades,save-load,question-set,timer,answer-validation,progression,story-node-graph,story-flags,inventory-lite,choice-resolution,ending-resolution,card-pair-set,card-flip-state,interaction-lock,match-detection,move-counter,victory-detection,word-target,daily-seed,guess-grid,keyboard-input,letter-feedback,attempt-limit,win-loss-state}.yaml
  component-contracts/{game-shell,resource-counter,upgrade-card,save-status,question-card,choice-list,timer-display,results-summary,story-panel,choice-card,story-state-summary,inventory-panel,ending-screen,card-grid,memory-card,move-counter,match-progress,victory-screen,word-grid,guess-row,letter-tile,on-screen-keyboard,word-result-panel}.yaml
  validators/{no-negative-currency,passive-income-tick,local-storage-roundtrip,timer-cleanup,score-calculation,question-progression,story-graph-reachability,no-dead-end-choice,story-state-consistency,card-pair-integrity,flip-lock-prevents-third-card,match-completion,duplicate-letter-feedback,guess-length-and-attempts,daily-seed-stability,keyboard-input-guardrails}.yaml
  recovery-playbooks/{stale-interval-or-bad-tick-loop,invalid-local-storage-json,stale-timer-or-uncleared-timeout,broken-question-progression,broken-story-graph,inconsistent-story-state,broken-card-flip-state,mismatched-card-pairs,stuck-interaction-lock,broken-duplicate-letter-feedback,unstable-daily-seed,invalid-guess-state}.yaml
  progress-labels/{idle-incremental,trivia-timer,branching-narrative,memory-match,word-daily}.yaml
  learning-hooks/{idle-incremental,trivia-timer,branching-narrative,memory-match,word-daily}.yaml
```

## Conceptual composition example

When a user says *“Build me a simple idle clicker where I earn coins and buy upgrades”*, a **future** composer would assemble:

```txt
registry_pack: pack.game
schema_version: 0.1
app_type:     game.idle-incremental
stack_kit:    stack.dom-game-minimal
mechanics:    mechanic.score → mechanic.economy → mechanic.upgrades → mechanic.save-load
contracts:    component.game-shell, component.resource-counter, component.upgrade-card, component.save-status
validators:   validator.no-negative-currency, validator.passive-income-tick, validator.local-storage-roundtrip
recovery:     recovery.stale-interval-or-bad-tick-loop, recovery.invalid-local-storage-json
progress:     progress.idle-incremental
learning:     learning.idle-incremental
```

Full id graph and dependency fields: [CONVENTIONS.md](CONVENTIONS.md#example-composition--gameidle-incremental).

HAM would then **generate custom code** from the composed playbook context — not copy a starter repo.

### Conceptual composition — `game.trivia-timer`

When a user says *“Build a timed trivia quiz with multiple choice questions”*, a **future** composer would assemble:

```txt
registry_pack: pack.game
schema_version: 0.1
app_type:     game.trivia-timer
stack_kit:    stack.dom-game-minimal
mechanics:    mechanic.question-set → mechanic.score → mechanic.timer → mechanic.answer-validation → mechanic.progression
contracts:    component.game-shell, component.resource-counter, component.question-card, component.choice-list, component.timer-display, component.results-summary
validators:   validator.timer-cleanup, validator.score-calculation, validator.question-progression
recovery:     recovery.stale-timer-or-uncleared-timeout, recovery.broken-question-progression
progress:     progress.trivia-timer
learning:     learning.trivia-timer
```

### Conceptual composition — `game.branching-narrative`

When a user says *“Build a branching story game where my choices change the ending”*, a **future** composer would assemble:

```txt
registry_pack: pack.game
schema_version: 0.1
app_type:     game.branching-narrative
stack_kit:    stack.dom-game-minimal
mechanics:    mechanic.story-node-graph → mechanic.story-flags → mechanic.inventory-lite → mechanic.choice-resolution → mechanic.ending-resolution
contracts:    component.game-shell, component.story-panel, component.choice-card, component.story-state-summary, component.inventory-panel, component.ending-screen
validators:   validator.story-graph-reachability, validator.no-dead-end-choice, validator.story-state-consistency
recovery:     recovery.broken-story-graph, recovery.inconsistent-story-state
progress:     progress.branching-narrative
learning:     learning.branching-narrative
```

### Conceptual composition — `game.memory-match`

When a user says *“Build a memory matching game with emoji cards”*, a **future** composer would assemble:

```txt
registry_pack: pack.game
schema_version: 0.1
app_type:     game.memory-match
stack_kit:    stack.dom-game-minimal
mechanics:    mechanic.card-pair-set → mechanic.card-flip-state → mechanic.interaction-lock → mechanic.match-detection → mechanic.move-counter → mechanic.victory-detection
contracts:    component.game-shell, component.card-grid, component.memory-card, component.move-counter, component.match-progress, component.victory-screen
validators:   validator.card-pair-integrity, validator.flip-lock-prevents-third-card, validator.match-completion
recovery:     recovery.broken-card-flip-state, recovery.mismatched-card-pairs, recovery.stuck-interaction-lock
progress:     progress.memory-match
learning:     learning.memory-match
```

### Conceptual composition — `game.word-daily`

When a user says *“Build a daily word guessing game like Wordle”*, a **future** composer would assemble:

```txt
registry_pack: pack.game
schema_version: 0.1
app_type:     game.word-daily
stack_kit:    stack.dom-game-minimal
mechanics:    mechanic.word-target → mechanic.daily-seed → mechanic.guess-grid → mechanic.keyboard-input → mechanic.letter-feedback → mechanic.attempt-limit → mechanic.win-loss-state
contracts:    component.game-shell, component.word-grid, component.guess-row, component.letter-tile, component.on-screen-keyboard, component.word-result-panel
validators:   validator.duplicate-letter-feedback, validator.guess-length-and-attempts, validator.daily-seed-stability, validator.keyboard-input-guardrails
recovery:     recovery.broken-duplicate-letter-feedback, recovery.unstable-daily-seed, recovery.invalid-guess-state
progress:     progress.word-daily
learning:     learning.word-daily
```

## Relation to v1 Builder Kits

v1 `tetris.json` / `calculator.json` remain **unchanged** one-layer archetype metadata. This pilot explores **decomposed mechanics** as the path forward for games. App type includes **`legacy_v1_fallback: generic`** for strangler routing when wired. See ADR-0016 § Game Pack pilot.

## Next steps (out of scope for this folder)

1. Promote approved YAML to `src/ham/data/build_registry/` **only after** loader/composer ADR is accepted.
2. Wire composition into Lane A chat scaffold — **separate implementation PR**.
3. Expand validator `runner` enum beyond `conceptual` when harness exists.
