# Build Registry v2 Manual Outcome Report Index

Index of **manual example** outcome reports for Build Registry v2 Game Pack recipes. For machine-readable outcome shape see [OUTCOME_FACTS.md](../OUTCOME_FACTS.md). For live registry status see [STATUS.md](../STATUS.md).

> **Manual learning artifacts only · Not production telemetry · Not automated validator output · Not Hermes-generated patches**

---

## 1. Purpose

This index tracks **manual outcome report examples** for Build Registry v2 recipes.

These reports are **human-authored learning artifacts**. They are **not** production telemetry, automated validator results, runtime-wired outcome facts, or Hermes-generated change requests.

They help maintainers compare **recipe intent** against **expected generated-build behavior** — positive signals, failure modes, routing boundaries, and possible future refinements — before any YAML or routing change is proposed.

---

## 2. Current report inventory

| Recipe | Wave | Report path | Primary stress test | Key routing boundary | Current recommendation |
|--------|------|-------------|---------------------|----------------------|------------------------|
| `game.resource-management-sim` | 2 | [game.resource-management-sim.manual-outcome.md](./game.resource-management-sim.manual-outcome.md) | Resource loops, allocation, capacity, win/loss | Dashboard / inventory / finance / spreadsheet overlap | Keep active; review generated builds before deeper sim expansion |
| `game.typing-speed-racer` | 2 | [game.typing-speed-racer.manual-outcome.md](./game.typing-speed-racer.manual-outcome.md) | Timing, WPM, accuracy, mistake feedback, result state | Typing tutor / writing tool / flashcard / form overlap | Keep active; preserve tutor/form negatives |
| `game.word-builder` | 2 | [game.word-builder.manual-outcome.md](./game.word-builder.manual-outcome.md) | Letter pool, valid submissions, duplicates, hints, scoring | Word-daily / hangman / typing-speed / dictionary overlap | Keep active; avoid new word-family recipes until boundaries stay stable |
| `game.card-deck-turn-based` | 3 | [game.card-deck-turn-based.manual-outcome.md](./game.card-deck-turn-based.manual-outcome.md) | Deck/hand/discard, turn loop, card effects, enemy state | Gambling / marketplace / flashcard / pitch deck / dashboard / memory-match overlap | Keep active; review real generated output before `game.deck-builder-lite` |

**Coverage:** 4 manual reports across **11** routed recipes (247 modules). Eight recipes have no manual outcome report yet (see §4).

---

## 3. Cross-report lessons

- **Manual reports are most useful at high-ambiguity recipe boundaries** — sim vs dashboard, typing vs tutor, word-family separation, card/deck vs marketplace/flashcard/pitch-deck.
- **Each report documents** positive signals, negative signals, routing implications, and possible future recipe refinements — without applying them.
- **Reports must not automatically trigger** recipe, routing, or schema changes. They inform human review and future ADR-0018 workflows.
- **Reports support the future Hermes critique loop**, but humans still decide and merge any change.
- **More reports are not always better.** After several boundary examples, the next high-value artifact may be a **lightweight registry reference-checker** or JSON Schema proposal rather than another manual report.

---

## 4. Coverage gaps

| Gap | Detail |
|-----|--------|
| **No real generated card-deck build reviewed** | [game.card-deck-turn-based.manual-outcome.md](./game.card-deck-turn-based.manual-outcome.md) is pattern-only |
| **No real generated resource-management build reviewed** | [game.resource-management-sim.manual-outcome.md](./game.resource-management-sim.manual-outcome.md) is pattern-only |
| **No automated outcome facts ingestion** | [OUTCOME_FACTS.md](../OUTCOME_FACTS.md) defines format; runtime capture not wired |
| **No validator/recovery runner** | Validators remain conceptual (`runner: conceptual`) |
| **No JSON Schema / reference checker** | `registry-pack.yaml` indexing is still manual |
| **No manual report yet for eight recipes** | `game.idle-incremental`, `game.trivia-timer`, `game.branching-narrative`, `game.memory-match`, `game.word-daily`, `game.daily-puzzle-grid`, `game.hangman-lite` — and no Wave 1 baseline report set |

---

## 5. Recommended next steps

1. **Do not add another recipe immediately** — pause for generated-build feedback ([WAVE_3_CARD_DECK_CHECKPOINT.md](../WAVE_3_CARD_DECK_CHECKPOINT.md)).
2. **Review at least one real generated build** for `game.card-deck-turn-based`.
3. **Review at least one real generated build** for `game.resource-management-sim`.
4. **Consider a lightweight registry reference-checker / JSON Schema proposal** — reduce manual index drift as module count grows.
5. **Keep `game.deck-builder-lite` deferred** until card-deck generated output is reviewed.
6. **Keep physics behind a separate ADR/design track** — do not mix into DOM-native Game Pack without explicit architecture approval.

---

## 6. Non-goals

This index does **not** authorize or imply:

- Production telemetry claims
- Runtime outcome ingestion or API fields
- Executable validator or recovery runners at build time
- Autonomous Hermes PRs or auto-merge
- Recipe edits from this index alone
- Routing changes from this index alone
- Default v2 enablement (`HAM_BUILD_REGISTRY_V2_ENABLED` remains off by default)

---

## 7. References

| Doc | Purpose |
|-----|---------|
| [OUTCOME_FACTS.md](../OUTCOME_FACTS.md) | Minimal outcome facts schema (ADR-0018 Phase B) |
| [WAVE_2_RETROSPECTIVE.md](../WAVE_2_RETROSPECTIVE.md) | Wave 2 completion and outcome-report trio context |
| [WAVE_3_CARD_DECK_CHECKPOINT.md](../WAVE_3_CARD_DECK_CHECKPOINT.md) | Wave 3 card-deck landing checkpoint |
| [AUTHORING_GUIDE.md](../AUTHORING_GUIDE.md) | Recipe authoring and validation rules |
| [ROUTING_STRATEGY.md](../ROUTING_STRATEGY.md) | Routing approval policy |
| [game.resource-management-sim.manual-outcome.md](./game.resource-management-sim.manual-outcome.md) | Wave 2 manual outcome — sim |
| [game.typing-speed-racer.manual-outcome.md](./game.typing-speed-racer.manual-outcome.md) | Wave 2 manual outcome — typing |
| [game.word-builder.manual-outcome.md](./game.word-builder.manual-outcome.md) | Wave 2 manual outcome — word builder |
| [game.card-deck-turn-based.manual-outcome.md](./game.card-deck-turn-based.manual-outcome.md) | Wave 3 manual outcome — card deck |
| [ADR-0018: Build Kit Evolution Loop with Hermes](../../adr/0018-build-kit-evolution-loop-with-hermes.md) | Future critique → proposed patch workflow |
