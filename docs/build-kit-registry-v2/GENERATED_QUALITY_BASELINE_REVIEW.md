# Build Registry v2 Generated Quality Baseline Review

> **Local/manual generated-output review · Not production telemetry · Not automated validator output · No runtime changes**

**Review date:** 2026-05-26 (UTC)

---

## 1. Executive summary

This review checks whether generated-output quality issues are **isolated to `game.card-deck-turn-based`** or **broader across Build Registry v2 recipes**.

**Finding:** The card-deck failure is **not unique**, but it is **worst among state-heavy recipes**. Simpler interaction loops (memory match, word builder) can produce **partially playable** scaffolds behind v2 routing. Complex multi-zone / multi-phase recipes (card-deck turn battle, resource sim) tend toward **component shells with stubbed or hollow reducers** — even when routing and v2 playbook injection succeed.

**v1 comparison:** For the same card-deck prompt, **v1 generic scaffold produced a more functional minimal loop** than v2 (draw → play → damage), while v2 produced a richer file layout with **no-op reducer actions**. Shell-only / hollow-logic behavior is **not v2-specific** — resource sim and typing also fail core loops under v2 — but v2 context may **encourage structure over runnable state** for hard recipes.

This is local/manual generated-output review, not telemetry. No runtime, scaffold, routing, recipe, or test changes were made. The goal is to decide whether the next fix should be **recipe-specific**, **scaffold-level**, or **broader builder-quality hardening**.

**Recommendation:** **Scaffold prompt hardening first**, paired with a **minimum playable loop checklist** for state-heavy recipes — not card-deck recipe YAML edits alone.

---

## 2. Method

### Generation path

Used the repo’s established public scaffold APIs (same path as [game.card-deck-turn-based.generated-review.md](./outcome-reports/game.card-deck-turn-based.generated-review.md)):

| API / module | Role |
|--------------|------|
| `select_registry_v2_app_type_for_prompt` | Intent routing |
| `enrich_plan_metadata_with_registry_v2` | Plan metadata enrichment |
| `resolve_scaffold_context` | v1/v2 context resolution |
| `_build_scaffold_messages` | Scaffold message assembly |
| `generate_scaffold()` in `src/ham/builder_llm_scaffold.py` | One-shot LLM scaffold (BYO OpenRouter) |

Reference harnesses inspected (not run as tests): `tests/test_builder_llm_scaffold_registry_manual_smoke.py`, `tests/test_build_registry_intent.py`.

No new committed generator script was added. A **single operator Python invocation** ran all attempts sequentially.

### Environment

| Setting | Value |
|---------|--------|
| **Feature flag (v2 runs)** | `HAM_BUILD_REGISTRY_V2_ENABLED=true` |
| **Feature flag (v1 comparison)** | `HAM_BUILD_REGISTRY_V2_ENABLED=false` |
| **OpenRouter key** | Repo-root `.env` (established local path) |
| **Output root** | `/tmp/ham-generated-quality-baseline/<recipe-id>_<v1\|v2>/` |
| **Card-deck v2** | Reused prior run at `/tmp/ham-card-deck-generated-review/` (not rerun) |

### v1 comparison

**Run:** Same prompts for `game.memory-match` and `game.card-deck-turn-based` with flag off.

### Review method

- Static source inspection of generated files (no `npm install` / preview boot in this pass).
- Heuristic signals (reducer stubs, state mutation, win/loss, timer/input) plus manual read of `App.tsx` and core logic files.
- Generated app output **not committed**.

---

## 3. Review matrix

| Recipe | Prompt type | Expected route | Observed route | v2 context | Render chars | Output status | Quality rating | Main gap | Safety drift? |
|--------|-------------|----------------|----------------|------------|--------------|---------------|----------------|----------|---------------|
| `game.memory-match` | v2 baseline | `game.memory-match` | `game.memory-match` | yes | 9,988 | 10 files | **Partially playable** | No restart; flip-resolve lock timing fragile | no |
| `game.typing-speed-racer` | v2 baseline | `game.typing-speed-racer` | `game.typing-speed-racer` | yes | 10,416 | 11 files | **Shell only** | Prompt not wired to input; WPM/accuracy calc broken | no |
| `game.word-builder` | v2 baseline | `game.word-builder` | `game.word-builder` | yes | 11,232 | 6 files | **Partially playable** | Hints missing; letters not returned after submit | no |
| `game.resource-management-sim` | v2 baseline | `game.resource-management-sim` | `game.resource-management-sim` | yes | 10,948 | 11 files | **Shell only** | `ALLOCATE` no-op; no food consumption; win = day count only | no |
| `game.card-deck-turn-based` | v2 (prior review) | `game.card-deck-turn-based` | `game.card-deck-turn-based` | yes | 10,793 | 13 files | **Shell only** | Stub reducer; no piles/effects/turns/victory | no |
| `game.memory-match` | v1 comparison | (none) | (none) | no (v1 generic) | 521 | 6 files | **Partially playable** | Single-file; no interaction lock during resolve | no |
| `game.card-deck-turn-based` | v1 comparison | (none) | (none) | no (v1 generic) | 521 | 6 files | **Partially playable** | Minimal draw/play/damage; no discard/turn loop | no |

**Routing:** All v2 baseline prompts routed to expected recipes. All v2 runs used v2 playbook context with no v1 fallback. v1 runs used generic Builder Kit context (~521 chars).

---

## 4. Per-recipe observations

### `game.memory-match` (v2)

**Output:** `/tmp/ham-generated-quality-baseline/game_memory-match_v2/` — Vite+React, 10 files (`CardGrid`, `MemoryCard`, `MoveCounter`, `VictoryScreen`).

**What worked:**
- Shuffled deck, two-card flip, match lock, move counter, victory when all matched.
- Interaction lock during resolve (`interactionLocked` + timeout).
- Routing and v2 context correct.

**What failed:**
- No restart / new game after victory.
- Static review only — import/build not verified.

**Playable?** **Partially** — core memory loop implemented in `App.tsx` state.

**Reducer/actions:** `useState` + `useEffect` (no reducer); actions **meaningful**.

**Win/loss/restart:** Win via `VictoryScreen`; **no restart**.

**Safety drift:** None.

---

### `game.typing-speed-racer` (v2)

**Output:** `/tmp/ham-generated-quality-baseline/game_typing-speed-racer_v2/` — 11 files (timer, WPM, accuracy, input, results components).

**What worked:**
- 60s countdown timer; results panel scaffold; component decomposition matches recipe UI contracts.
- Routing and v2 context correct.

**What failed:**
- `TypingPrompt` displays a random prompt, but `currentPrompt` in `App` stays `''` — mistake detection compares against empty string.
- WPM calculation uses `(60 - timer)` at expiry (degenerate divisor); accuracy logic incomplete.
- Input not locked meaningfully during/after timer in practice.

**Playable?** **Shell only** — timer ticks but typing feedback loop is non-functional.

**Reducer/actions:** `useState` only; timer action works; **input validation path broken**.

**Win/loss/restart:** `isFinished` result state; **no restart**.

**Safety drift:** None.

---

### `game.word-builder` (v2)

**Output:** `/tmp/ham-generated-quality-baseline/game_word-builder_v2/` — 6 files, logic concentrated in `App.tsx`.

**What worked:**
- Letter pool selection, word submission, static dictionary check, duplicate rejection, length-based scoring.
- Routing and v2 context correct.

**What failed:**
- **Hints** not implemented (prompt requested limited hints).
- Letters removed on click but not returned after failed submit or word clear.
- Small static word list only.

**Playable?** **Partially** — submit/score/duplicate loop works for happy path.

**Reducer/actions:** Inline handlers; **meaningful** for submit/score.

**Win/loss/restart:** Score only; **no terminal state or restart**.

**Safety drift:** None.

---

### `game.resource-management-sim` (v2)

**Output:** `/tmp/ham-generated-quality-baseline/game_resource-management-sim_v2/` — 11 files with dashboard/allocation/upgrade panels.

**What worked:**
- Resource dashboard scaffold; `useReducer` skeleton; day counter; win trigger at day 10.
- Routing and v2 context correct.

**What failed:**
- `ALLOCATE` case returns `{ ...state }` unchanged — **no-op**.
- `AllocationControl`, `ProductionPanel`, `UpgradePanel` are **display shells** (no dispatch wiring).
- No food consumption, worker assignment, or storage upgrade logic — win fires after 10 `NEXT_DAY` ticks regardless of food.

**Playable?** **Shell only** — sim loop is not meaningful.

**Reducer/actions:** Reducer present; **mostly stubbed** except day increment.

**Win/loss/restart:** `goal`/`failure` flags possible; **no restart**; failure path unused.

**Safety drift:** None.

---

### `game.card-deck-turn-based` (v2, prior review)

**Output:** `/tmp/ham-card-deck-generated-review/` — 13 files (see [generated review](./outcome-reports/game.card-deck-turn-based.generated-review.md)).

**What worked:**
- Routing; v2 playbook injection; component layout (hand, opponent, action bar, event log); `useReducer` pattern chosen.

**What failed:**
- `PLAY_CARD` / `END_TURN` are comment placeholders returning `{ ...state }`.
- No draw/discard piles, card catalog, effects, enemy turn, victory, or restart.
- Likely import mismatch (`App.tsx` named import vs default export).

**Playable?** **Shell only**.

**Reducer/actions:** **Stubbed / no-op**.

**Win/loss/restart:** **Absent**.

**Safety drift:** None.

---

### `game.memory-match` (v1 comparison)

**Output:** `/tmp/ham-generated-quality-baseline/game_memory-match_v1/` — 6 files, single-file game in `App.tsx`.

**What worked:**
- Flip-two, match, unflip on mismatch, move count, win banner when all matched.

**What failed:**
- No explicit interaction lock (third flip possible during resolve).
- Fewer files than v2; no dedicated victory component.

**Playable?** **Partially** — comparable core loop to v2, less structure.

**Safety drift:** None.

---

### `game.card-deck-turn-based` (v1 comparison)

**Output:** `/tmp/ham-generated-quality-baseline/game_card-deck-turn-based_v1/` — 6 files, single-file `App.tsx`.

**What worked:**
- Draw button populates hand; play card reduces enemy HP; local-only DOM.

**What failed:**
- No discard pile, turn loop, card effects, or victory terminal state.
- `initialDeck.sort()` mutates deck each draw; generic card names only.

**Playable?** **Partially** — **more functional than v2** for the same prompt despite minimal structure.

**Safety drift:** None.

---

## 5. Cross-recipe findings

| Question | Answer |
|----------|--------|
| Are multiple recipes producing shell-only apps? | **Yes** — typing-speed-racer, resource-management-sim, and card-deck-turn-based (v2). |
| Are simple recipes playable while complex recipes fail? | **Mostly yes** — memory-match and word-builder reached partial playability; multi-mechanic sims/card battle did not. |
| Are reducers/actions often stubbed? | **Yes, on state-heavy recipes** — explicit no-op reducer cases in card-deck (v2) and resource sim (v2). |
| Are components present but logic missing? | **Yes** — typing and resource sim split UI across components without wiring core behavior. |
| Does v1 show the same issue if tested? | **Mixed** — v1 card-deck was **more playable** than v2; v1 memory similar to v2. Hollow shells are **general builder behavior**, but v2 may amplify structure-without-logic for hard recipes. |
| Recipe-specific or scaffold-level? | **Scaffold-level first** — routing/context tests pass; quality gap is in LLM output honoring playability, especially for multi-step state machines. |

**Pattern:** The scaffold LLM often delivers **credible file/component structure** and **assertions that describe desired behavior**, but **implementation depth correlates inversely with mechanic count** unless the loop is simple (flip pairs, submit word).

---

## 6. Root-cause hypotheses

1. **General scaffold prompt may reward component/file structure over runnable gameplay** — more files ≠ playable loop.
2. **Recipe context is advisory** — v2 playbooks describe mechanics but do not enforce minimum runnable state transitions in output.
3. **State-heavy recipes need explicit “minimum playable loop” acceptance criteria** in scaffold system prompt or post-parse checks.
4. **LLM creates reducers/actions but leaves them no-op** unless explicitly forbidden — seen in card-deck and resource sim `ALLOCATE` / `PLAY_CARD`.
5. **Current tests validate routing/context, not generated app quality** — `test_build_registry_intent.py` e2e stops at message content.
6. **v2 comparison suggests context volume ≠ implementation quality** — v2 card-deck (10.8k chars context) underperformed v1 generic (521 chars) on playability for the same prompt.
7. **Assertions can hallucinate completeness** — LLM lists behavioral assertions even when code is stubbed.

---

## 7. Recommendation

**Scaffold prompt hardening first**, plus a **minimum playable loop checklist for state-heavy recipes**.

Evidence does **not** support card-deck-only recipe YAML edits as the first fix. Routing works; simpler v2 recipes can partially play; v1 is not uniformly better; the common failure mode is **scaffold output stopping at UI architecture**.

Secondary: **More generated reviews needed** for the remaining six unrouted-in-baseline recipes before broad registry changes.

**Not recommended yet:** Routing adjustment; enabling v2 by default; recipe-specific YAML edits without scaffold hardening trial.

---

## 8. Suggested next artifacts

| Artifact | When |
|----------|------|
| [SCAFFOLD_PROMPT_PLAYABILITY_HARDENING_PROPOSAL.md](./SCAFFOLD_PROMPT_PLAYABILITY_HARDENING_PROPOSAL.md) | **First** — forbid empty reducer cases; require initial playable state |
| [STATEFUL_GAME_MINIMUM_LOOP_CHECKLIST.md](./STATEFUL_GAME_MINIMUM_LOOP_CHECKLIST.md) | **First** — per-recipe-type acceptance criteria (piles, turns, timer wiring) |
| [GENERATED_REVIEW_METHOD.md](./GENERATED_REVIEW_METHOD.md) | Standardize operator baseline runs under `/tmp/` |
| [CARD_DECK_RECIPE_REFINEMENT_PROPOSAL.md](./CARD_DECK_RECIPE_REFINEMENT_PROPOSAL.md) | **After** scaffold hardening trial — only if card-deck still uniquely fails |

---

## 9. Non-goals

- No recipe YAML edits
- No routing edits
- No scaffold code edits (this review)
- No tests added
- No CI changes
- No generated app output committed
- No production telemetry claims
- No autonomous Hermes changes
- No Build Registry v2 default enablement
- No reference checker implementation

---

## 10. References

- [game.card-deck-turn-based.generated-review.md](./outcome-reports/game.card-deck-turn-based.generated-review.md)
- [game.card-deck-turn-based.manual-outcome.md](./outcome-reports/game.card-deck-turn-based.manual-outcome.md)
- [game.resource-management-sim.manual-outcome.md](./outcome-reports/game.resource-management-sim.manual-outcome.md)
- [game.typing-speed-racer.manual-outcome.md](./outcome-reports/game.typing-speed-racer.manual-outcome.md)
- [game.word-builder.manual-outcome.md](./outcome-reports/game.word-builder.manual-outcome.md)
- [OUTCOME_REPORT_INDEX.md](./outcome-reports/OUTCOME_REPORT_INDEX.md)
- [WAVE_3_CARD_DECK_CHECKPOINT.md](./WAVE_3_CARD_DECK_CHECKPOINT.md)
- [REGISTRY_REFERENCE_CHECKER_PROPOSAL.md](./REGISTRY_REFERENCE_CHECKER_PROPOSAL.md)
- [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md)
- [ADR-0018: Build Kit Evolution Loop with Hermes](../adr/0018-build-kit-evolution-loop-with-hermes.md)

**Local artifacts (not in repo):**

- `/tmp/ham-generated-quality-baseline/all-results.json`
- `/tmp/ham-generated-quality-baseline/game_*_{v1,v2}/`
- `/tmp/ham-card-deck-generated-review/` (card-deck v2 prior run)
