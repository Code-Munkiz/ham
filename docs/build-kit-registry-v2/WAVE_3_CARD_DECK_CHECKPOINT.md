# Build Registry v2 Wave 3 Card Deck Checkpoint

Completion checkpoint after **`game.card-deck-turn-based`** was authored, validated, routed behind the registry flag, and pushed to `origin/main`. This document records what landed and what remains — it is **not** approval for another recipe, routing change, or runtime enablement. For live status see [STATUS.md](STATUS.md).

**Checkpoint:** `origin/main` at `2d6deafa` — eleven recipes, 247 indexed modules, all routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`.

**Related commits:**

| Hash | Subject |
|------|---------|
| `eb049b02` | `docs(builder): add wave 3 direction checkpoint` |
| `55598361` | `docs(builder): add card deck ambiguity review` |
| `794abc11` | `feat(builder): add card deck turn based recipe` |
| `2d6deafa` | `feat(builder): route card deck recipe behind registry flag` |

---

## 1. Executive summary

**Wave 3 has begun** with **`game.card-deck-turn-based`**.

The recipe is **authored** as a generative playbook (no templates or starter source files), **validated and composed**, **rendered at ~10.8k characters** (under the 12k default budget), **routed conservatively** behind `HAM_BUILD_REGISTRY_V2_ENABLED`, and **pushed** to `origin/main`.

**Build Registry v2 remains opt-in.** v1 Builder Kits remain the default when the flag is unset or false. No API, frontend, or Builder Studio changes were made for this milestone.

---

## 2. Current baseline

| Dimension | State |
|-----------|--------|
| **Recipes** | 11 — all validate, compose, and render under 12k default budget |
| **Modules** | 247 indexed in [game-pack/registry-pack.yaml](game-pack/registry-pack.yaml) |
| **Routing** | All eleven routed behind `HAM_BUILD_REGISTRY_V2_ENABLED` with narrow intent matching |
| **Default path** | v1 Builder Kits when flag unset/false |
| **Templates / starters** | None — generative playbooks only |
| **Card-deck render length** | ~10.8k chars (no truncation at default budget) |
| **Card/deck routing model** | **Not** a generic card/deck router — strong combined game signals required |

**Wave inventory:**

| Wave | Recipes |
|------|---------|
| Wave 1 | `game.idle-incremental`, `game.trivia-timer`, `game.branching-narrative`, `game.memory-match`, `game.word-daily` |
| Wave 2 | `game.daily-puzzle-grid`, `game.resource-management-sim`, `game.hangman-lite`, `game.typing-speed-racer`, `game.word-builder` |
| Wave 3 (started) | `game.card-deck-turn-based` |

---

## 3. Card-deck recipe summary

**App type:** `game.card-deck-turn-based` — a small browser **turn-based card battle** with local-only, DOM-native interaction.

**Core mechanics (composed chain):**

| Mechanic | Role |
|----------|------|
| `mechanic.deck-draw-pile` | Shuffled draw pile; draw-from-top; deck exhaustion handling |
| `mechanic.hand-state` | Hand limit; add/remove on draw and play |
| `mechanic.discard-pile` | Played/discarded cards; optional top-of-discard visibility |
| `mechanic.card-turn-loop` | Player/enemy turn alternation; cards-per-turn limit |
| `mechanic.card-effect-resolution` | Deterministic damage, heal, draw effects on play |
| `mechanic.opponent-challenge-state` | Simple enemy HP, name, scripted turn actions |
| `mechanic.card-battle-scoring` | HP/score tracking; victory threshold evaluation |
| `mechanic.card-battle-result-state` | Terminal win/loss/draw; blocks further play; restart flow |

**UI contracts:** zone layout (deck/discard), playable cards, hand panel, opponent status, turn action bar, battle event log, results panel — plus shared `component.game-shell`.

**Behavioral posture:**

- Static in-memory card definitions for MVP
- DOM tap/click; no Canvas requirement
- Event log for turn feedback
- Restart / new round resets deck, hand, HP, and battle state
- No multiplayer, accounts, or network egress for MVP

---

## 4. Routing posture

Routing lives in `src/ham/build_registry/intent.py` and applies **only** when `HAM_BUILD_REGISTRY_V2_ENABLED` is truthy.

| Property | Detail |
|----------|--------|
| **Precedence** | **Lowest** — after trivia, idle, branching, memory-match, word-daily, daily-puzzle-grid, resource-management-sim, hangman-lite, typing-speed-racer, and word-builder |
| **Positive bar** | Strong **combined** signals: turn-based card battle, draw pile + hand + discard, play one card per turn, card effects + enemy/HP, solitaire-like strategy with deck/hand/discard/score, shuffle/draw/play/victory |
| **Weak signals (alone)** | “cards,” “deck,” “hand,” “deck builder,” “card app,” “card layout” — **do not route** without stronger game semantics |
| **Memory match** | Flip-pair / memory-card prompts keep **`game.memory-match`** precedence |
| **Non-match** | Falls back to v1 (no `registry_v2_app_type` metadata from routing) |
| **Bad/unknown app types** | Scaffold context falls back safely to v1 per existing ADR-0017 behavior |

See [CARD_DECK_AMBIGUITY_REVIEW.md](CARD_DECK_AMBIGUITY_REVIEW.md) and [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md) for the full negative/positive fixture rationale.

---

## 5. Safety exclusions

Card-deck routing **must not** capture prompts aimed at:

| Category | Examples (non-exhaustive) |
|----------|---------------------------|
| **Gambling / casino** | poker, blackjack, casino, betting, wagering, chips, odds |
| **Marketplace / NFT** | NFT cards, trading-card marketplace, buy/sell/trade cards, card auction |
| **Study decks** | flashcard study deck, spaced repetition cards |
| **Presentation decks** | pitch deck, slide deck, investor deck |
| **UI card layouts** | dashboard with cards, kanban board with cards, pricing cards, profile cards |
| **Non-game card apps** | credit-card app, business-card designer |
| **Generic weak prompts** | “build a deck builder,” “build a card deck app,” bare “cards” or “deck” |

These exclusions are encoded in negative patterns and cross-recipe guards — not as product features.

---

## 6. Tests and validation

| Check | Result |
|-------|--------|
| `python3 scripts/validate_game_pack_registry.py --app-type game.card-deck-turn-based --check` | Passed — 247 modules; compose OK |
| `pytest tests/test_build_registry.py -q` | 64 passed (recipe compose/render/budget; module count 247) |
| Targeted routing/scaffold pytest | 431 passed (`test_build_registry_intent.py`, `test_build_registry_scaffold_context.py`, `test_builder_llm_scaffold_registry_context.py`) |

**Routing test coverage (card-deck):**

- **Flag off** — strong card-deck prompt does not set `registry_v2_app_type`; v1 scaffold context preserved
- **Flag on positives** — multiple strong turn-based card battle prompts route to `game.card-deck-turn-based`
- **Flag on negatives** — gambling, marketplace, flashcard, pitch/slide deck, dashboard/kanban/UI card, credit/business card, and generic weak prompts do not route
- **Cross-recipe exclusions** — memory-match and existing routed recipes keep precedence; card-deck does not steal sibling lanes
- **Metadata / scaffold** — when routed, metadata contains `registry_v2_app_type=game.card-deck-turn-based`; rendered v2 context includes deck/hand/discard mechanics; unknown/bad app types fall back to v1

---

## 7. What this proves

- **Wave 3 can extend the Game Pack without templates** — another full recipe landed as YAML playbook modules only.
- **Conservative routing scales to 11 recipes** — lowest-precedence card-deck slot did not require a generic router.
- **Card/deck ambiguity is manageable** with strong positives, broad negatives, cross-recipe guards, and low precedence (see [CARD_DECK_AMBIGUITY_REVIEW.md](CARD_DECK_AMBIGUITY_REVIEW.md)).
- **Schema-first, route-after-approval rhythm still works** — ambiguity review → schema → tests → routing → push, in separate commits.
- **Build Registry v2 remains safe opt-in infrastructure** — flag off by default; v1 unchanged for operators who do not enable v2.

---

## 8. Remaining risks

| Risk | Detail |
|------|--------|
| **Pattern complexity** | Regex and cross-recipe negative tuples continue to grow with each recipe |
| **Card/deck language ambiguity** | “Deck” and “card” overlap many non-game domains; routing drift is possible under edge prompts |
| **`game.deck-builder-lite`** | Still high-risk; overlaps pitch decks, flashcard builders, and marketplace semantics |
| **Test suite growth** | Intent and scaffold tests now cover eleven recipes; maintenance cost rises |
| **Outcome reports still manual** | No automated generated-build feedback loop yet (ADR-0018 deferred) |
| **No real generated build reviewed** | Card-deck playbook has not been stress-tested against an actual LLM scaffold output |
| **Render budget pressure** | Future recipes should watch compose/render length; card-deck landed at ~10.8k with headroom |

---

## 9. Recommended next steps

1. **Do not add another recipe immediately** — pause for generated-build feedback on card-deck.
2. **Create a manual outcome report** for `game.card-deck-turn-based` (follow [OUTCOME_FACTS.md](OUTCOME_FACTS.md) and existing [outcome-reports/](outcome-reports/) examples).
3. **Consider an `OUTCOME_REPORT_INDEX.md`** — single index linking all manual outcome reports as the set grows.
4. **Consider a lightweight registry reference-checker / JSON Schema proposal** — reduce manual `registry-pack.yaml` indexing errors as module count grows.
5. **Defer `game.deck-builder-lite`** until card-deck generated output is reviewed and routing proves stable.
6. **Keep physics behind a separate ADR/design track** — do not mix Canvas/physics recipes into the DOM-native Game Pack without explicit architecture approval (see [WAVE_3_DIRECTION_CHECKPOINT.md](WAVE_3_DIRECTION_CHECKPOINT.md)).

---

## 10. Non-goals

This checkpoint does **not** authorize:

- Default v2 enablement (`HAM_BUILD_REGISTRY_V2_ENABLED` off by default)
- Public kit picker for registry v2 app types
- Generic game router or generic card/deck router
- Gambling/casino gameplay support
- Marketplace / card-trading / NFT support
- Templates or starter source file cloning
- Autonomous Hermes PRs or runtime recipe mutation
- Executable validators or recovery runners at build time
- Physics engines, multiplayer, or live services

---

## 11. References

| Document | Path |
|----------|------|
| Live status | [STATUS.md](STATUS.md) |
| Wave 3 direction (pre-recipe) | [WAVE_3_DIRECTION_CHECKPOINT.md](WAVE_3_DIRECTION_CHECKPOINT.md) |
| Card/deck ambiguity review | [CARD_DECK_AMBIGUITY_REVIEW.md](CARD_DECK_AMBIGUITY_REVIEW.md) |
| Wave 2 retrospective | [WAVE_2_RETROSPECTIVE.md](WAVE_2_RETROSPECTIVE.md) |
| Authoring guide | [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md) |
| Routing strategy | [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md) |
| Outcome facts format | [OUTCOME_FACTS.md](OUTCOME_FACTS.md) |
| Manual outcome — resource-management-sim | [outcome-reports/game.resource-management-sim.manual-outcome.md](outcome-reports/game.resource-management-sim.manual-outcome.md) |
| Manual outcome — typing-speed-racer | [outcome-reports/game.typing-speed-racer.manual-outcome.md](outcome-reports/game.typing-speed-racer.manual-outcome.md) |
| Manual outcome — word-builder | [outcome-reports/game.word-builder.manual-outcome.md](outcome-reports/game.word-builder.manual-outcome.md) |
| ADR — registry design | [../adr/0016-generative-build-kit-registry-v2.md](../adr/0016-generative-build-kit-registry-v2.md) |
| ADR — opt-in scaffold wiring | [../adr/0017-build-registry-v2-opt-in-scaffold-wiring.md](../adr/0017-build-registry-v2-opt-in-scaffold-wiring.md) |
| ADR — Hermes evolution loop | [../adr/0018-build-kit-evolution-loop-with-hermes.md](../adr/0018-build-kit-evolution-loop-with-hermes.md) |
