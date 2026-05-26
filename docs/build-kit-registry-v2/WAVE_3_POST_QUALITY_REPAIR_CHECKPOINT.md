# Build Registry v2 Wave 3 Post-Quality-Repair Checkpoint

Completion checkpoint after the **generated-quality repair detour** landed on `origin/main`. This document records what was fixed, what was proven, what remains imperfect, and how Wave 3 should resume — it is **not** approval for another recipe, routing change, or runtime enablement. For live status see [STATUS.md](STATUS.md).

**Checkpoint:** `origin/main` at `6a79b6bf` — eleven recipes, 247 indexed modules, all routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`.

**Related commits (generated-quality detour):**

| Hash | Subject |
|------|---------|
| `fb047c8c` | `fix(builder): harden scaffold prompt playability` |
| `93aa8c05` | `fix(builder): repair low-quality scaffold outputs` |
| `3bb67439` | `fix(builder): tighten scaffold quality repair guard` |
| `50c0940a` | `fix(builder): close scaffold quality timer and result gaps` |
| `6a79b6bf` | `fix(builder): close card deck generated quality gate` |

---

## 1. Executive summary

**Wave 3 card-deck is complete enough to proceed.**

The generated-quality gap was **broader than card-deck alone** — shell-only outputs, no-op reducers, dispatch/reducer mismatches, and timer/result wiring failures appeared across multiple sampled v2 recipes. The **scaffold quality repair guard** is now live behind the existing scaffold pipeline (`HAM_SCAFFOLD_QUALITY_REPAIR=false` still disables repair).

**Card-deck generated gate is now Pass.** Final rerun (`/tmp/ham-card-deck-wave3-gate-review-final/`) had a clean inspector, non-empty deck/draw path, play/discard/HP/victory wiring, and no committed generated app output.

**Wave 3 can resume**, but new recipes should still be chosen carefully — schema-first, route-after-approval, conservative negatives, and manual outcome review remain required.

---

## 2. What was fixed

| Gap class | Guard / behavior |
|-----------|------------------|
| Shell-only generated outputs | Repair prompt + playability hardening; post-output quality inspection |
| No-op reducer actions | `noop_reducer_action` — primary gameplay actions that return state unchanged |
| Empty / log-only handlers | `empty_primary_handler`, `stub_placeholder` |
| Dispatch / reducer mismatches | `dispatch_reducer_mismatch`, `import_export_mismatch` |
| Timer / result gaps | `timer_duration_mismatch`, `missing_result_state`, `stale_state_win_check` |
| Card-deck empty deck/hand seed | `empty_deck_seed`, `ignored_seed_payload` |
| Card-deck victory wiring | `missing_victory_wiring` — enemy HP reduced but win/result never fires |

Repair is conditional: issues are detected, a focused repair prompt is built, and one repair pass runs when enabled. Remaining issues are logged after repair.

---

## 3. Current proof points

| Proof | Evidence |
|-------|----------|
| Sampled v2 outputs reach at least Partially playable after repair guard | Baseline reviews before/after repair guard; timer, result, and card-deck reruns |
| Card-deck final rerun — clean inspector | 0 issues post-output on `/tmp/ham-card-deck-wave3-gate-review-final/` |
| Card-deck gameplay loop | Non-empty deck/draw path, hand population, discard on play, HP mutation, victory state |
| Tests green | **34** scaffold quality tests; **435** registry/scaffold suite tests |
| No generated app output committed | All gate reruns under `/tmp/` only |
| No API / frontend / Builder Studio changes | Guard lives in `src/ham/scaffold_quality.py` + tests + docs |

**Card-deck gate decision:** **Pass** — safe to discuss next Wave 3 recipe direction. Minor gap: restart/new-round UX can still improve.

---

## 4. What remains imperfect

- **Generated quality is improved, not magically solved forever.** LLM variance and prompt drift can still produce shallow or broken outputs on any single run.
- **Resource sim can still be shallow.** Economy loops may pass inspection while lacking depth or balance.
- **Card-deck restart UX can improve.** Final pass lacked an explicit play-again control in `ResultsPanel`.
- **Inspector is heuristic, not a full app validator.** String/pattern checks catch common failure modes; they do not prove runtime correctness or UX polish.
- **Manual review remains required.** Outcome reports, gate reviews, and operator smoke remain the source of truth for recipe readiness.

---

## 5. Wave 3 decision options

### `game.reaction-time-challenge`

| Factor | Assessment |
|--------|------------|
| Risk | **Lower** — simple DOM timing/reflex loop |
| Value | Tests timing/input hardening on a new axis |
| Engine | DOM-native; no Canvas/physics dependency |
| Confidence | **Good confidence recipe** — narrow intent, clear win/loss, minimal state surface |

### `game.deck-builder-lite`

| Factor | Assessment |
|--------|------------|
| Risk | **Higher** — deck construction + run progression ambiguity |
| Value | Higher product value if done well |
| Overlap | Pitch decks, flashcards, marketplace, dashboard drift |
| Recommendation | **Remain deferred** until at least one more stable card/deck-style generation cycle or explicit operator approval |

See [CARD_DECK_AMBIGUITY_REVIEW.md](./CARD_DECK_AMBIGUITY_REVIEW.md) for the turn-based vs deck-builder split.

### Physics / Canvas

| Factor | Assessment |
|--------|------------|
| Status | **Still deferred** |
| Prerequisite | Separate ADR/design track before any physics-family recipe |

---

## 6. Recommendation

1. **Next Wave 3 recipe lane:** `game.reaction-time-challenge`
2. **Do not start** `game.deck-builder-lite` yet
3. **Do not start** physics/Canvas recipes yet
4. **Preserve rhythm:** schema-first authoring → validation → conservative routing → manual generated-output gate → docs checkpoint

---

## 7. Non-goals

This checkpoint does **not** authorize:

- Default v2 enablement (`HAM_BUILD_REGISTRY_V2_ENABLED` remains opt-in)
- Public kit picker or Builder Studio routing UI
- A new recipe from this checkpoint alone
- Routing changes from this checkpoint alone
- Committing generated app output from `/tmp/`
- Autonomous Hermes or API/frontend changes

---

## 8. References

- [WAVE_3_CARD_DECK_CHECKPOINT.md](./WAVE_3_CARD_DECK_CHECKPOINT.md) — card-deck recipe authored and routed
- [GENERATED_QUALITY_BASELINE_REVIEW.md](./GENERATED_QUALITY_BASELINE_REVIEW.md) — pre-repair baseline
- [GENERATED_QUALITY_BASELINE_AFTER_REPAIR_GUARD.md](./GENERATED_QUALITY_BASELINE_AFTER_REPAIR_GUARD.md) — post-repair-guard baseline
- [GENERATED_QUALITY_REPAIR_GUARD_V2_REVIEW.md](./GENERATED_QUALITY_REPAIR_GUARD_V2_REVIEW.md) — v2 guard review
- [GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md](./GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md) — timer/result gap pass
- [outcome-reports/game.card-deck-turn-based.wave3-gate-fix-review.md](./outcome-reports/game.card-deck-turn-based.wave3-gate-fix-review.md) — final card-deck gate (Pass)
- [CARD_DECK_AMBIGUITY_REVIEW.md](./CARD_DECK_AMBIGUITY_REVIEW.md) — turn-based vs deck-builder ambiguity
- [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md) — conservative routing model
