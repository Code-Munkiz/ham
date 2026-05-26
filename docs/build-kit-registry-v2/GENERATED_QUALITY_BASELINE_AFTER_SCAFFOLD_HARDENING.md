# Generated Quality Baseline After Scaffold Hardening

> **Local/manual generated-output review · Not production telemetry · Single prompt patch trial**

**Review date:** 2026-05-26 (UTC)

Prior baseline: [GENERATED_QUALITY_BASELINE_REVIEW.md](./GENERATED_QUALITY_BASELINE_REVIEW.md)

---

## 1. Executive summary

**What changed:** A minimal playability hardening patch was added to `_SCAFFOLD_SYSTEM_PROMPT` in `src/ham/builder_llm_scaffold.py` (~6 new Rules lines per [SCAFFOLD_PROMPT_PLAYABILITY_HARDENING_PROPOSAL.md](./SCAFFOLD_PROMPT_PLAYABILITY_HARDENING_PROPOSAL.md)).

**Quality outcome:** **Mixed improvement** — not uniform across recipes.

| Direction | Recipes |
|-----------|---------|
| **Improved** | `game.typing-speed-racer` (v2), `game.resource-management-sim` (v2) |
| **Unchanged / still weak** | `game.card-deck-turn-based` (v2), `game.memory-match` (v2) |
| **Regressed** | `game.word-builder` (v2) — inline logic replaced by stub reducer |
| **v1 comparison stable** | memory-match and card-deck v1 remain partially playable |

**Routing and safety:** All v2 samples routed correctly with v2 context. **No safety drift** observed.

**Conclusion:** Scaffold prompt hardening **helps some state-heavy recipes** but is **not sufficient alone** for multi-mechanic loops like card-deck turn battle. LLM variance and tendency to reintroduce component shells with stub reducers remain.

---

## 2. Patch summary

| Item | Detail |
|------|--------|
| **File changed** | `src/ham/builder_llm_scaffold.py` |
| **Target** | `_SCAFFOLD_SYSTEM_PROMPT` Rules block (inherited by `_SCAFFOLD_SYSTEM_PROMPT_STRICT`) |
| **Additions** | Prefer smaller working loop; forbid no-op/stub core actions; require wired state transitions + feedback; meaningful reducer actions; end-to-end self-check; import/export consistency |
| **Lines added** | 6 Rules bullets (~8 lines) |

**Not changed:** routing, recipe YAML, registry YAML, API, frontend, Builder Studio, CI, v1 JSON, templates, generated app output in repo.

---

## 3. Method

| Setting | Value |
|---------|--------|
| **Prompts** | Same as [GENERATED_QUALITY_BASELINE_REVIEW.md](./GENERATED_QUALITY_BASELINE_REVIEW.md) |
| **Flag** | `HAM_BUILD_REGISTRY_V2_ENABLED=true` (v2); `false` (v1 comparison) |
| **API** | `generate_scaffold()` + `enrich_plan_metadata_with_registry_v2` |
| **Output** | `/tmp/ham-generated-quality-baseline-after/` |
| **Review** | Static source inspection (no npm install / preview boot) |
| **v1 comparison** | **Run** — memory-match and card-deck-turn-based prompts with flag off |
| **Card-deck v2** | **Rerun** (not reused from pre-patch `/tmp/ham-card-deck-generated-review/`) |

Artifacts: `/tmp/ham-generated-quality-baseline-after/all-results.json`

---

## 4. Before/after matrix

| Recipe | Before rating | After rating | Main before gap | Main after observation | Improved? | Safety drift? |
|--------|---------------|--------------|-----------------|------------------------|-----------|---------------|
| `game.memory-match` (v2) | Partially playable | Partially playable | No restart | Flip/match loop present; reducer misuse on flip-back (`shuffle` action); still no restart | **No** | no |
| `game.typing-speed-racer` (v2) | Shell only | **Partially playable** | Prompt not wired to input | `currentPrompt` initialized; input vs prompt comparison; timer → finish | **Yes** | no |
| `game.word-builder` (v2) | Partially playable | **Shell only** | Hints missing | `SUBMIT_WORD` reducer case is no-op; score never updates; hints stubbed | **No (regressed)** | no |
| `game.resource-management-sim` (v2) | Shell only | **Partially playable** | `ALLOCATE` no-op | `ALLOCATE` subtracts resources; `END_TURN` advances days + win/loss alert; food does not decay on tick | **Yes** | no |
| `game.card-deck-turn-based` (v2) | Shell only | **Shell only** | Stub reducer | `GameContext` reducer still returns unchanged state for `DRAW_CARD`/`PLAY_CARD`/`END_TURN`; piles in initial state but never populated | **No** | no |
| `game.memory-match` (v1) | Partially playable | Partially playable | Single-file; no resolve lock | Single-file flip/match/win comparable to pre-patch v1 | **No** | no |
| `game.card-deck-turn-based` (v1) | Partially playable | Partially playable | No discard/turn loop | Draw/play/damage + discard pile in single `App.tsx`; **still better than v2 after** | **No** | no |

**Routing:** All v2 after runs matched expected recipes. Context lengths unchanged (~10–11k v2, ~521 v1).

---

## 5. Per-recipe after observations

### `game.memory-match` (v2)

**Output:** 10 files — `/tmp/ham-generated-quality-baseline-after/game_memory-match_v2/`

**Improved:** Reducer-based state; shuffle on mount; move counter; victory dispatch.

**Still failed:** No restart; flip-back uses `shuffle` action incorrectly (resets moves/pairs risk); interaction lock weaker than pre-patch run.

**State mutation:** Yes (flip, match, increment moves).

**Win/loss/restart:** Win at 8 pairs; **no restart**.

**Stubs/no-ops:** No explicit reducer no-ops; logic bugs remain.

**Import/export:** No obvious mismatch.

---

### `game.typing-speed-racer` (v2)

**Output:** 11 files — `/tmp/ham-generated-quality-baseline-after/game_typing-speed-racer_v2/`

**Improved:** **Primary win for this patch trial** — prompt selected on mount; `handleInputChange` compares input to `currentPrompt`; timer expiry sets finished; WPM computed (simplified).

**Still failed:** Accuracy meter wiring approximate; no restart; WPM formula crude.

**State mutation:** Yes (input, mistakes, timer, finished).

**Win/loss/restart:** Results on finish; **no restart**.

**Stubs/no-ops:** None observed in core path.

---

### `game.word-builder` (v2)

**Output:** 12 files — `/tmp/ham-generated-quality-baseline-after/game_word-builder_v2/`

**Improved:** Component split; `USE_HINT` decrements hints; letter pool object in state.

**Still failed:** **`SUBMIT_WORD` returns `{ ...state }` unchanged** — pre-patch baseline had working inline submit/score/duplicate logic in `App.tsx`; after-patch run **regressed** to shell.

**State mutation:** Hints only; score/submit broken.

**Win/loss/restart:** None.

**Stubs/no-ops:** `SUBMIT_WORD` case is explicit no-op.

---

### `game.resource-management-sim` (v2)

**Output:** 11 files — `/tmp/ham-generated-quality-baseline-after/game_resource-management-sim_v2/`

**Improved:** `ALLOCATE` wired and mutates resources; `END_TURN` increments days; win/loss alert on day 10 or food ≤ 0.

**Still failed:** Food does not decrease each day; allocation subtracts without production loop; panels partially decorative.

**State mutation:** Yes (allocate, end turn).

**Win/loss/restart:** Win/loss via alert; **no restart**.

**Stubs/no-ops:** No primary no-op cases; survival loop still shallow.

---

### `game.card-deck-turn-based` (v2)

**Output:** 12 files — `/tmp/ham-generated-quality-baseline-after/game_card-deck-turn-based_v2/`

**Improved:** State shape includes `drawPile`, `discardPile`, `playerHp`, `enemyHp`; context provider pattern; named export/import consistent for `Game`.

**Still failed:** **Reducer actions unchanged from pre-patch** — all three cases return `state` with `// Logic` comments; hand stays empty; no draw/play UI; End Turn dispatches no-op.

**State mutation:** **No** meaningful gameplay mutation.

**Win/loss/restart:** HP fields never change; **no terminal state or restart**.

**Stubs/no-ops:** **Yes** — primary gameplay actions stubbed.

---

### `game.memory-match` (v1)

**Output:** 6 files — single-file `App.tsx` with flip/match/win.

**vs pre-patch v1:** Comparable partial playability. Patch did not clearly help or harm v1 path.

---

### `game.card-deck-turn-based` (v1)

**Output:** 6 files — card definitions, draw, play, damage, discard pile.

**vs pre-patch v1:** Comparable or slightly richer (typed cards, discard). **Still outperforms v2 after** on playability despite less context.

---

## 6. Cross-recipe conclusion

| Question | Answer |
|----------|--------|
| Did the patch reduce shell-only outputs? | **Partially** — 2 of 5 v2 recipes improved; 1 unchanged shell; 1 regression to shell |
| Did it improve state-heavy recipes? | **Inconsistent** — resource sim improved; card-deck unchanged; word-builder regressed |
| Did it introduce regressions? | **Yes** — word-builder lost working inline submit logic |
| Is scaffold hardening enough alone? | **No** — card-deck still stubbed; LLM can still ignore new rules |
| Recipe-specific minimum-loop refinements still needed? | **Yes** — especially card-deck, and guardrails against reducer shells |

**Note:** Single-run LLM variance applies; reruns may differ. This is manual review, not telemetry.

---

## 7. Recommendation

**Keep the patch and commit** — low cost, measurable wins on typing and resource sim, no routing/safety regression.

**Next moves (in order):**

1. **Add `STATEFUL_GAME_MINIMUM_LOOP_CHECKLIST.md`** — explicit acceptance criteria for state-heavy recipes (per proposal §7).
2. **Optional small prompt revision** — strengthen “assertions must match implemented code” and “remove SUBMIT_WORD/PLAY_CARD cases if not implemented.”
3. **Rerun baseline once more** after checklist doc (same matrix) to measure stability.
4. **Defer recipe YAML edits** until card-deck shows improvement across ≥2 reruns.
5. **Do not add CI/generated-output lint yet.**

---

## 8. Non-goals

- No generated app output committed
- No production telemetry claims
- No autonomous Hermes changes
- No recipe or routing changes from this review alone
- No reference checker implementation
- No Build Registry v2 default enablement

---

## 9. References

- [GENERATED_QUALITY_BASELINE_REVIEW.md](./GENERATED_QUALITY_BASELINE_REVIEW.md)
- [SCAFFOLD_PROMPT_PLAYABILITY_HARDENING_PROPOSAL.md](./SCAFFOLD_PROMPT_PLAYABILITY_HARDENING_PROPOSAL.md)
- [game.card-deck-turn-based.generated-review.md](./outcome-reports/game.card-deck-turn-based.generated-review.md)
- [OUTCOME_REPORT_INDEX.md](./outcome-reports/OUTCOME_REPORT_INDEX.md)
- [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md)

**Local artifacts:** `/tmp/ham-generated-quality-baseline-after/` (not in repo)
