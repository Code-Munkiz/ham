# Deck Builder Lite Readiness Review

> **Readiness/design gate only · Not recipe approval · Not routing approval · Not implementation authorization**

Pre-authoring review for a potential **`game.deck-builder-lite`** Game Pack recipe. This document evaluates whether the next card-family expansion is safe to **author schema-only** after Wave 3 card/timing gates passed. It does **not** add a recipe, routing, templates, or runtime changes.

**Review date:** 2026-05-26 (UTC)  
**Baseline:** `origin/main` at `dfc40c88` — thirteen recipes, 300 indexed modules, all routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`, scaffold quality repair guard live.

---

## 1. Executive summary

**`game.deck-builder-lite` is now viable to evaluate** because **`game.card-deck-turn-based`** passed its generated gate (final rerun clean inspector, playable draw/hand/discard/turn loop) and Wave 3 DOM timing/input lanes (**reaction-time**, **rhythm-tap**) also passed.

It should **not** be authored blindly. The main risks remain **prompt ambiguity**, **state complexity**, **progression-loop scaffolding**, and collisions with **pitch decks**, **flashcards**, **marketplaces**, and **`game.card-deck-turn-based`**.

**This review does not add a recipe or routing.**

---

## 2. Current Wave 3 baseline

| Dimension | State |
|-----------|--------|
| **Recipes** | 13 |
| **Indexed modules** | 300 |
| **Routing** | All 13 recipes route narrowly behind `HAM_BUILD_REGISTRY_V2_ENABLED` |
| **Default lane** | v1 Builder Kit JSON when flag off |
| **Scaffold quality guard** | Live — post-output inspection + optional one-pass repair (`HAM_SCAFFOLD_QUALITY_REPAIR=false` disables repair) |
| **Templates / starter files** | None — generative playbooks only |
| **Wave 3 generated gates passed** | `game.card-deck-turn-based` (**Pass**), `game.reaction-time-challenge` (**Pass**), `game.rhythm-tap-lite` (**Pass** after quality fix pass) |

Card-deck gate evidence moved from Conditional pass → **Pass** after scaffold quality hardening (empty deck seed, ignored payload, victory wiring). Rhythm-tap gate closed a false-positive result-state flag and improved miss/final-score repair guidance.

---

## 3. Why deck-builder-lite is attractive

| Factor | Rationale |
|--------|-----------|
| **Higher product-demo value** | Roguelite deck-building is a recognizable game genre with clear “build your deck, fight, choose rewards” UX — stronger demo story than a single-match card battler alone. |
| **Builds on card-deck foundation** | Draw/hand/discard, card effects, enemy/challenge resolution, and result/restart patterns are proven in `game.card-deck-turn-based` schema + generated gate. |
| **Progression and strategic choice** | Reward picks (add/remove/upgrade), run-scoped deck mutation, and lightweight encounter loops showcase Build Registry v2’s generative playbook depth without physics/Canvas. |
| **Bridge to deeper systems** | A minimal run loop (encounter → reward → next encounter) extends the card family toward roguelite depth while staying DOM-native and local-only. |

---

## 4. Why deck-builder-lite is risky

| Risk | Detail |
|------|--------|
| **“Deck builder” ambiguity** | Overlaps pitch decks, slide/presentation builders, flashcard/study decks, construction/project planning, dashboard card layouts, and collectible/trading-card marketplaces — see [CARD_DECK_AMBIGUITY_REVIEW.md](./CARD_DECK_AMBIGUITY_REVIEW.md). |
| **State complexity** | Run state must coordinate deck, hand, discard, reward pool, encounter/enemy, deck mutations (add/remove/upgrade), and run result — more modules and more scaffold failure modes than turn-based card battle alone. |
| **Shell-only outputs** | LLM scaffolds may emit component trees without playable reward loops, empty deck seeds, or no-op reducers — card-deck gate history shows this is real without quality guard + repair focus. |
| **Overlap with `game.card-deck-turn-based`** | Turn-based battle prompts may steal or be stolen if routing negatives are not strict; deck-builder must require **progression/reward/mutation** signals beyond draw/hand/discard/turn alone. |
| **Marketplace/collectible drift** | “Card collection,” “card packs,” “rarity,” “trade/buy/sell” language can pull toward ecommerce/NFT semantics — out of scope for Game Pack MVP. |

---

## 5. Candidate recipe intent

Safe intended shape for **`game.deck-builder-lite`** (schema authoring target, not yet implemented):

| Area | Intended behavior |
|------|-------------------|
| **Platform** | DOM-native, local-only, single-player browser game |
| **Starting deck** | Small fixed starter set (non-empty, populated card objects) |
| **Core loop** | Draw → hand → play/discard → resolve encounter effects |
| **Encounters** | Simple rounds or static enemy/challenge steps (no map/pathing in v1) |
| **Rewards** | After encounter: choose add card, remove card, or upgrade card (small pool) |
| **Progression** | Lightweight run progression — deck grows/shrinks/refines across encounters |
| **Result** | Win/loss or run-complete state with summary |
| **Restart** | New run resets deck, hand, discard, rewards, encounter, and result state |

This is **lighter than a full roguelite** (no node map, no shop economy, no account persistence) but **heavier than turn-based card battle** (deck mutation between encounters is the differentiator).

---

## 6. Explicit exclusions

Do **not** interpret future deck-builder routing or schema as supporting:

- Pitch deck generator
- Slide deck builder
- Presentation builder
- Flashcard / study deck
- NFT / trading-card marketplace
- Buy/sell/trade card app
- Card pack store / gacha store
- Gambling / casino / poker / blackjack
- Dashboard / card layout builder
- Kanban board
- Construction / project planning deck
- Music deck / audio deck apps

Prompts matching these families should **fall back to v1** or route to other recipes only when unambiguous game signals exist elsewhere.

---

## 7. Strong positive signals for future routing

Future routing (deferred until explicit approval) may require combinations such as:

- deck-building card game
- start with a small deck and earn new cards after battles
- add cards to deck after each encounter
- remove or upgrade cards between rounds
- draw hand, play cards, discard, then choose rewards
- roguelite deck builder
- Slay-the-Spire-like browser card game *(routing/tests only — do not embed third-party IP in generated copy)*

Require **game + deck mutation/progression** semantics, not bare “deck builder” language.

---

## 8. Weak signals that should not route alone

These must **not** route to `game.deck-builder-lite` without stronger game/progression signals:

- deck builder
- card deck
- deck
- cards
- build a deck
- card collection
- presentation deck
- study deck

Weak signals should fall back to **v1** or, when appropriate, to **`game.card-deck-turn-based`** only if turn-based battle semantics dominate (draw/hand/discard/turn without reward-loop language).

---

## 9. Candidate recipe scope

Recommended **schema-only v1 scope** (keep small):

| In scope | Out of scope (defer) |
|----------|----------------------|
| One player | Multiplayer |
| Simple enemy/challenge per encounter | Map/pathing/node graph |
| Small starter deck (e.g. 5–8 cards) | Large card pools / expansions |
| Small reward pool (add/remove/upgrade) | Marketplace / collection economy |
| Local run state only | Accounts / backend / cloud save |
| DOM components + reducer/state machine | Canvas / physics |
| Run result + new run | Meta-progression across sessions |

**Render budget:** stay under **12k** chars (Game Pack default), same as existing thirteen recipes.

---

## 10. Readiness decision

**Ready to author schema-only next**, provided:

- Scope remains the **minimal local run loop** in §9 (no map, no marketplace, no backend).
- **Routing is deferred** until schema validates, composes, renders under budget, and human approval follows [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md).
- Ambiguity negatives and cross-recipe boundaries are designed **before** any routing work, using [CARD_DECK_AMBIGUITY_REVIEW.md](./CARD_DECK_AMBIGUITY_REVIEW.md) as the card-family source of truth.

This is **not** approval to route or enable v2 by default.

---

## 11. Next-step recommendation

1. **Author `game.deck-builder-lite` schema-only** — app type YAML + mechanics/components/validators/recovery/progress/learning modules; index in `registry-pack.yaml`.
2. **Do not add routing in the same step** — schema land and validation tests first.
3. **Keep render budget under 12k** — validate with `scripts/validate_game_pack_registry.py --app-type game.deck-builder-lite --check`.
4. **Add generated gate review after routing** — `/tmp/` operator run → outcome report, same Wave 3 bar as card-deck/reaction/rhythm.
5. **Keep `game.card-deck-turn-based` as the base boundary** — turn-based battle prompts stay on card-deck; deck-builder requires reward/mutation/progression signals.

---

## 12. Non-goals

- No recipe from this review alone
- No routing from this review alone
- No default v2 enablement (`HAM_BUILD_REGISTRY_V2_ENABLED` stays off unless operator sets it)
- No templates or starter source files
- No marketplace / card-trading support
- No gambling / casino support
- No backend / accounts / cloud persistence
- No physics / Canvas engine
- No multiplayer

---

## 13. References

- [CARD_DECK_AMBIGUITY_REVIEW.md](./CARD_DECK_AMBIGUITY_REVIEW.md)
- [WAVE_3_PROGRESS_CHECKPOINT.md](./WAVE_3_PROGRESS_CHECKPOINT.md)
- [WAVE_3_POST_QUALITY_REPAIR_CHECKPOINT.md](./WAVE_3_POST_QUALITY_REPAIR_CHECKPOINT.md)
- [outcome-reports/game.card-deck-turn-based.wave3-gate-fix-review.md](./outcome-reports/game.card-deck-turn-based.wave3-gate-fix-review.md)
- [outcome-reports/game.reaction-time-challenge.wave3-gate-review.md](./outcome-reports/game.reaction-time-challenge.wave3-gate-review.md)
- [outcome-reports/game.rhythm-tap-lite.wave3-gate-review.md](./outcome-reports/game.rhythm-tap-lite.wave3-gate-review.md)
- [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md)
- [AUTHORING_GUIDE.md](./AUTHORING_GUIDE.md)
- [STATUS.md](./STATUS.md)
