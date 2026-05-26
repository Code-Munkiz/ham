# Build Registry v2 Wave 3 Completion Checkpoint

Closeout checkpoint after all four Wave 3 recipes landed on `origin/main`, passed generated gate reviews, and the deck-builder quality guard pass completed. This document **closes Wave 3** — it is **not** approval for another recipe, routing change, runtime enablement, or default v2 rollout. For live status see [STATUS.md](STATUS.md).

**Checkpoint:** `origin/main` at `5a5d0864` — fourteen recipes, 323 indexed modules, all routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`.

**Wave 3 closeout commits (schema → routing → gate review → quality guard):**

| Recipe | Schema | Routing | Gate review | Quality guard |
|--------|--------|---------|-------------|---------------|
| `game.card-deck-turn-based` | prior Wave 3 land | prior Wave 3 land | [wave3-gate-fix-review](./outcome-reports/game.card-deck-turn-based.wave3-gate-fix-review.md) — **Pass** | card-deck seed/victory |
| `game.reaction-time-challenge` | `2f586559` | `7b2181ce` | [wave3-gate-review](./outcome-reports/game.reaction-time-challenge.wave3-gate-review.md) — **Pass** | timer/result baseline |
| `game.rhythm-tap-lite` | prior Wave 3 land | prior Wave 3 land | [wave3-gate-review](./outcome-reports/game.rhythm-tap-lite.wave3-gate-review.md) — **Pass** | rhythm miss/result |
| `game.deck-builder-lite` | `42fbb600` | `a9cad352` + `d5115e79` | [wave3-gate-review](./outcome-reports/game.deck-builder-lite.wave3-gate-review.md) — **Pass** | reward/discard/run-result |

---

## 1. Executive summary

**Wave 3 is complete.**

- Four Wave 3 recipes were **authored**, **routed behind the registry flag**, and **generated-gate reviewed** with **Pass** final decisions.
- The **scaffold quality repair guard** was introduced and hardened during Wave 3 — post-output inspection, optional one-pass repair, and deck-builder-specific detectors for reward pools, discard wiring, and run-result/restart gaps.
- **Build Registry v2 remains opt-in** — routing and v2 playbook context apply only when `HAM_BUILD_REGISTRY_V2_ENABLED` is truthy.
- **v1 remains default** when the flag is unset or false.
- **No templates or starter source files** were created — recipes remain generative playbooks only.
- **No API, frontend, or Builder Studio changes** were made during Wave 3 closeout.
- **Generated app output has not been committed** — all gate artifacts remain under `/tmp/` only.

---

## 2. Final Wave 3 baseline

| Dimension | State |
|-----------|--------|
| **Recipes** | 14 |
| **Indexed modules** | 323 |
| **Routing** | All 14 recipes route narrowly behind `HAM_BUILD_REGISTRY_V2_ENABLED` |
| **Default lane** | v1 Builder Kit JSON when flag off |
| **Templates / starter files** | None — generative playbooks only |
| **Generated app output** | Not committed — gate artifacts under `/tmp/` only |
| **Scaffold quality repair guard** | Active — post-output inspection + optional one-pass repair (`HAM_SCAFFOLD_QUALITY_REPAIR=false` disables repair) |
| **Public kit picker / default v2 enablement** | None |
| **API / frontend / Builder Studio** | No Wave 3 changes |
| **Validation** | `scripts/validate_game_pack_registry.py` + registry/scaffold pytest suites green |

---

## 3. Completed Wave 3 recipes

| Recipe | Lane | Status | Routing | Generated gate result | Key risk resolved |
|--------|------|--------|---------|----------------------|-------------------|
| `game.card-deck-turn-based` | Card/deck | Authored + routed | Behind flag | **Pass** | Deck/hand/discard/victory wiring |
| `game.reaction-time-challenge` | Arcade DOM-lite / timing | Authored + routed | Behind flag | **Pass** | Wait/signal/false-start/reaction-ms loop |
| `game.rhythm-tap-lite` | Arcade DOM-lite / rhythm timing | Authored + routed | Behind flag | **Pass** | Beat/timing/miss/result loop |
| `game.deck-builder-lite` | Card/deck progression | Authored + routed | Behind flag | **Pass** | Starter deck/reward/discard/run-result loop |

**Wave 3 scope decision:** `game.turn-based-tactics-lite` and `game.city-builder-lite` were **not** added to Wave 3. Tactics belongs in Wave 4 or a later strategy/sim lane; city-builder is broader and should wait until sim outputs are better understood.

---

## 4. Scaffold quality repair work

Baseline generated-quality reviews showed that **routing and v2 context injection worked**, but **generated playability had gaps** broader than card-deck alone:

| Problem class | Examples |
|---------------|----------|
| Shell-only outputs | UI scaffold without implemented gameplay handlers |
| No-op / stub logic | Primary reducer actions returning unchanged state |
| Timer / result gaps | Wrong duration, missing result screen, stale closure win checks |
| Card-deck gaps | Empty deck seed, ignored `NEW_GAME` payload, missing victory wiring |
| Rhythm gaps | Weak miss feedback, stale `setFinalScore(score)` capture |
| Deck-builder gaps | Empty reward pools, discard not wired, missing run result/restart |

**What landed during Wave 3:**

1. **Scaffold prompt hardening** — playability expectations pushed into generation prompts.
2. **One-pass quality repair guard** — `inspect_generated_scaffold_quality()` + `maybe_repair_generated_scaffold()` in the scaffold pipeline.
3. **Guard extensions** — reducers, timers, results, card-deck seed/victory, rhythm miss/result, deck-builder reward/discard/run-result detectors.
4. **Deck-builder repair focus block** — explicit guidance for starter deck, reward pool, discard wiring, encounter progression, run result, and restart.

**Outcome:** All sampled v2 outputs reached at least **partially playable** after repair work; Wave 3 gate recipes reached **Pass** on final reruns. **Wave 3 gates now include generated output review** as a standard completion bar — schema → route → `/tmp/` generated run → outcome report.

Generated gate reviews remain **local operator evidence**, not production telemetry or automated CI gates.

---

## 5. Routing posture

- All Wave 3 routes remain behind **`HAM_BUILD_REGISTRY_V2_ENABLED`**.
- **v1 remains default** when the flag is off.
- Routing remains **conservative and recipe-specific** — no generic card/deck/reaction/rhythm/timer router was added.
- **Negative prompt families remain guarded:**
  - pitch/slide decks
  - flashcards
  - marketplaces / NFT / card trading
  - gambling / casino
  - dashboards / kanban / card layouts
  - medical / assessment prompts
  - Pomodoro / stopwatch / metronome / music-player / karaoke
  - physics / Canvas prompts unless explicitly designed later

See [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md) and [CARD_DECK_AMBIGUITY_REVIEW.md](./CARD_DECK_AMBIGUITY_REVIEW.md) for card/deck split posture.

---

## 6. What Wave 3 proved

| Proof point | Evidence |
|-------------|----------|
| **Schema-first, route-after-approval rhythm scales** | Four Wave 3 recipes added without breaking the 14-recipe / 323-module registry |
| **Conservative routing can scale** | Explicit negative tests and cross-recipe precedence prevent drift (e.g. card-deck vs deck-builder split) |
| **Generated gate reviews are necessary** | Routing + v2 context alone did not guarantee playable output; gate reviews caught gaps |
| **Scaffold repair guard materially improves playability** | Card-deck, rhythm-tap, and deck-builder moved from Conditional pass / Hold → **Pass** after guard hardening |
| **DOM-native game recipes expand without templates** | Timing, rhythm, and deck-progression loops proven without Canvas/physics |
| **Card/deck ambiguity is manageable** | Turn-based card battle vs deck-building progression separated with careful routing posture |

---

## 7. Remaining cautions

- **323 modules is large enough that registry reference drift is a real risk** — orphan refs, duplicate ids, and stale module counts need automated checking.
- **Generated quality is improved, not magically solved forever** — LLM variance and prompt drift can still produce shallow or broken outputs on any single run.
- **Quality guard is heuristic, not a full app validator** — pattern checks catch common failure modes; they do not prove runtime correctness or UX polish.
- **Manual generated gate reviews remain required** — outcome reports and operator smoke remain the source of truth for recipe readiness.
- **`game.turn-based-tactics-lite` should wait for Wave 4** — not a Wave 3 recipe; needs strategy/sim direction first.
- **`game.city-builder-lite` should wait beyond Wave 4** — or until sim outputs are better understood.
- **Physics / Canvas still requires an ADR/design track** before any physics-family recipe.

---

## 8. Recommended next workstream

Wave 3 is closed. **Do not add another recipe immediately.**

1. **Registry hardening** — lightweight reference checker, JSON Schema proposal or implementation, orphan/reference/duplicate/module-count checks. See [REGISTRY_REFERENCE_CHECKER_PROPOSAL.md](./REGISTRY_REFERENCE_CHECKER_PROPOSAL.md).
2. **Wave 4 strategy/sim direction** — consider authoring `WAVE_4_STRATEGY_SIM_DIRECTION.md` before `game.turn-based-tactics-lite`.
3. **Physics / Canvas ADR** — keep physics behind a dedicated design doc; no Canvas recipes until ADR exists.
4. **Generated gate reviews for future recipes** — any future routed recipe must follow schema → route → `/tmp/` gate → outcome report rhythm.
5. **No default v2 enablement** — `HAM_BUILD_REGISTRY_V2_ENABLED` stays opt-in.

---

## 9. Deferred candidates

| Candidate | Status | Notes |
|-----------|--------|-------|
| `game.turn-based-tactics-lite` | Wave 4 candidate | **Not Wave 3** — strategy/sim lane; needs direction doc first |
| `game.city-builder-lite` | Later strategy/sim candidate | Broader sim scope; wait until sim outputs understood |
| `game.canvas-arcade-lite` | Deferred | Only after Canvas/physics design |
| `game.physics-bounce-lite` | Deferred | Only after Physics Game Pack ADR |
| `game.physics-slingshot` | Later | Physics family |
| Fluid simulation / multiplayer / live AI NPC systems | Not near-term | Out of scope for current registry rhythm |

---

## 10. Non-goals

This checkpoint does **not** authorize:

- Default v2 enablement (`HAM_BUILD_REGISTRY_V2_ENABLED` remains opt-in)
- Public kit picker or Builder Studio registry UX
- New recipes from this checkpoint
- Routing changes from this checkpoint
- Templates or starter source files
- Generated app output committed from `/tmp/`
- Autonomous Hermes PRs or evolution-loop automation
- Executable validators or recovery runners from this checkpoint alone
- Physics / Canvas work from this checkpoint

---

## 11. References

- [STATUS.md](./STATUS.md)
- [WAVE_3_PROGRESS_CHECKPOINT.md](./WAVE_3_PROGRESS_CHECKPOINT.md)
- [WAVE_3_POST_QUALITY_REPAIR_CHECKPOINT.md](./WAVE_3_POST_QUALITY_REPAIR_CHECKPOINT.md)
- [WAVE_3_CARD_DECK_CHECKPOINT.md](./WAVE_3_CARD_DECK_CHECKPOINT.md)
- [DECK_BUILDER_LITE_READINESS_REVIEW.md](./DECK_BUILDER_LITE_READINESS_REVIEW.md)
- [CARD_DECK_AMBIGUITY_REVIEW.md](./CARD_DECK_AMBIGUITY_REVIEW.md)
- [GENERATED_QUALITY_BASELINE_REVIEW.md](./GENERATED_QUALITY_BASELINE_REVIEW.md)
- [GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md](./GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md)
- [outcome-reports/game.card-deck-turn-based.wave3-gate-fix-review.md](./outcome-reports/game.card-deck-turn-based.wave3-gate-fix-review.md)
- [outcome-reports/game.reaction-time-challenge.wave3-gate-review.md](./outcome-reports/game.reaction-time-challenge.wave3-gate-review.md)
- [outcome-reports/game.rhythm-tap-lite.wave3-gate-review.md](./outcome-reports/game.rhythm-tap-lite.wave3-gate-review.md)
- [outcome-reports/game.deck-builder-lite.wave3-gate-review.md](./outcome-reports/game.deck-builder-lite.wave3-gate-review.md)
- [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md)
- [AUTHORING_GUIDE.md](./AUTHORING_GUIDE.md)
- [REGISTRY_REFERENCE_CHECKER_PROPOSAL.md](./REGISTRY_REFERENCE_CHECKER_PROPOSAL.md)
