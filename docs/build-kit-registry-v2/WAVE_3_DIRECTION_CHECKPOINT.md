# Build Registry v2 Wave 3 Direction Checkpoint

Decision checkpoint before adding any more Game Pack recipes. This document records options, risks, and a recommended path — it is **not** implementation approval for new recipes, routing, or runtime changes. For live status see [STATUS.md](STATUS.md). For Wave 2 context see [WAVE_2_RETROSPECTIVE.md](WAVE_2_RETROSPECTIVE.md).

**Checkpoint:** `origin/main` at `cc6c3ef6` — ten recipes, 219 indexed modules, three manual outcome reports, all routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`.

---

## 1. Executive summary

**Wave 2 is complete.** The Build Registry v2 Game Pack now covers ten DOM-native game patterns with schema, validation, compose/render, narrow routing, and three manual outcome reports for learning — without templates, starter files, or default v2 enablement.

The registry has **enough recipes and manual outcome artifacts to pause before expansion.** Adding more recipes immediately increases routing surface, context bloat risk, and maintenance cost without corresponding feedback from actual generated builds.

**Wave 3 should not begin** by adding physics engines, multiplayer systems, fluid simulation, or live AI NPC story generation. Those lanes need separate design tracks and stronger evidence thresholds.

The **next decision** is whether Wave 3 should focus on:

- **Option A:** DOM-native card/deck games
- **Option B:** Deeper DOM-native strategy/sim games
- **Option C:** Arcade DOM-lite games
- **Option D:** A separate Physics Game Pack design track (ADR first, recipes later)

This checkpoint recommends **pausing recipe expansion**, then choosing between a **card/deck ambiguity review** (preferred if recipes continue) or a **Physics Game Pack ADR** (preferred if architecture work comes first).

---

## 2. Current baseline

| Dimension | State |
|-----------|--------|
| **Recipes** | 10 — all validate, compose, and render under 12k default budget |
| **Modules** | 219 indexed in [game-pack/registry-pack.yaml](game-pack/registry-pack.yaml) |
| **Routing** | All ten routed behind `HAM_BUILD_REGISTRY_V2_ENABLED` with narrow intent matching |
| **Default path** | v1 Builder Kits when flag unset/false |
| **Templates / starters** | None — generative playbooks only |
| **Manual outcome reports** | 3 — [resource-management-sim](outcome-reports/game.resource-management-sim.manual-outcome.md), [typing-speed-racer](outcome-reports/game.typing-speed-racer.manual-outcome.md), [word-builder](outcome-reports/game.word-builder.manual-outcome.md) |
| **Operating model** | Schema-first, route-after-approval; recipe creation does not imply routing |
| **Validators / recovery** | Conceptual only (`runner: conceptual`) — not executed at build time |
| **Hermes evolution** | Documented (ADR-0018) — not wired; no autonomous recipe mutation |

**Wave inventory:**

| Wave | Recipes |
|------|---------|
| Wave 1 | `game.idle-incremental`, `game.trivia-timer`, `game.branching-narrative`, `game.memory-match`, `game.word-daily` |
| Wave 2 | `game.daily-puzzle-grid`, `game.resource-management-sim`, `game.hangman-lite`, `game.typing-speed-racer`, `game.word-builder` |

---

## 3. Evidence from outcome reports

Three manual outcome reports now exist under [outcome-reports/](outcome-reports/). They are **learning artifacts**, not production telemetry, automated validator results, or Hermes-generated change requests.

| Report | What it stress-tested |
|--------|----------------------|
| [game.resource-management-sim](outcome-reports/game.resource-management-sim.manual-outcome.md) | Sim complexity, allocation tradeoffs, win/loss clarity, and **dashboard/inventory/finance overlap** — resource-management language must not route SaaS or warehouse apps |
| [game.typing-speed-racer](outcome-reports/game.typing-speed-racer.manual-outcome.md) | Timing, WPM/accuracy feedback, mistake penalties, result state, and **typing tutor/form/writing-tool overlap** — speed challenge must not become a lesson page |
| [game.word-builder](outcome-reports/game.word-builder.manual-outcome.md) | Letter pool, validation, duplicate blocking, scoring, hints, and **word-family boundary** — separation from word-daily, hangman-lite, and typing-speed-racer |

**What the reports do not yet provide:**

- Evidence from **actual generated builds** (preview behavior, follow-up edits, failure codes)
- Repeated failure patterns meeting ADR-0018 evidence thresholds
- Proof that word-family or sim routing remains stable under real operator prompts

**Implication for Wave 3:** Outcome reports justify **pausing** before high-ambiguity expansion (card/deck, city-builder, physics). More recipes without generated-build feedback increases guesswork.

---

## 4. Wave 3 option A: DOM-native card/deck systems

### Candidate recipes

| Recipe | Scope sketch |
|--------|----------------|
| `game.card-deck-turn-based` | Turn order, hand, draw/discard piles, play cards, scoring — small deterministic deck |
| `game.deck-builder-lite` | Construct or refine a deck across runs; lighter than full roguelike deckbuilder |

### Benefits

- Fits the existing **DOM-native** model (`stack.dom-game-minimal`).
- Good next step for **state, turns, hands, discard piles, draw piles, and scoring** — distinct from memory-match flip mechanics.
- Avoids Canvas, physics, and render-loop complexity.
- Product-demo value: recognizable “card game” without engine risk.

### Risks

- **Card/deck language is ambiguous** — overlaps memory match, flashcards, poker, trading-card marketplaces, and finance dashboards.
- Must **avoid gambling/casino routing** — slots, blackjack-for-money, betting language.
- Must **avoid finance/trading-card marketplace semantics** — NFT marketplaces, portfolio trackers.
- Needs **careful recipe-specific negatives** and cross-exclusion from `game.memory-match`.
- Routing test suite already large; card family adds another high-overlap cluster.

### Recommendation

**Preferred Wave 3 recipe lane if continuing expansion now** — but **not without an ambiguity review first.** Start with `game.card-deck-turn-based` only after `CARD_DECK_AMBIGUITY_REVIEW.md` (or equivalent) documents positive/negative prompt fixtures and sibling exclusions.

Land schema-only first; route in a separate approved step per [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md).

---

## 5. Wave 3 option B: Deeper DOM-native strategy/sim

### Candidate recipes

| Recipe | Scope sketch |
|--------|----------------|
| `game.turn-based-tactics-lite` | Grid movement, turn order, simple actions — not full 4X |
| `game.city-builder-lite` | Placement, production, population/capacity — extends resource-management sim |

### Benefits

- Extends **resource-management** and grid logic already proven in Wave 2.
- Strong **product-demo value** — “meaningful” generated games for operators.
- Stays DOM-native if scope is tightly bounded.

### Risks

- **Higher state complexity** — more mechanics, more render budget pressure.
- **Context bloat** — composed playbooks approach 12k cap faster.
- **Dashboard/app drift** — city-builder and tactics language overlaps planning tools, GIS dashboards, and project management apps.
- **`game.city-builder-lite` may be too broad** until at least one **actual generated** resource-management build is reviewed against the manual outcome report.

### Recommendation

**Defer** until resource-management-sim (and ideally daily-puzzle-grid) outcomes are validated against real scaffolds — not manual reports alone. If pursued, land **turn-based-tactics-lite** before city-builder-lite; keep both schema-only until routing ambiguity review completes.

---

## 6. Wave 3 option C: Arcade DOM-lite

### Candidate recipes

| Recipe | Scope sketch |
|--------|----------------|
| `game.reaction-time-challenge` | Click/tap when signal appears; score by reaction time |
| `game.rhythm-tap-lite` | Timed tap sequences; streak/combo scoring |

### Benefits

- Still **DOM-native** — buttons, timers, score displays.
- Good for **timing, scoring, streaks, and feedback loops** without physics.
- **Lower ambiguity** than card/deck for routing (fewer sibling recipes).
- Avoids physics stack and Canvas ADR decisions.

### Risks

- **Precise event timing** — rhythm games may need tighter input handling than typical DOM casual games.
- Could become **too shallow** if recipes only produce counters and buttons without a satisfying loop.
- Overlaps **typing-speed-racer** on timer/streak language — needs cross-recipe negatives.

### Recommendation

**Viable secondary lane** if card/deck ambiguity feels too high. Prefer **reaction-time-challenge** before rhythm-tap-lite (simpler timing model). Same schema-first, route-after-approval discipline applies.

---

## 7. Wave 3 option D: Physics Game Pack design track

### Candidate future recipes (not approved)

| Recipe | Scope sketch |
|--------|----------------|
| `game.canvas-arcade-lite` | First Canvas-based arcade loop |
| `game.physics-bounce-lite` | Simple bounce/collision |
| `game.physics-slingshot` | Angry-Birds-style slingshot — later |

### Explicitly not yet

- Fluid simulation
- Where’s My Water-style mechanics
- Multiplayer physics
- Live AI NPC simulations

### Why a separate track

Physics should **not** be added as normal Wave 3 DOM recipes. It likely needs a **separate ADR or design doc** covering:

- Stack assumptions (Canvas vs DOM hybrid, library choices if any)
- Render loop model and frame timing
- Canvas guidance in composed playbooks
- Collision scope and performance limits
- Validation strategy (conceptual vs executable)
- Prompt/routing boundaries (arcade vs sim vs tutor apps)
- Render budget impact — physics guidance may exceed 12k faster than DOM recipes

### Recommendation

Create **`PHYSICS_GAME_PACK_ADR_DRAFT.md`** (or formal ADR) **before any physics recipe**. Do not land `game.canvas-arcade-lite` or `game.physics-bounce-lite` in the current Game Pack without that design lane.

---

## 8. Recommended Wave 3 decision

| Priority | Action |
|----------|--------|
| **1** | **Do not add more recipes immediately** — pause after ten recipes and three outcome reports |
| **2** | **Create a card/deck ambiguity review next** — highest-value prep if recipe expansion continues |
| **3** | **If choosing recipe expansion:** start with `game.card-deck-turn-based` only after ambiguity review; schema-only first |
| **4** | **If choosing architecture instead:** start with a Physics Game Pack ADR draft — no physics recipes until approved |
| **5** | **Keep Build Registry v2 opt-in** — `HAM_BUILD_REGISTRY_V2_ENABLED` off by default; v1 remains default path |

**Default recommendation:** Option A prep (card/deck ambiguity review) over immediate recipe landing. Option D prep in parallel if product direction favors Canvas/physics demos later.

---

## 9. Non-goals

Wave 3 planning does **not** authorize:

- Default Build Registry v2 enablement
- Public kit picker for registry v2 app types
- Generic “game” router
- **New recipes from this checkpoint alone**
- Templates or starter source file cloning
- Autonomous Hermes PRs or recipe mutation
- Executable validator/recovery runners
- Physics recipes without dedicated Physics Game Pack design
- Multiplayer or live services
- Gambling/casino card-game routing
- Fluid simulation, Where’s My Water-style mechanics, or live AI NPC systems

---

## 10. Recommended next artifacts

| Artifact | Purpose |
|----------|---------|
| [ ] **`CARD_DECK_AMBIGUITY_REVIEW.md`** | Positive/negative prompt fixtures; memory-match vs card-battler vs flashcard vs casino exclusions |
| [ ] **`PHYSICS_GAME_PACK_ADR_DRAFT.md`** | Stack, render loop, collision scope, routing boundaries — before any Canvas recipe |
| [ ] **`OUTCOME_REPORT_INDEX.md`** | Index of manual outcome reports + when to add more vs pause |
| [ ] **Lightweight registry reference-checker / JSON Schema proposal** | Formalize YAML conventions beyond Python loader as module count grows |

Optional follow-ups (lower priority):

- CI ratchet from warning-only to blocking after confidence increases
- One **actual generated-build** review logged against an existing outcome report template
- STATUS.md update when Wave 3 direction is chosen (separate docs commit)

---

## 11. References

| Doc | Purpose |
|-----|---------|
| [STATUS.md](STATUS.md) | Live handoff — recipes, routing, validation |
| [WAVE_2_RETROSPECTIVE.md](WAVE_2_RETROSPECTIVE.md) | Wave 2 completion and lessons |
| [WAVE_1_RETROSPECTIVE.md](WAVE_1_RETROSPECTIVE.md) | Wave 1 completion and lessons |
| [OUTCOME_FACTS.md](OUTCOME_FACTS.md) | Outcome facts schema (future Hermes loop) |
| [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md) | Recipe authoring rules |
| [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md) | Routing approval policy |
| [game.resource-management-sim.manual-outcome.md](outcome-reports/game.resource-management-sim.manual-outcome.md) | Sim/dashboard overlap learning artifact |
| [game.typing-speed-racer.manual-outcome.md](outcome-reports/game.typing-speed-racer.manual-outcome.md) | Timing/tutor overlap learning artifact |
| [game.word-builder.manual-outcome.md](outcome-reports/game.word-builder.manual-outcome.md) | Word-family boundary learning artifact |
| [ADR-0016](../adr/0016-generative-build-kit-registry-v2.md) | Registry design |
| [ADR-0017](../adr/0017-build-registry-v2-opt-in-scaffold-wiring.md) | Opt-in scaffold wiring |
| [ADR-0018](../adr/0018-build-kit-evolution-loop-with-hermes.md) | Future Hermes evolution loop |
