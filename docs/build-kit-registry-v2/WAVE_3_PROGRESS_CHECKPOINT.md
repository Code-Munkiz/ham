# Build Registry v2 Wave 3 Progress Checkpoint

Progress checkpoint after **`game.card-deck-turn-based`** and **`game.reaction-time-challenge`** both landed on `origin/main` and passed generated gate reviews. This document records Wave 3 completion status and the recommended next lane — it is **not** approval for another recipe, routing change, runtime enablement, or default v2 rollout. For live status see [STATUS.md](STATUS.md).

**Checkpoint:** `origin/main` at `8bdc31e2` — twelve recipes, 273 indexed modules, all routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`.

**Related Wave 3 commits (schema → routing → gate review):**

| Recipe | Schema | Routing | Gate review |
|--------|--------|---------|-------------|
| `game.card-deck-turn-based` | prior Wave 3 land | prior Wave 3 land | [wave3-gate-fix-review](./outcome-reports/game.card-deck-turn-based.wave3-gate-fix-review.md) — **Pass** |
| `game.reaction-time-challenge` | `2f586559` | `7b2181ce` | [wave3-gate-review](./outcome-reports/game.reaction-time-challenge.wave3-gate-review.md) — **Pass** |

---

## 1. Executive summary

**Wave 3 has two completed routed recipes.**

- **`game.card-deck-turn-based`** and **`game.reaction-time-challenge`** are authored, validated, routed behind the opt-in flag, and have **Pass** generated gate reviews on local operator runs.
- The **scaffold quality repair guard** is live in the scaffold pipeline (repair can be disabled via `HAM_SCAFFOLD_QUALITY_REPAIR=false`).
- **Build Registry v2 remains opt-in** — routing and v2 playbook context apply only when `HAM_BUILD_REGISTRY_V2_ENABLED` is truthy.
- **v1 remains default** when the flag is unset or false.
- **Next recommended recipe:** **`game.rhythm-tap-lite`** — schema-first, route-after-approval, then generated gate review.

---

## 2. Current baseline

| Dimension | State |
|-----------|--------|
| **Recipes** | 12 |
| **Indexed modules** | 273 |
| **Routing** | All 12 recipes route narrowly behind `HAM_BUILD_REGISTRY_V2_ENABLED` |
| **Default lane** | v1 Builder Kit JSON when flag off |
| **Templates / starter files** | None — generative playbooks only |
| **API / frontend / Builder Studio** | No Wave 3 changes |
| **Scaffold quality repair guard** | Active — post-output inspection + optional one-pass repair |
| **Generated app output** | Not committed — gate artifacts under `/tmp/` only |
| **Validation** | `scripts/validate_game_pack_registry.py` + registry/scaffold pytest suites green |

---

## 3. Completed Wave 3 recipes

### `game.card-deck-turn-based`

| Field | Value |
|-------|--------|
| **Status** | Validated — schema + compose/render complete |
| **Routing** | Yes (narrow) — draw/hand/discard/turn/card-play intent behind flag |
| **Generated gate** | **Pass** — final rerun clean inspector, playable loop |
| **Key risk resolved** | Empty deck seeding, ignored `NEW_GAME` payload, missing victory wiring, no-op `DRAW_CARD` — addressed via scaffold quality guard + card-deck repair focus |

### `game.reaction-time-challenge`

| Field | Value |
|-------|--------|
| **Status** | Validated — schema + compose/render complete (~11.2k render) |
| **Routing** | Yes (narrow) — wait/signal/false-start/reaction-ms intent behind flag |
| **Generated gate** | **Pass** — clean inspector, core wait → green → click → ms → best score → play again loop |
| **Key risk resolved** | Pomodoro/stopwatch/typing/rhythm/medical/dashboard/gambling/physics prompt drift excluded at routing layer; DOM-native timing loop proven without Canvas/physics |

---

## 4. Quality repair impact

The generated-quality detour (see [WAVE_3_POST_QUALITY_REPAIR_CHECKPOINT.md](./WAVE_3_POST_QUALITY_REPAIR_CHECKPOINT.md)) materially changed Wave 3 outcomes:

| Improvement | Effect |
|-------------|--------|
| **Shell-only outputs reduced** | Playability hardening + repair prompt push toward implemented handlers |
| **No-op / stub reducers guarded** | `noop_reducer_action`, `empty_primary_handler`, `stub_placeholder` detection |
| **Timer / result gaps improved** | `timer_duration_mismatch`, `missing_result_state`, `stale_state_win_check` |
| **Card-deck seed / victory wiring** | `empty_deck_seed`, `ignored_seed_payload`, `missing_victory_wiring` — card-deck gate moved from Conditional pass → **Pass** |
| **Generated gate reviews in Wave rhythm** | Schema → route → `/tmp/` generated run → outcome report is now the standard Wave 3 completion bar |

Generated gate reviews are **local operator evidence**, not production telemetry or automated CI gates.

---

## 5. Remaining cautions

- **Generated quality is improved but still heuristic.** Single-run Pass does not guarantee every future LLM output is playable.
- **Manual generated reviews remain required.** Outcome reports and gate reviews are the source of truth for recipe readiness.
- **`game.deck-builder-lite` remains higher risk** — deck construction, collection, and marketplace-adjacent prompts need stronger negatives and more guard coverage; defer until after another lower-risk DOM timing/input recipe.
- **Physics / Canvas still needs a dedicated ADR/design track** — do not fold Canvas/physics recipes into Wave 3 DOM-native lanes without explicit design approval.

---

## 6. Recommended next Wave 3 step

1. **Author `game.rhythm-tap-lite` schema-only next** — beat/tap timing loop, conservative negatives vs reaction-time and music-app drift.
2. **Keep schema-first, route-after-approval** — no routing until intent tests and ambiguity review are explicit.
3. **Run generated gate review after routing** — one operator run under `/tmp/`, docs-only outcome report, no committed generated output.
4. **Do not start `game.deck-builder-lite` yet** — wait until rhythm-tap-lite completes the DOM timing/input lane proof point.

---

## 7. Non-goals

- No default v2 enablement (`HAM_BUILD_REGISTRY_V2_ENABLED` stays opt-in).
- No public kit picker or Builder Studio registry UX from this checkpoint.
- No new recipe from this checkpoint alone.
- No routing from this checkpoint alone.
- No generated app output committed.
- No autonomous Hermes evolution-loop changes.
- No physics / Canvas work from this checkpoint.

---

## 8. References

- [WAVE_3_POST_QUALITY_REPAIR_CHECKPOINT.md](./WAVE_3_POST_QUALITY_REPAIR_CHECKPOINT.md)
- [WAVE_3_CARD_DECK_CHECKPOINT.md](./WAVE_3_CARD_DECK_CHECKPOINT.md)
- [game.card-deck-turn-based.wave3-gate-fix-review.md](./outcome-reports/game.card-deck-turn-based.wave3-gate-fix-review.md)
- [game.reaction-time-challenge.wave3-gate-review.md](./outcome-reports/game.reaction-time-challenge.wave3-gate-review.md)
- [GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md](./GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md)
- [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md)
- [STATUS.md](./STATUS.md)
