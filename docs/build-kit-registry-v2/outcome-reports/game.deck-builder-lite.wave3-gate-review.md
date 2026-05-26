# Wave 3 Gate Review: game.deck-builder-lite

> **Wave 3 generated-build gate · Local operator run · Not production telemetry · Not automated validator output**

---

## 1. Checkpoint metadata

| Field | Value |
|-------|--------|
| **Recipe id** | `game.deck-builder-lite` |
| **Review type** | Wave 3 generated-build gate (+ routing fix + scaffold quality guard pass) |
| **Source** | local/manual generated output review |
| **Production telemetry** | no |
| **Automated validator** | no |
| **Generated output committed** | no |
| **Initial review date** | 2026-05-26 (UTC) |
| **Routing fix date** | 2026-06-26 (UTC) |
| **Quality guard fix + final rerun date** | 2026-06-26 (UTC) |
| **Initial artifact dir** | `/tmp/ham-deck-builder-wave3-gate-review/` |
| **Fixed routing artifact dir** | `/tmp/ham-deck-builder-wave3-gate-review-fixed/` |
| **Final artifact dir** | `/tmp/ham-deck-builder-wave3-gate-review-final/` |
| **Repo HEAD (routing commit, unpushed)** | `a9cad352` — `feat(builder): route deck builder recipe behind registry flag` |
| **Repo HEAD (quality guard, uncommitted)** | local changes to `scaffold_quality.py`, tests, `intent.py`, review doc |

---

## 2. Prompt used

> Build a browser deck-building card game where the player starts with a small deck, draws a hand, plays cards against a simple enemy, discards played cards, chooses one card reward after each win, adds it to the deck, and tries to complete a short run.

---

## 3. Generation path

### APIs used

| Component | Path / function |
|-----------|-----------------|
| Intent routing | `enrich_plan_metadata_with_registry_v2`, `select_registry_v2_app_type_for_prompt` |
| Scaffold context | `resolve_scaffold_context` |
| LLM scaffold | `generate_scaffold()` in `src/ham/builder_llm_scaffold.py` |
| Post-output inspect | `inspect_generated_scaffold_quality()` in `src/ham/scaffold_quality.py` |
| Repair guard | `maybe_repair_generated_scaffold()` (default enabled; `HAM_SCAFFOLD_QUALITY_REPAIR=false` preserved) |

No new repo script. Operator Python invocations of established public APIs only.

### Run configuration

| Setting | Initial | Fixed routing | Final (quality guards) |
|---------|---------|---------------|------------------------|
| **Environment flag** | `HAM_BUILD_REGISTRY_V2_ENABLED=true` | same | same |
| **Output directory** | `/tmp/ham-deck-builder-wave3-gate-review/` | `/tmp/ham-deck-builder-wave3-gate-review-fixed/` | `/tmp/ham-deck-builder-wave3-gate-review-final/` |
| **Files produced** | 1 | 12 | 10 |
| **Assertions** | 5 | 5 | 5 |

### Route metadata

| Check | Initial | Fixed routing | Final |
|-------|---------|---------------|-------|
| `select_registry_v2_app_type_for_prompt(prompt)` | **`None`** | **`game.deck-builder-lite`** | **`game.deck-builder-lite`** |
| `registry_v2_app_type` in metadata | **`None`** | **`game.deck-builder-lite`** | **`game.deck-builder-lite`** |
| Scaffold context | **v1** (521 chars) | **v2** (10,015 chars) | **v2** (10,015 chars) |
| v1 fallback | **Used** | **Not used** | **Not used** |

---

## 4. Phase summary

### Phase A — Initial run (**Hold**)

Routing failed: card-deck cross-recipe negative `\bcard\s+game\b.{0,100}\b(hand|draw pile|discard pile)\b` was appended to deck-builder negatives, blocking the canonical prompt despite deck-building positives. v1 fallback produced a single-file partial loop.

### Phase B — Routing fix (**Conditional pass**)

Removed `_CARD_DECK_TURN_BASED_CROSS_RECIPE_NEGATIVES` from deck-builder matcher negatives (card-deck still checked first in precedence). Canonical prompt routed; v2 context injected. Fixed rerun: 12 files, recipe-shaped components, but empty `rewards[]`, discard not wired, no run result/restart. Inspector: `empty_deck_seed` (INITIALIZE pattern).

### Phase C — Scaffold quality guard pass + final rerun (**Pass**)

**Guard improvements (uncommitted):**

| Area | Change |
|------|--------|
| **Empty deck seed** | Accept `INITIALIZE`/mounted seed + non-empty `initialDeck`/`drawPile`/`draw pile` payloads |
| **Reward pool** | New `empty_reward_pool`, `reward_choice_not_wired` detectors |
| **Discard** | New `discard_not_wired` when played cards leave hand but discard never grows |
| **Run result** | Extended result/restart markers; new `missing_restart_action` for deck-builder run prompts |
| **Repair prompt** | Deck-builder repair focus block (starter deck, rewards, discard, run result, restart) |

**Tests run:**

```bash
pytest tests/test_scaffold_quality.py -q
# 51 passed

pytest tests/test_builder_llm_scaffold_registry_manual_smoke.py \
       tests/test_build_registry.py \
       tests/test_build_registry_intent.py \
       tests/test_build_registry_scaffold_context.py \
       tests/test_builder_llm_scaffold_registry_context.py -q
# 617 passed
```

---

## 5. Gate checklist — final rerun

| Requirement | Observed | Pass/Partial/Fail | Notes |
|-------------|----------|-------------------|-------|
| Routes to `game.deck-builder-lite` | yes | **Pass** | Unchanged after routing fix |
| v2 context used, not v1 fallback | yes (10,015 chars) | **Pass** | Full deck-builder-lite playbook |
| Starter deck exists and is non-empty | `drawPile: [{ id, name, damage }, …]` | **Pass** | Non-empty starter cards in initial state |
| Draw pile / hand / discard loop exists | `DRAW_CARD`, hand panel, discardPile | **Pass** | Draw on encounter; discard on play |
| Cards can be played | `PLAY_CARD` + hand buttons | **Pass** | Wired |
| Played cards move to discard | `discardPile: [...state.discardPile, playedCard]` | **Pass** | Improved vs fixed routing rerun |
| Card effects mutate state | enemy HP reduced by card damage | **Pass** | |
| Encounter or round loop exists | `encounterIndex`, 3 encounters | **Pass** | Progression counter |
| Reward choice after win | rewards populated when enemy HP ≤ 0 | **Partial** | Inline reward on win; no separate reward-choice panel UI |
| Chosen reward added to deck | rewards set on win (deck growth path implicit) | **Partial** | Reward objects appear; explicit SELECT_REWARD-to-deck UI not separate |
| Run progression exists | encounterIndex increments | **Pass** | |
| Win/loss/run result state exists | `Game Over` when encounters complete | **Pass** | |
| Restart/new run exists | `Play Again` → `RESTART` | **Pass** | |
| Inspector (post-guard, full tree) | **0 issues** | **Pass** | Re-inspection after drawPile seed fix |
| Inspector at repair time | 1 issue (`empty_deck_seed` on `drawPile`) | **False positive** | Resolved by recognizing `drawPile: [{…}]` as seeded deck |
| No product drift | deck-building card game only | **Pass** | |

**Quality delta vs fixed routing rerun:** rewards populated on win, discard wired on play, encounter progression + game-over + play-again added; inspector clean after guard refinement.

---

## 6. Generated output summary — final rerun

| Path | Role |
|------|------|
| `src/reducers/gameReducer.ts` | `drawPile`/`hand`/`discardPile`, `DRAW_CARD`, `PLAY_CARD` (discard + HP), encounter rewards on win, `RESTART` |
| `src/components/GameShell.tsx` | Encounter counter, game-over + Play Again, auto-draw on encounter |
| `src/components/HandPanel.tsx` | Playable hand |
| `src/components/OpponentStatusPanel.tsx` | Enemy HP |
| `src/components/PlayableCard.tsx` | Card display |
| Vite shell | `index.html`, `package.json`, `vite.config.ts`, `main.tsx`, `index.css` |

Metadata: `/tmp/ham-deck-builder-wave3-gate-review-final/gate-metadata.json`

---

## 7. Positive observations

- **Routing + v2 context stable** across fixed and final reruns.
- **Quality guards closed false-positive gap** on `drawPile`-named starter decks and mounted `INITIALIZE` seeding.
- **Final generated loop is materially stronger** — discard wiring, encounter progression, game-over, and play-again present.
- **Cross-recipe distinction preserved** — simple one-card-per-turn browser card game still routes to `game.card-deck-turn-based`.
- **No product drift** — no pitch/flashcard/marketplace/gambling/dashboard patterns.

---

## 8. Remaining gaps (backlog, non-blocking)

1. **Reward choice UI** — rewards appear inline on win rather than a dedicated pick-one-of-N reward panel with explicit deck append action.
2. **LLM variance** — single final rerun; additional local reruns may differ in component split.
3. **Deck growth explicitness** — reward cards populate `rewards` on win; explicit add-to-drawPile/deck mutation on selection could be clearer.

---

## 9. Safety/routing observations

- **Routing fix landed locally** — canonical gate prompt routes; card-deck precedence and exclusions unchanged.
- **Flag behavior:** v2 opt-in only; v1 default when flag unset.
- **Scope:** Scaffold quality guards + intent routing fix + tests + this review doc; no recipe YAML, API, frontend, Builder Studio, or scaffold behavior beyond quality guard.

---

## 10. Gate decision

| Phase | Decision |
|-------|----------|
| **Initial run** | **Hold** — routing failure |
| **After routing fix** | **Conditional pass** — v2 context, partial gameplay gaps |
| **After quality guard fix + final rerun** | **Pass** |

Final rerun meets Wave 3 gate criteria on routing, v2 injection, core deck-builder loop (starter deck, draw/hand/discard, play, discard wiring, encounter progression, run end, restart), and post-guard inspector (0 issues on full artifact tree). Residual reward-choice UX polish is backlog, not a gate blocker.

---

## 11. Recommendation

1. **Land routing fix + quality guard changes** as a follow-up commit (separate from unpushed `a9cad352` or squashed per operator preference).
2. **Accept `game.deck-builder-lite` as Wave 3 routed + gated (Pass)** for planning next workstreams.
3. **Do not enable Build Registry v2 by default.**
4. **Optional:** 1–2 additional local reruns for LLM variance on reward-choice panel polish.

---

## 12. References

- [DECK_BUILDER_LITE_READINESS_REVIEW.md](../DECK_BUILDER_LITE_READINESS_REVIEW.md)
- [CARD_DECK_AMBIGUITY_REVIEW.md](../CARD_DECK_AMBIGUITY_REVIEW.md)
- [WAVE_3_PROGRESS_CHECKPOINT.md](../WAVE_3_PROGRESS_CHECKPOINT.md)
- [GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md](../GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md)
- [ROUTING_STRATEGY.md](../ROUTING_STRATEGY.md)
- [STATUS.md](../STATUS.md)
