# Build Registry v2 Card/Deck Ambiguity Review

Ambiguity and routing-risk review before authoring any card/deck Game Pack recipe. This document is **not** recipe approval, routing approval, or implementation authorization. For Wave 3 context see [WAVE_3_DIRECTION_CHECKPOINT.md](WAVE_3_DIRECTION_CHECKPOINT.md). For routing policy see [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md).

**Review date:** post–Wave 3 direction checkpoint (`eb049b02` on `main`).

---

## 1. Executive summary

**Card/deck systems are the preferred next DOM-native Wave 3 recipe lane** if Game Pack expansion continues — but only after this ambiguity review and explicit human approval at each step (schema → validation → routing).

**No recipe or routing should be added from this review alone.**

Card/deck language is **highly ambiguous**. It overlaps with:

- Playable **card games** (intended lane)
- **Gambling/casino** apps (poker, blackjack, betting)
- **Collectible card marketplaces** (buy/sell/trade, NFT cards)
- **Flashcards** and study decks
- **Dashboards** and UI card layouts (pricing cards, profile cards, kanban)
- **Pitch decks** and presentation builders
- **Generic “deck builder”** tools unrelated to games

The **safest first candidate** is likely **`game.card-deck-turn-based`**, not **`game.deck-builder-lite`**. Turn-based play with draw/hand/discard piles maps cleanly to DOM-native game loops. Deck-builder progression overlaps too many non-game “deck” meanings.

---

## 2. Scope

### In scope

- DOM-native **card/deck game** recipe ambiguity
- Prompt-routing boundaries (future, not implemented here)
- Positive and negative routing signals
- Cross-recipe risks with existing ten recipes
- Candidate prompt examples for review fixtures
- Recommendation on whether a first recipe is **safe to author later**

### Out of scope

- Adding recipes or YAML modules
- Adding routing or tests
- Creating templates or starter source files
- Enabling `HAM_BUILD_REGISTRY_V2_ENABLED` by default
- Gambling/casino gameplay support
- Trading-card marketplace or ecommerce support
- Multiplayer services
- Canvas/physics implementation

---

## 3. Candidate recipe: `game.card-deck-turn-based`

### Likely recipe intent

A **small browser turn-based card game** with local-only state:

| Mechanic area | Expected behavior |
|---------------|-------------------|
| **Draw pile** | Shuffled deck; draw cards into hand |
| **Discard pile** | Played or discarded cards accumulate |
| **Hand state** | Limited hand size; visible card UI |
| **Turn loop** | Player turn → play/discard/end turn → opponent or challenge step |
| **Card effects** | Simple deterministic effects (damage, block, draw, heal) |
| **Scoring or victory** | HP, score threshold, or deck exhaustion win |
| **Opponent/challenge** | Simple AI enemy, static challenge, or solo score target |
| **Interaction** | DOM-native — tap/click cards; no Canvas requirement for MVP |

### Good-fit prompts

- “Build a simple turn-based card battle game with a draw pile, hand, discard pile, and health points.”
- “Build a browser card game where the player draws cards, plays one card per turn, and tries to defeat a simple enemy.”
- “Build a solitaire-like strategy card game with a deck, hand, discard pile, and score.”

### Risky prompts (should not route without stronger game signals — many should never route)

- “Build a card deck app.”
- “Build a deck builder.”
- “Build a trading card marketplace.”
- “Build a poker game.”
- “Build a blackjack app.”
- “Build a flashcard study deck.”
- “Build a pitch deck generator.”
- “Build a dashboard with cards.”

---

## 4. Candidate recipe: `game.deck-builder-lite`

### Likely recipe intent

A **lighter deck-construction roguelike loop**:

- Starting deck → card rewards after encounters
- Add/remove/upgrade cards between rounds
- Synergy choices and run progression
- Encounters or nodes between deck edits

### Why it is riskier than `game.card-deck-turn-based`

| Risk | Detail |
|------|--------|
| **“Deck builder” ambiguity** | Overlaps pitch decks, presentation builders, flashcard builders, construction/project planning, and card collection marketplaces |
| **Higher state complexity** | Run map, reward pools, deck mutation history — more YAML and render budget pressure |
| **Progression guidance** | Needs clearer acceptance criteria than a single-match turn loop |
| **Routing overlap** | “Build a deck builder” is weak signal for games vs non-games |

### Recommendation for sequencing

Treat **`game.deck-builder-lite` as a second card/deck recipe** — only after `game.card-deck-turn-based` schema, validation, and (if approved) routing prove stable with conservative negatives.

---

## 5. Major ambiguity classes

### A. Gambling/casino ambiguity

**Example phrases:** poker, blackjack, casino, betting, wagering, chips, odds, gambling, roulette, slots

**Recommendation:** Do **not** route gambling/casino prompts to Build Registry v2 card/deck recipes. Fall back to **v1** or require separate product/policy review. HAM Game Pack MVP should not imply real-money or casino mechanics.

### B. Trading card marketplace ambiguity

**Example phrases:** NFT cards, collectible card marketplace, card packs for sale, buy/sell/trade cards, card rarity marketplace, auction cards

**Recommendation:** Do **not** route marketplace/ecommerce/asset-trading prompts to game recipes.

### C. Flashcard/study ambiguity

**Example phrases:** flashcards, study deck, spaced repetition, quiz cards, vocabulary cards, Anki-style

**Recommendation:** Do **not** route flashcard/study prompts to card **game** recipes. Existing trivia routing already excludes flashcards; card/deck negatives must reinforce this.

### D. Pitch deck/document ambiguity

**Example phrases:** pitch deck, investor deck, slide deck, presentation deck, PowerPoint-style deck

**Recommendation:** Do **not** route pitch/presentation prompts to card game recipes.

### E. UI card/dashboard ambiguity

**Example phrases:** card layout, dashboard cards, pricing cards, profile cards, kanban cards, stat cards, component library cards

**Recommendation:** Do **not** route UI-card/dashboard prompts to card game recipes. Global negatives already block many dashboard prompts; card-specific negatives still needed.

### F. Existing game recipe overlap

Compare against current routed recipes:

| Existing recipe | Overlap risk |
|-----------------|--------------|
| `game.memory-match` | “Cards” + flip/match language — **highest sibling risk** |
| `game.idle-incremental` | Upgrade/card UI metaphors — low unless clicker-on-cards |
| `game.trivia-timer` | Quiz “cards” — exclude flashcard/quiz study |
| `game.branching-narrative` | Choice “cards” — exclude story choice UI without deck mechanics |
| `game.daily-puzzle-grid` | Grid cells vs card grid — exclude unless deck/hand signals |
| `game.resource-management-sim` | Resource “cards” in dashboards — exclude |
| Word-family recipes | Unrelated unless prompt mixes word + deck incorrectly |

**Recommendation:** Card/deck routing should require **explicit deck/hand/draw/discard/turn/card-play game semantics**. Memory-match flip-pair prompts must **not** route to card-deck-turn-based.

---

## 6. Positive routing signals

### Strong signals (future routing may require one or more)

- card game
- deck of cards
- draw pile / draw stack
- discard pile
- hand (of cards)
- play a card
- turn-based card battle / turn-based card game
- card effects
- simple enemy / opponent with cards
- solitaire-like **game** (with deck/hand/discard context)
- health points plus cards / HP and cards
- one card per turn
- shuffle, draw, discard (together with game/challenge/battle)

### Weak signals (must not route alone)

- cards
- deck
- hand
- card layout
- card builder
- deck builder
- card UI
- card component

**Rule:** Weak signals alone → **v1 fallback**, no `registry_v2_app_type`.

---

## 7. Negative routing signals

Future recipe and cross-recipe negatives should block (non-exhaustive):

| Category | Terms / patterns |
|----------|------------------|
| **Gambling** | poker, blackjack, casino, gambling, betting, wager, odds, chips, roulette, slots |
| **Marketplace** | NFT, marketplace, buy/sell/trade, collectible marketplace, card packs for sale, auction |
| **Study** | flashcard, study deck, spaced repetition, vocabulary cards, quiz cards (study) |
| **Presentation** | pitch deck, slide deck, presentation, investor deck |
| **UI/dashboard** | dashboard cards, kanban, pricing cards, profile cards, card layout, stat cards |
| **Non-game IDs** | credit card, ID card, business card |
| **Generic weak** | `\bcards\b` without game/deck/hand/draw/discard/turn; `\bdeck\b` without game/card-play context |

---

## 8. Candidate routing posture

| Rule | Posture |
|------|---------|
| Generic card/deck router | **No** — one recipe, narrow patterns |
| `game.card-deck-turn-based` | Route only on **strong game-specific phrases** when flag on |
| `game.deck-builder-lite` | **Wait** — second recipe after turn-based proves stable |
| “Deck builder” (generic) | **v1 fallback** unless explicitly framed as card **game** with run/encounter/play signals |
| “Cards” (generic) | **v1 fallback** |
| Gambling/casino | **v1 fallback** — never route to Game Pack card recipe |
| Memory match | Cross-exclude flip/pair/match prompts from card-deck route |

All routing remains behind **`HAM_BUILD_REGISTRY_V2_ENABLED`**; v1 default unchanged per ADR-0017.

---

## 9. Candidate positive/negative test prompts

Future routing fixtures (not implemented by this review). Expected behavior assumes flag **on** for “route” rows.

### Positive prompts → eventual `game.card-deck-turn-based`

| Prompt | Expected behavior | Reason |
|--------|-------------------|--------|
| Build a simple turn-based card battle game with a draw pile, hand, discard pile, and health points. | Route | Strong deck/hand/discard/turn/battle signals |
| Build a browser card game where the player draws cards, plays one card per turn, and tries to defeat a simple enemy. | Route | Draw, play per turn, enemy — clear game loop |
| Build a solitaire-like strategy card game with a deck, hand, discard pile, and score. | Route | Solitaire-like + deck/hand/discard + score |
| Make a turn-based card game with shuffle, draw, and discard mechanics. | Route | Core pile mechanics + turn-based card game |
| Create a card battle game where I play one card per turn from my hand. | Route | Hand + one card per turn + battle |
| Build a browser game with a draw pile, hand limit, and discard pile for playing cards. | Route | Explicit pile/hand/discord game semantics |
| Make a simple card duel game with HP and card effects. | Route | Duel + HP + card effects |
| Build a DOM card game where I draw from a deck and play cards against a simple opponent. | Route | Deck draw + play + opponent |

### Negative prompts → must not route to `game.card-deck-turn-based`

| Prompt | Expected behavior | Reason |
|--------|-------------------|--------|
| Build a poker game. | v1 / no route | Gambling class — out of scope |
| Make a blackjack app. | v1 / no route | Gambling class |
| Build a casino card game with betting and chips. | v1 / no route | Gambling + betting |
| Create a trading card marketplace to buy and sell NFT cards. | v1 / no route | Marketplace class |
| Build a collectible card auction site. | v1 / no route | Marketplace / ecommerce |
| Make a flashcard study deck with spaced repetition. | v1 / no route | Flashcard/study class |
| Build vocabulary quiz cards for learning Spanish. | v1 / no route | Study/quiz cards |
| Create a pitch deck generator for investors. | v1 / no route | Pitch deck class |
| Build a slide deck presentation app. | v1 / no route | Presentation class |
| Make a dashboard with pricing cards and profile cards. | v1 / no route | UI card/dashboard class |
| Build a kanban board with draggable cards. | v1 / no route | Kanban/workflow UI |
| Design a credit card comparison dashboard. | v1 / no route | Credit card — non-game |
| Build a business card scanner app. | v1 / no route | Business card — non-game |
| Build a deck builder. | v1 / no route | Weak/generic — deck builder ambiguity |
| Build a card deck app. | v1 / no route | Weak — no game loop signals |
| Build a memory card matching game with flip pairs. | Route to `game.memory-match` (not card-deck) | Existing recipe — flip/pair overlap |
| Build me an idle clicker game. | Route to idle (not card-deck) | Existing recipe overlap |
| Build a trivia quiz with timer. | Route to trivia (not card-deck) | Existing recipe overlap |
| Build a resource management sim. | Route to resource sim (not card-deck) | Existing recipe overlap |

---

## 10. Recommendation

| Decision | Recommendation |
|----------|----------------|
| Author `game.card-deck-turn-based` next? | **Yes, when ready** — safe to **author schema/docs only** if routing stays conservative per this review |
| Author `game.deck-builder-lite` first? | **No** — defer until turn-based recipe proves stable |
| Add routing now? | **No** — routing only after recipe validation and explicit approval per [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md) |
| Gambling/casino support? | **No** |
| Marketplace/card-trading support? | **No** |
| Generic card/deck router? | **No** |
| v2 default? | **No** — keep opt-in; v1 remains default |

**Summary:** Card/deck is viable as Wave 3’s first **schema** expansion lane, but ambiguity is real. Conservative positives, broad negatives, and memory-match cross-exclusion are mandatory before any routing land.

---

## 11. Suggested next artifact

1. **`game.card-deck-turn-based` recipe authoring** — docs/schema only in `game-pack/`; follow [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md); index in `registry-pack.yaml`; validate with `validate_game_pack_registry.py --check`.
2. **Routing** — separate step only after schema validates and humans approve prompt fixtures from §9.
3. **If ambiguity still feels too high** — draft candidate routing tests in a design doc **before** authoring YAML, or author schema-only and hold routing indefinitely.

Optional follow-ups:

- Update [WAVE_3_DIRECTION_CHECKPOINT.md](WAVE_3_DIRECTION_CHECKPOINT.md) when card-deck schema lands
- Add manual outcome report template for card-deck after first schema validation
- [OUTCOME_REPORT_INDEX.md](OUTCOME_REPORT_INDEX.md) when outcome report set grows

---

## 12. References

| Doc | Purpose |
|-----|---------|
| [WAVE_3_DIRECTION_CHECKPOINT.md](WAVE_3_DIRECTION_CHECKPOINT.md) | Wave 3 options and pause recommendation |
| [WAVE_2_RETROSPECTIVE.md](WAVE_2_RETROSPECTIVE.md) | Wave 2 lessons; card-deck deferral rationale |
| [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md) | Routing approval policy |
| [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md) | Recipe authoring rules |
| [OUTCOME_FACTS.md](OUTCOME_FACTS.md) | Outcome facts schema |
| [game.resource-management-sim.manual-outcome.md](outcome-reports/game.resource-management-sim.manual-outcome.md) | Sim/dashboard overlap pattern |
| [game.typing-speed-racer.manual-outcome.md](outcome-reports/game.typing-speed-racer.manual-outcome.md) | Timing/tutor overlap pattern |
| [game.word-builder.manual-outcome.md](outcome-reports/game.word-builder.manual-outcome.md) | Word-family boundary pattern |
| [ADR-0016](../adr/0016-generative-build-kit-registry-v2.md) | Registry design |
| [ADR-0017](../adr/0017-build-registry-v2-opt-in-scaffold-wiring.md) | Opt-in scaffold wiring |
| [ADR-0018](../adr/0018-build-kit-evolution-loop-with-hermes.md) | Future Hermes evolution loop |

Existing memory-match routing notes: [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md) (card battler / trading card / flashcard exclusions).
