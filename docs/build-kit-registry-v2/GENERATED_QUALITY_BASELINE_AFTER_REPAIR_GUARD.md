# Generated Quality Baseline After Repair Guard

> **Local/manual generated-output review · Not production telemetry · Single repair-guard trial**

**Review date:** 2026-05-26 (UTC)

Prior baselines:

- [GENERATED_QUALITY_BASELINE_REVIEW.md](./GENERATED_QUALITY_BASELINE_REVIEW.md) (original)
- [GENERATED_QUALITY_BASELINE_AFTER_SCAFFOLD_HARDENING.md](./GENERATED_QUALITY_BASELINE_AFTER_SCAFFOLD_HARDENING.md) (prompt-only)

---

## 1. Executive summary

**What changed:** Added a lightweight static **scaffold quality guard** (`src/ham/scaffold_quality.py`) that inspects generated files for obvious playability failures (no-op reducer actions, stub/TODO placeholders in core paths, import/export mismatches). When issues are detected, `generate_scaffold()` runs **one focused repair LLM pass** before returning output.

**Quality outcome:** **Improved overall** — all five v2 baseline prompts reached at least **Partially playable** on static review (memory-match reached **Playable** with restart). State-heavy **`game.card-deck-turn-based` v2** improved from **Shell only** to **Partially playable** (deck/hand/discard/effects/win logic in `App.tsx`).

**Routing and safety:** Unchanged and correct. All v2 samples routed to expected recipes with v2 context. **No safety drift** observed.

**Caveats:** LLM variance applies; inspector does not catch all wiring bugs (e.g. disconnected props without reducers). One repair pass is not a guarantee.

---

## 2. Implementation summary

| Component | Location | Role |
|-----------|----------|------|
| `ScaffoldQualityIssue` | `src/ham/scaffold_quality.py` | Issue record (code, message, path) |
| `inspect_generated_scaffold_quality()` | `src/ham/scaffold_quality.py` | Static inspection of `file_changes` |
| `build_scaffold_repair_prompt()` | `src/ham/scaffold_quality.py` | Targeted repair messages |
| `maybe_repair_generated_scaffold()` | `src/ham/scaffold_quality.py` | One repair LLM call when issues found |
| `_maybe_apply_quality_repair()` | `src/ham/builder_llm_scaffold.py` | Wired after successful JSON parse (attempt 1 or 2) |
| Unit tests | `tests/test_scaffold_quality.py` | Detector + repair prompt + integration (mocked LLM) |

**Prompt hardening preserved:** Existing `_SCAFFOLD_SYSTEM_PROMPT` playability Rules unchanged.

**Opt-out:** `HAM_SCAFFOLD_QUALITY_REPAIR=false` skips repair pass.

**Not changed:** routing, recipe/registry YAML, API, frontend, Builder Studio, CI, v1 JSON, templates.

---

## 3. Tests run

```bash
pytest tests/test_scaffold_quality.py -q
# 10 passed

pytest tests/test_builder_llm_scaffold_registry_manual_smoke.py \
  tests/test_build_registry.py tests/test_build_registry_intent.py \
  tests/test_build_registry_scaffold_context.py \
  tests/test_builder_llm_scaffold_registry_context.py -q
# 435 passed
```

---

## 4. Before / after / after-repair matrix

| Recipe | Original baseline | After prompt hardening | After repair guard | Main remaining gap | Improved? | Safety drift? |
|--------|-------------------|------------------------|--------------------|--------------------|-----------|-------------|
| `game.memory-match` (v2) | Partially playable | Partially playable | **Playable** | Flip-back edge cases | **Yes** | no |
| `game.typing-speed-racer` (v2) | Shell only | Partially playable | **Partially playable** | 60s timer uses elapsed counter not fixed 60s; finish WPM approximate | **Yes** | no |
| `game.word-builder` (v2) | Partially playable | Shell only (regressed) | **Partially playable** | Hints UI present but hint logic thin; submit via components | **Yes vs hardening** | no |
| `game.resource-management-sim` (v2) | Shell only | Partially playable | **Partially playable** | Survival loop shallow; production/gather simplified | **Yes** | no |
| `game.card-deck-turn-based` (v2) | Shell only | Shell only | **Partially playable** | Win check closure timing; enemy turn simplified | **Yes** | no |
| `game.memory-match` (v1) | Partially playable | Partially playable | **Partially playable** | Comparable single/multi-file loop | Stable | no |
| `game.card-deck-turn-based` (v1) | Partially playable | Partially playable | **Partially playable** | Draw/play/damage; repair guard also applies to v1 path | Stable | no |

**Routing:** All v2 after-repair runs matched expected recipes. v2 context ~10–11k chars; v1 ~521 chars.

---

## 5. Per-recipe after observations

### `game.memory-match` (v2)

**Output:** `/tmp/ham-generated-quality-baseline-repaired/game_memory-match_v2/` (9 files)

**Improved:** Reducer with meaningful cases; flip/match/move increment; **restart via `RESET_GAME`** and `VictoryScreen onReset`.

**Still failed:** Flip-back timing relies on `SET_CARDS` payload patterns; not preview-boot verified.

**State mutation:** Yes. **Win/restart:** Yes. **Stubs:** None detected post-repair.

---

### `game.typing-speed-racer` (v2)

**Output:** `/tmp/ham-generated-quality-baseline-repaired/game_typing-speed-racer_v2/` (11 files)

**Improved:** Prompt index wired to input; mistake counting; finish flow and results panel.

**Still failed:** Timer is elapsed-seconds not explicit 60s countdown; repair guard did not run (no reducer stubs detected).

**State mutation:** Yes. **Result state:** `isFinished` + results panel. **Stubs:** None.

---

### `game.word-builder` (v2)

**Output:** `/tmp/ham-generated-quality-baseline-repaired/game_word-builder_v2/` (11 files)

**Improved:** Recovered from prompt-hardening regression — inline submit/score/duplicate logic in `App.tsx` (no stub reducer).

**Still failed:** Hint decrement not fully wired; `gameOver` never toggled.

**State mutation:** Yes (submit/score). **Stubs:** None post-repair.

---

### `game.resource-management-sim` (v2)

**Output:** `/tmp/ham-generated-quality-baseline-repaired/game_resource-management-sim_v2/` (11 files)

**Improved:** Resource gather/day advance/win/loss assertions align with mutating handlers (inspector clean).

**Still failed:** Full worker assignment / food decay loop still simplified.

**State mutation:** Yes. **Stubs:** None detected.

---

### `game.card-deck-turn-based` (v2)

**Output:** `/tmp/ham-generated-quality-baseline-repaired/game_card-deck-turn-based_v2/` (12 files)

**Improved:** **Major gain** — `App.tsx` implements shuffled deck, hand/discard zones, `playCard`, effect resolution, HP updates, result panel (vs stub reducer before).

**Still failed:** `checkWinCondition` reads stale `enemyHp` closure; turn/enemy logic minimal; no dedicated reducer file.

**State mutation:** Yes. **Win/loss:** Present. **Stubs:** None detected post-repair.

---

### v1 comparison rows

Both v1 samples remained **partially playable**. Repair guard runs on v1 scaffolds too but did not require repair when output was already clean.

---

## 6. Cross-recipe conclusion

| Question | Answer |
|----------|--------|
| Did the repair guard reduce shell-only outputs? | **Yes** — card-deck v2 moved off shell-only; word-builder recovered from hardening regression |
| Did it improve state-heavy recipes? | **Yes** — card-deck and resource sim; typing/word-builder benefit from combined prompt + variance |
| Did it introduce regressions? | **Not observed** in this rerun (LLM variance still applies) |
| Is scaffold hardening alone enough? | **No** — card-deck stayed shell-only after prompt-only patch until repair guard |
| Recipe-specific minimum-loop refinements still needed? | **Optional** — for consistent card-deck/sim depth, not blocking keeping repair guard |

**Inspector gap:** Wiring bugs without reducers (e.g. broken prompt/input) may skip repair; future checklist/heuristics could add non-reducer checks.

---

## 7. Recommendation

**Keep the repair guard and commit** (prompt hardening + quality module + tests + this review).

**Next:**

1. Add `STATEFUL_GAME_MINIMUM_LOOP_CHECKLIST.md` for manual/generated reviews.
2. Optionally extend inspector for **non-reducer** wiring failures (prompt state not passed to input handlers).
3. Rerun baseline once more after a major model change — do not treat one rerun as telemetry.
4. **Defer** recipe YAML edits until card-deck shows stable partial playability across multiple reruns.

---

## 8. Non-goals

- No generated app output committed
- No production telemetry claims
- No autonomous Hermes changes
- No recipe/routing/registry changes from this review alone
- No CI enforcement of generated quality
- No reference checker implementation

---

## 9. References

- [GENERATED_QUALITY_BASELINE_REVIEW.md](./GENERATED_QUALITY_BASELINE_REVIEW.md)
- [GENERATED_QUALITY_BASELINE_AFTER_SCAFFOLD_HARDENING.md](./GENERATED_QUALITY_BASELINE_AFTER_SCAFFOLD_HARDENING.md)
- [SCAFFOLD_PROMPT_PLAYABILITY_HARDENING_PROPOSAL.md](./SCAFFOLD_PROMPT_PLAYABILITY_HARDENING_PROPOSAL.md)
- [game.card-deck-turn-based.generated-review.md](./outcome-reports/game.card-deck-turn-based.generated-review.md)
- [OUTCOME_REPORT_INDEX.md](./outcome-reports/OUTCOME_REPORT_INDEX.md)
- [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md)

**Local artifacts:** `/tmp/ham-generated-quality-baseline-repaired/all-results.json`
