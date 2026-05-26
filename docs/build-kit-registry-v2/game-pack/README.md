# Game Pack — Build Kit Registry v2 schema pilot

**Status:** Non-runtime schema pilot only. **Schema version:** `0.1`

This directory holds **design data** for the first [Generative Build Kit Registry v2](../../adr/0016-generative-build-kit-registry-v2.md) Game Pack pilot: thirteen routed Wave 1–3 recipes plus **`game.deck-builder-lite`** (Wave 3 schema-only, not routed). See [STATUS.md](../STATUS.md) for the full recipe list.

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

### `game.daily-puzzle-grid` (Wave 2)

| Reason | Detail |
|--------|--------|
| **Sixth recipe shape** | Proves the pack supports daily grid logic puzzles with constraint-based completion — distinct from word guessing and card games. |
| **DOM-native grid UI** | Puzzle grid, cells, rule panel, status bar, optional hints — no Canvas or external puzzle API for MVP. |
| **Shared reuse** | Reuses `component.game-shell`, `stack.dom-game-minimal`. |
| **Distinct mechanics** | Puzzle seed, grid state, constraint rules, cell interaction, mistake tracking, hints, completion check. |
| **Explicit MVP bounds** | Static in-memory puzzle definitions; deterministic daily seed; no accounts, leaderboard, or live puzzle API. |

### `game.resource-management-sim` (Wave 2)

| Reason | Detail |
|--------|--------|
| **Seventh recipe shape** | Proves the pack supports turn/tick resource sims with allocation tradeoffs — distinct from idle clickers and grid puzzles. |
| **DOM-native sim UI** | Resource dashboard, allocation controls, production panel, upgrades, event log, goal status — no Canvas or external economy API for MVP. |
| **Shared reuse** | Reuses `component.game-shell`, `stack.dom-game-minimal`. Does not reuse idle `mechanic.economy` or `mechanic.score`. |
| **Distinct mechanics** | Resource pool, capacity limits, production chains, allocation decisions, turn/tick loop, upgrades, bounded events, goal/failure state. |
| **Explicit MVP bounds** | Static in-memory sim data; 2–4 resources; local-only state; no accounts, multiplayer economy, or live market APIs. |

### `game.hangman-lite` (Wave 2)

| Reason | Detail |
|--------|--------|
| **Eighth recipe shape** | Proves the pack supports hangman-style letter guessing — distinct from Wordle-style word-daily feedback grids. |
| **DOM-native hangman UI** | Hidden word display, letter bank, wrong-guess meter, result panel — no Canvas or external word API for MVP. |
| **Shared reuse** | Reuses `component.game-shell`, `stack.dom-game-minimal`. Does not reuse `mechanic.word-target`, `mechanic.letter-feedback`, or word-daily keyboard grid semantics. |
| **Distinct mechanics** | Hidden word, letter guessing, duplicate prevention, reveal state, wrong-guess limit, hangman win/loss. |
| **Explicit MVP bounds** | Static in-memory word list; one target word per round; local-only state; no accounts, leaderboard, or live word API. |

### `game.typing-speed-racer` (Wave 2)

| Reason | Detail |
|--------|--------|
| **Ninth recipe shape** | Proves the pack supports typing speed / accuracy challenges — distinct from word guessing, hangman, and flashcard apps. |
| **DOM-native typing UI** | Prompt panel, input box, WPM display, accuracy meter, streak indicator, results panel — no Canvas or live prompt API for MVP. |
| **Shared reuse** | Reuses `component.game-shell`, `stack.dom-game-minimal`. Does not reuse word-daily, hangman, or trivia timer semantics. |
| **Distinct mechanics** | Prompt set, race clock, input stream, mistake tracking, accuracy scoring, WPM calculation, streak combo, result state. |
| **Explicit MVP bounds** | Static in-memory prompt list; local-only state; input lock after finish; no accounts, leaderboard, or multiplayer race. |

### `game.word-builder` (Wave 2 — schema-only, not routed)

| Reason | Detail |
|--------|--------|
| **Tenth recipe shape** | Proves the pack supports word-building / spelling challenges — distinct from Wordle-style guessing, hangman letter guessing, and typing speed tests. |
| **DOM-native word-builder UI** | Letter pool panel, word slot board, submit control, feedback panel, score display, results panel — no Canvas or live dictionary API for MVP. |
| **Shared reuse** | Reuses `component.game-shell`, `stack.dom-game-minimal`. Does not reuse word-daily, hangman-lite, or typing-speed-racer mechanics. |
| **Distinct mechanics** | Letter pool, word slot construction, word validation, submission attempts, scoring, lightweight hints, level progression, result state. |
| **Explicit MVP bounds** | Static in-memory accepted word set; finite letter pool; duplicate submissions do not score twice; local-only state; no accounts or leaderboard. |
| **Routing** | Schema-only — not routed behind `HAM_BUILD_REGISTRY_V2_ENABLED` until explicitly approved. |

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
  app-types/game.daily-puzzle-grid.yaml
  app-types/game.resource-management-sim.yaml
  app-types/game.hangman-lite.yaml
  app-types/game.typing-speed-racer.yaml
  app-types/game.word-builder.yaml
  stack-kits/dom-game-minimal.yaml
  mechanics/{score,economy,upgrades,save-load,question-set,timer,answer-validation,progression,story-node-graph,story-flags,inventory-lite,choice-resolution,ending-resolution,card-pair-set,card-flip-state,interaction-lock,match-detection,move-counter,victory-detection,word-target,daily-seed,guess-grid,keyboard-input,letter-feedback,attempt-limit,win-loss-state,puzzle-seed,grid-state,constraint-rules,cell-interaction,mistake-tracking,hint-system-lite,completion-check,resource-pool,capacity-limit,production-chain,allocation-decision,turn-or-tick-loop,upgrade-path,event-modifier,goal-and-failure-state,hidden-word,letter-guessing,duplicate-guess-prevention,reveal-state,wrong-guess-limit,hangman-win-loss-state,typing-prompt-set,timer-or-race-clock,typing-input-stream,mistake-tracking-typing,accuracy-scoring,wpm-calculation,streak-combo,typing-result-state,letter-pool,word-slot-construction,word-validation,submission-attempts,word-builder-scoring,hint-reveal-lite,level-progression,word-builder-result-state}.yaml
  component-contracts/{game-shell,resource-counter,upgrade-card,save-status,question-card,choice-list,timer-display,results-summary,story-panel,choice-card,story-state-summary,inventory-panel,ending-screen,card-grid,memory-card,move-counter,match-progress,victory-screen,word-grid,guess-row,letter-tile,on-screen-keyboard,word-result-panel,puzzle-grid,grid-cell,rule-panel,puzzle-status-bar,hint-button,completion-modal,resource-dashboard,allocation-control,production-panel,upgrade-panel,event-log,goal-status,hidden-word-display,letter-bank,wrong-guess-meter,guess-input,hangman-result-panel,typing-prompt-panel,typing-input-box,wpm-display,accuracy-meter,streak-indicator,typing-results-panel,letter-pool-panel,word-slot-board,submit-word-control,word-feedback-panel,word-score-display,word-builder-results-panel}.yaml
  validators/{no-negative-currency,passive-income-tick,local-storage-roundtrip,timer-cleanup,score-calculation,question-progression,story-graph-reachability,no-dead-end-choice,story-state-consistency,card-pair-integrity,flip-lock-prevents-third-card,match-completion,duplicate-letter-feedback,guess-length-and-attempts,daily-seed-stability,keyboard-input-guardrails,grid-dimensions,constraint-consistency,cell-state-transitions,puzzle-seed-stability,completion-detection,no-negative-resources,production-chain-consistency,allocation-bounds,capacity-limit-enforcement,goal-state-detection,tick-loop-stability,letter-reveal-correctness,duplicate-guess-blocking,wrong-guess-limit-enforcement,hangman-win-loss-detection,wpm-calculation-consistency,accuracy-score-bounds,timer-completion,mistake-counting,input-lock-after-finish,letter-pool-integrity,word-slot-state-consistency,word-validation-rules,duplicate-submission-blocking,word-builder-scoring-consistency,word-builder-completion}.yaml
  recovery-playbooks/{stale-interval-or-bad-tick-loop,invalid-local-storage-json,stale-timer-or-uncleared-timeout,broken-question-progression,broken-story-graph,inconsistent-story-state,broken-card-flip-state,mismatched-card-pairs,stuck-interaction-lock,broken-duplicate-letter-feedback,unstable-daily-seed,invalid-guess-state,broken-grid-state,inconsistent-constraint-rules,unstable-puzzle-seed,bad-completion-check,broken-resource-accounting,invalid-production-chain,runaway-tick-loop,unreachable-goal-state,broken-letter-reveal,duplicate-guess-state,invalid-hangman-end-state,broken-wpm-calculation,invalid-accuracy-score,stuck-typing-timer,input-accepted-after-finish,broken-letter-pool,invalid-word-slot-state,bad-word-validation,duplicate-word-submission}.yaml
  progress-labels/{idle-incremental,trivia-timer,branching-narrative,memory-match,word-daily,daily-puzzle-grid,resource-management-sim,hangman-lite,typing-speed-racer,word-builder}.yaml
  learning-hooks/{idle-incremental,trivia-timer,branching-narrative,memory-match,word-daily,daily-puzzle-grid,resource-management-sim,hangman-lite,typing-speed-racer,word-builder}.yaml
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

### Conceptual composition — `game.daily-puzzle-grid`

When a user says *“Build a daily grid logic puzzle with row and column constraints”*, a **future** composer would assemble:

```txt
registry_pack: pack.game
schema_version: 0.1
app_type:     game.daily-puzzle-grid
stack_kit:    stack.dom-game-minimal
mechanics:    mechanic.puzzle-seed → mechanic.grid-state → mechanic.constraint-rules → mechanic.cell-interaction → mechanic.mistake-tracking → mechanic.hint-system-lite → mechanic.completion-check
contracts:    component.game-shell, component.puzzle-grid, component.grid-cell, component.rule-panel, component.puzzle-status-bar, component.hint-button, component.completion-modal
validators:   validator.grid-dimensions, validator.constraint-consistency, validator.cell-state-transitions, validator.puzzle-seed-stability, validator.completion-detection
recovery:     recovery.broken-grid-state, recovery.inconsistent-constraint-rules, recovery.unstable-puzzle-seed, recovery.bad-completion-check
progress:     progress.daily-puzzle-grid
learning:     learning.daily-puzzle-grid
```

**Note:** This recipe is **schema-only** today — not routed until explicitly approved.

### Conceptual composition — `game.resource-management-sim`

When a user says *“Build a turn-based resource management sim where I allocate wood and stone to production”*, a **future** composer would assemble:

```txt
registry_pack: pack.game
schema_version: 0.1
app_type:     game.resource-management-sim
stack_kit:    stack.dom-game-minimal
mechanics:    mechanic.resource-pool → mechanic.capacity-limit → mechanic.production-chain → mechanic.allocation-decision → mechanic.turn-or-tick-loop → mechanic.upgrade-path → mechanic.event-modifier → mechanic.goal-and-failure-state
contracts:    component.game-shell, component.resource-dashboard, component.allocation-control, component.production-panel, component.upgrade-panel, component.event-log, component.goal-status
validators:   validator.no-negative-resources, validator.production-chain-consistency, validator.allocation-bounds, validator.capacity-limit-enforcement, validator.tick-loop-stability, validator.goal-state-detection
recovery:     recovery.broken-resource-accounting, recovery.invalid-production-chain, recovery.runaway-tick-loop, recovery.unreachable-goal-state
progress:     progress.resource-management-sim
learning:     learning.resource-management-sim
```

### Conceptual composition — `game.hangman-lite`

When a user says *“Build a hangman word game where I guess letters”*, a **future** composer would assemble:

```txt
registry_pack: pack.game
schema_version: 0.1
app_type:     game.hangman-lite
stack_kit:    stack.dom-game-minimal
mechanics:    mechanic.hidden-word → mechanic.letter-guessing → mechanic.duplicate-guess-prevention → mechanic.reveal-state → mechanic.wrong-guess-limit → mechanic.hangman-win-loss-state
contracts:    component.game-shell, component.hidden-word-display, component.letter-bank, component.guess-input, component.wrong-guess-meter, component.hangman-result-panel
validators:   validator.letter-reveal-correctness, validator.duplicate-guess-blocking, validator.wrong-guess-limit-enforcement, validator.hangman-win-loss-detection
recovery:     recovery.broken-letter-reveal, recovery.duplicate-guess-state, recovery.invalid-hangman-end-state
progress:     progress.hangman-lite
learning:     learning.hangman-lite
```

### Conceptual composition — `game.typing-speed-racer`

When a user says *“Build a typing speed game with WPM and accuracy”*, a **future** composer would assemble:

```txt
registry_pack: pack.game
schema_version: 0.1
app_type:     game.typing-speed-racer
stack_kit:    stack.dom-game-minimal
mechanics:    mechanic.typing-prompt-set → mechanic.timer-or-race-clock → mechanic.typing-input-stream → mechanic.mistake-tracking-typing → mechanic.accuracy-scoring → mechanic.wpm-calculation → mechanic.streak-combo → mechanic.typing-result-state
contracts:    component.game-shell, component.typing-prompt-panel, component.typing-input-box, component.wpm-display, component.accuracy-meter, component.streak-indicator, component.typing-results-panel
validators:   validator.wpm-calculation-consistency, validator.accuracy-score-bounds, validator.timer-completion, validator.mistake-counting, validator.input-lock-after-finish
recovery:     recovery.broken-wpm-calculation, recovery.invalid-accuracy-score, recovery.stuck-typing-timer, recovery.input-accepted-after-finish
progress:     progress.typing-speed-racer
learning:     learning.typing-speed-racer
```

**Note:** This recipe is **schema-only** today — not routed until explicitly approved.

### Conceptual composition — `game.word-builder`

When a user says *"Build a word builder game where I form words from letter tiles"*, a **future** composer would assemble:

```txt
registry_pack: pack.game
schema_version: 0.1
app_type:     game.word-builder
stack_kit:    stack.dom-game-minimal
mechanics:    mechanic.letter-pool → mechanic.word-slot-construction → mechanic.word-validation → mechanic.submission-attempts → mechanic.word-builder-scoring → mechanic.hint-reveal-lite → mechanic.level-progression → mechanic.word-builder-result-state
contracts:    component.game-shell, component.letter-pool-panel, component.word-slot-board, component.submit-word-control, component.word-feedback-panel, component.word-score-display, component.word-builder-results-panel
validators:   validator.letter-pool-integrity, validator.word-slot-state-consistency, validator.word-validation-rules, validator.duplicate-submission-blocking, validator.word-builder-scoring-consistency, validator.word-builder-completion
recovery:     recovery.broken-letter-pool, recovery.invalid-word-slot-state, recovery.bad-word-validation, recovery.duplicate-word-submission
progress:     progress.word-builder
learning:     learning.word-builder
```

**Note:** This recipe is **schema-only** today — not routed until explicitly approved.

### `game.rhythm-tap-lite` (Wave 3 — schema-only, not routed)

| Reason | Detail |
|--------|--------|
| **Thirteenth recipe shape** | Proves the pack supports DOM rhythm tap timing — distinct from reaction-time false-start games and typing speed tests. |
| **DOM-native rhythm UI** | Cue panel, timing feedback, score tracker, streak indicator, miss panel, round controls, results panel — no Canvas or external audio for MVP. |
| **Shared reuse** | Reuses `component.game-shell`, `stack.dom-game-minimal`. Does not reuse reaction-time or typing-speed mechanics. |
| **Distinct mechanics** | Beat sequence, timing windows, tap input, accuracy scoring, streak combo, round progression, result state. |
| **Explicit MVP bounds** | Local-only beat/cue schedule; perfect/good/miss judgment; no copyrighted music, live audio sync, or accounts. |
| **Routing** | Schema-only — not routed behind `HAM_BUILD_REGISTRY_V2_ENABLED` until explicitly approved. |

### Conceptual composition — `game.rhythm-tap-lite`

When a user says *"Build a rhythm tap game where I press space on the beat for perfect/good/miss scores"*, a **future** composer would assemble:

```txt
registry_pack: pack.game
schema_version: 0.1
app_type:     game.rhythm-tap-lite
stack_kit:    stack.dom-game-minimal
mechanics:    mechanic.rhythm-round-state-machine → mechanic.rhythm-beat-sequence → mechanic.rhythm-timing-window → mechanic.rhythm-tap-input → mechanic.rhythm-accuracy-scoring → mechanic.rhythm-streak-combo → mechanic.rhythm-round-progression → mechanic.rhythm-result-state
contracts:    component.game-shell, component.rhythm-cue-panel, component.rhythm-timing-feedback, component.rhythm-score-tracker, component.rhythm-streak-indicator, component.rhythm-miss-panel, component.rhythm-round-controls, component.rhythm-results-panel
validators:   validator.rhythm-state-transitions, validator.rhythm-timing-window-bounds, validator.rhythm-score-consistency, validator.rhythm-input-cleanup, validator.rhythm-streak-bounds
recovery:     recovery.stuck-rhythm-state, recovery.broken-rhythm-timing, recovery.invalid-rhythm-score, recovery.stale-rhythm-cue
progress:     progress.rhythm-tap-lite
learning:     learning.rhythm-tap-lite
```

**Note:** This recipe is **schema-only** today — not routed until explicitly approved.

### `game.deck-builder-lite` (Wave 3 — schema-only, not routed)

| Reason | Detail |
|--------|--------|
| **Fourteenth recipe shape** | Proves the pack supports DOM deck-building runs — distinct from turn-based battle-only and non-game “deck” meanings. |
| **DOM-native deck UI** | Card zones, hand panel, encounter bar, reward choice, run status, event log, results panel — no Canvas for MVP. |
| **Shared reuse** | Reuses `mechanic.deck-draw-pile`, `mechanic.hand-state`, `mechanic.discard-pile`, `mechanic.card-effect-resolution`, `mechanic.opponent-challenge-state`, and card-zone components from `game.card-deck-turn-based`. |
| **Distinct mechanics** | Run state machine, starter deck seed, encounter loop, reward offer/choice, deck mutation, run result. |
| **Explicit MVP bounds** | Local-only linear encounter run; add-card rewards; optional lightweight remove/upgrade; no map/pathing, marketplace, or accounts. |
| **Routing** | Schema-only — not routed behind `HAM_BUILD_REGISTRY_V2_ENABLED` until explicitly approved. |

### Conceptual composition — `game.deck-builder-lite`

When a user says *"Build a browser deck-building card game where the player starts with a small deck, fights simple encounters, and chooses a new card reward after each win"*, a **future** composer would assemble:

```txt
registry_pack: pack.game
schema_version: 0.1
app_type:     game.deck-builder-lite
stack_kit:    stack.dom-game-minimal
mechanics:    mechanic.deck-builder-run-state-machine → mechanic.starter-deck-seed → mechanic.deck-draw-pile → mechanic.hand-state → mechanic.discard-pile → mechanic.encounter-round-loop → mechanic.card-effect-resolution → mechanic.opponent-challenge-state → mechanic.reward-offer-choice → mechanic.deck-mutation → mechanic.deck-builder-result-state
contracts:    component.game-shell, component.card-zone-layout, component.playable-card, component.hand-panel, component.opponent-status-panel, component.encounter-action-bar, component.reward-choice-panel, component.deck-builder-event-log, component.deck-builder-results-panel
validators:   validator.deck-builder-run-state-transitions, validator.starter-deck-non-empty, validator.deck-zone-integrity, validator.hand-size-bounds, validator.draw-discard-consistency, validator.reward-choice-integrity, validator.deck-mutation-consistency, validator.card-effect-resolution-order, validator.deck-builder-run-result-detection
recovery:     recovery.broken-deck-builder-run-state, recovery.empty-reward-pool, recovery.stuck-encounter-loop, recovery.invalid-deck-mutation
progress:     progress.deck-builder-lite
learning:     learning.deck-builder-lite
```

**Note:** This recipe is **schema-only** today — not routed until explicitly approved.

## Relation to v1 Builder Kits

v1 `tetris.json` / `calculator.json` remain **unchanged** one-layer archetype metadata. This pilot explores **decomposed mechanics** as the path forward for games. App type includes **`legacy_v1_fallback: generic`** for strangler routing when wired. See ADR-0016 § Game Pack pilot.

## Next steps (out of scope for this folder)

1. Promote approved YAML to `src/ham/data/build_registry/` **only after** loader/composer ADR is accepted.
2. Wire composition into Lane A chat scaffold — **separate implementation PR**.
3. Expand validator `runner` enum beyond `conceptual` when harness exists.
