# Scaffold Prompt Playability Hardening Proposal

> **Design/proposal only · Not implemented · Not production telemetry · No runtime changes authorized by this document**

**Proposal date:** 2026-05-26 (UTC)

Related evidence: [GENERATED_QUALITY_BASELINE_REVIEW.md](./GENERATED_QUALITY_BASELINE_REVIEW.md)

---

## 1. Executive summary

The [generated quality baseline](./GENERATED_QUALITY_BASELINE_REVIEW.md) shows a **broader scaffold/playability gap**, not a card-deck-only issue.

**What is working:**

- Build Registry v2 **routing** and **context selection** behind `HAM_BUILD_REGISTRY_V2_ENABLED`
- **Safety posture** — no gambling, marketplace, backend, or telemetry drift in sampled outputs
- **Simpler recipes** can reach partially playable scaffolds (memory match, word builder)

**What is failing:**

- **State-heavy recipes** often produce **component shells** with missing, stubbed, or disconnected logic
- The scaffold LLM frequently lists **behavioral assertions** that describe desired gameplay but are **not implemented in code**

The next improvement should **harden scaffold instructions** so generated apps implement **minimally playable loops**, not just file/component architecture.

**This proposal does not implement** code, tests, CI, routing, recipe YAML, or registry changes. It defines goals, draft prompt language, checklists, and a recommended first implementation path for a future, minimal patch to `_SCAFFOLD_SYSTEM_PROMPT` in `src/ham/builder_llm_scaffold.py`.

---

## 2. Evidence from baseline

Summary from [GENERATED_QUALITY_BASELINE_REVIEW.md](./GENERATED_QUALITY_BASELINE_REVIEW.md) (local/manual review, 2026-05-26):

| Recipe | Context | Quality | Key observation |
|--------|---------|---------|-----------------|
| `game.memory-match` | v2 | **Partially playable** | Flip/match/lock/victory loop works; **no restart** |
| `game.typing-speed-racer` | v2 | **Shell only** | Timer ticks; **prompt not wired to input**; WPM/accuracy broken |
| `game.word-builder` | v2 | **Partially playable** | Submit/score/duplicate handling works; **hints missing** |
| `game.resource-management-sim` | v2 | **Shell only** | **`ALLOCATE` no-op**; panels unwired; no survival/food loop |
| `game.card-deck-turn-based` | v2 | **Shell only** | **Stub reducer**; no draw/discard/effects/enemy turn/win state |
| `game.memory-match` | v1 | **Partially playable** | Single-file loop comparable to v2 |
| `game.card-deck-turn-based` | v1 | **Partially playable** | Minimal draw/play/damage — **better than v2** for same prompt |

**Cross-cutting signals:**

- All v2 baseline prompts **routed correctly** with v2 playbook context (~10–11k chars).
- **No safety drift** in any sample.
- **Implementation depth inversely correlates with mechanic count** unless the loop is simple.
- Current tests (`test_build_registry_intent.py`, `test_builder_llm_scaffold_registry_manual_smoke.py`) validate **routing and context injection**, not generated app playability.

---

## 3. Diagnosis

| Hypothesis | Assessment |
|------------|------------|
| Primary issue is routing | **Unlikely** — all v2 samples routed to expected recipes |
| Primary issue is safety drift | **Unlikely** — no excluded domains observed |
| Primary issue is scaffold completeness | **Likely** — structure without runnable core loops |
| v2 playbook encourages architecture over behavior | **Plausible** — richer component trees correlate with hollow reducers on hard recipes |
| State-heavy recipes vulnerable to no-op reducers | **Confirmed** — card-deck (`PLAY_CARD`/`END_TURN` stubs), resource sim (`ALLOCATE` pass-through) |
| v1 vs v2 on card-deck | **v1 outperformed v2 on playability** despite ~20× less context — suggests prompt/stack behavior matters more than context volume alone |

**Current scaffold system prompt** (`_SCAFFOLD_SYSTEM_PROMPT` in `src/ham/builder_llm_scaffold.py`) asks for “real, runnable code” and “ALL the initial source files” but does **not** explicitly forbid placeholder gameplay, no-op reducer cases, or disconnected UI controls. The retry prompt (`_SCAFFOLD_SYSTEM_PROMPT_STRICT`) only tightens JSON formatting.

**Context assembly** (`resolve_scaffold_context` in `src/ham/build_registry/scaffold_context.py`) injects v1 Builder Kit or v2 playbook guidance into the **user message**; neither layer currently enforces a **minimum playable loop** acceptance gate on LLM output.

---

## 4. Hardening goals

Future scaffold prompting (and optional follow-on checks) should aim for:

1. **Minimally playable requested loop** — the user can complete the core interaction path without TODOs or stubs.
2. **Meaningful state mutation** — primary user actions change game/app state in observable ways.
3. **No placeholder core actions** — reducer/action handlers must not be no-ops or comment-only placeholders.
4. **Reducer discipline** — if a reducer is used, every declared action either mutates state meaningfully or is removed; no pass-through `return { ...state }` for primary gameplay actions.
5. **Wired UI controls** — buttons, inputs, and clickable elements dispatch to handlers that update state.
6. **Terminal states when relevant** — win/loss/result screens or flags when the plan/recipe implies them.
7. **Restart/new round when relevant** — reset flow after terminal state for game recipes that expect replay.
8. **Import/export consistency** — default exports match import sites (named vs default).
9. **Local-only by default** — no backend, fetch, or external services unless the plan explicitly requests them.
10. **Honest assertions** — behavioral assertions in scaffold JSON must reflect implemented behavior, not aspirational behavior.

---

## 5. Proposed scaffold prompt additions

Draft language for a **future** patch to `_SCAFFOLD_SYSTEM_PROMPT` (not applied by this proposal):

### Playability (core)

> Do not produce placeholder or no-op core gameplay actions. For every primary interaction described in the plan, implement the state transition, UI wiring, and feedback needed for a minimally playable version.

> Before finalizing files, self-check that the generated app can be used end-to-end for the requested loop without requiring TODOs, stubs, or future implementation.

> If using reducers or action dispatch, every declared action must either mutate state in a meaningful way or be removed. Do not leave primary actions as pass-through returns.

> Prefer a smaller fully working loop over a larger component shell.

### Wiring and feedback

> Every visible control (button, card, input, slider) shown in the UI must be connected to state logic. Do not render controls whose handlers are empty or unimplemented.

> After primary actions, update user-visible feedback (score, log line, HP, timer, message) so the user can tell the action succeeded.

### Assertions honesty

> List 1–5 assertions that describe behavior actually implemented in the generated files. Do not assert gameplay that remains stubbed or TODO.

### Imports and local-only

> Ensure import/export styles match (default export ↔ default import). Self-check for named/default mismatches before output.

> Keep the app local-only (React state, no fetch/API) unless the plan explicitly requires network access.

### Size tradeoff (guardrail)

> If file or complexity limits conflict with playability, reduce file count and component split — but keep the core loop complete.

These additions should stay **concise** (target: +8–12 lines in the Rules block) to avoid prompt bloat.

---

## 6. Minimum playable loop checklist

Generic checklist for **manual generated reviews** and future optional lint/self-check prompts:

| # | Check | Pass criterion |
|---|--------|----------------|
| 1 | **Initial state valid** | State initializes with data needed to start (non-empty hand/deck/grid/prompt where applicable) |
| 2 | **Primary controls wired** | Main buttons/inputs/cards call handlers that exist and run |
| 3 | **Core actions mutate state** | Primary actions change scores, piles, timers, HP, matched flags, etc. |
| 4 | **User feedback** | Action causes visible update (log, counter, animation class, message) |
| 5 | **Result state** | Win/loss/complete/finished state exists when prompt implies it |
| 6 | **Restart/new round** | Reset path exists when recipe/game type expects replay |
| 7 | **No core stubs** | No `// Logic`, `TODO`, or no-op reducer cases for primary gameplay |
| 8 | **Import/export consistency** | No obvious named/default import mismatches |
| 9 | **Local-only default** | No fetch/axios/backend unless requested |
| 10 | **Assertions match code** | Listed assertions are verifiable from generated source |

**Rating guide** (aligned with baseline):

- **Playable** — passes 1–4 and 5 where relevant; minor polish gaps only
- **Partially playable** — core loop mostly works; missing restart, hints, or edge cases
- **Shell only** — structure present; core loop broken or stubbed
- **Failed generation** — LLM/scaffold error; no usable files

---

## 7. State-heavy recipe checklist

Extra checks beyond §6 for recipes with timers, reducers, multi-phase loops, or pile semantics:

| Area | Extra checks |
|------|----------------|
| **Timers** | Timer state drives phase transitions; input locks when finished; results computed from elapsed/typed data |
| **Reducers** | Every action type in `switch`/`case` updates relevant slice; no primary no-op cases |
| **Turn loops** | Phase indicator; player vs opponent/enemy phases; actions blocked on wrong phase |
| **Resource loops** | Allocation changes resource counts; consumption/production runs on tick/day advance |
| **Validation/submission** | Input compared to rules/dictionary; duplicates rejected; score updates on valid submit |
| **Draw/discard/hand** | Piles in state; shuffle/draw/play/discard transitions preserve conservation |
| **Win/loss** | Terminal check on HP/score/day/pairs; UI blocks further play after terminal |
| **Invalid state recovery** | Empty deck reshuffle or graceful message; no negative counts; no stuck phases |

Applies especially to: `game.card-deck-turn-based`, `game.resource-management-sim`, `game.typing-speed-racer`, and future state-heavy app types.

---

## 8. Implementation options for later

| Option | Description | Effort | When |
|--------|-------------|--------|------|
| **A. Scaffold prompt patch only** | Add §5 language to `_SCAFFOLD_SYSTEM_PROMPT` (+ optional mirror in strict retry) | Small | **Recommended first** |
| **B. Self-check block in prompt** | Ask LLM to mentally verify checklist before JSON output | Small | Pair with A |
| **C. v2 “minimum playable behavior” section** | Render short acceptance block from registry compose into playbook context | Medium | After A/B trial if recipe-specific gaps remain |
| **D. Manual generated review method** | Document operator baseline reruns under `/tmp/` (`GENERATED_REVIEW_METHOD.md`) | Small | Parallel to A |
| **E. Lightweight generated-output lint** | Post-parse static heuristics (no-op reducer regex, empty handler detection) | Medium | **Only after** A/B + second baseline show persistent gaps |
| **F. CI / automated validation** | Block merges on generated quality | Large | **Deferred** — insufficient evidence and flaky LLM variance |

Options C and E touch registry render or scaffold parse paths; keep them **out of scope** until prompt-only hardening is measured.

---

## 9. Recommended first implementation

**Start with the smallest scaffold prompt hardening patch (Options A + B).**

| Do | Don't (yet) |
|----|-------------|
| Add §5 draft rules to `_SCAFFOLD_SYSTEM_PROMPT` | Edit recipe YAML |
| Keep addition under ~12 lines in Rules block | Add CI or automated generated-app validation |
| Apply same rules to v1 and v2 paths (system prompt is shared) | Enable Build Registry v2 by default |
| Rerun the [baseline matrix](./GENERATED_QUALITY_BASELINE_REVIEW.md) sample prompts | Treat one rerun as production telemetry |
| Compare before/after quality ratings in a new generated review doc | Implement registry reference checker for output quality |

**Success criteria for first patch trial:**

- `game.card-deck-turn-based` v2 improves from **Shell only** toward **Partially playable** (piles + at least one effect + HP change)
- `game.resource-management-sim` v2 `ALLOCATE` mutates resources or is removed
- `game.typing-speed-racer` v2 wires displayed prompt to input validation
- No regression: `game.memory-match` v2 stays **Partially playable** or better
- v1 card-deck does not regress below current partial playability

---

## 10. Risks

| Risk | Mitigation |
|------|------------|
| **Overconstraining creative outputs** | “Minimally playable” not “feature-complete”; allow smaller file counts |
| **Prompt length growth** | Cap additions; monitor total system prompt size |
| **LLM claims completeness without implementing** | Assertions honesty rule; manual baseline reruns; defer automated lint |
| **v1/default scaffold regression** | Shared system prompt — rerun v1 comparison samples in baseline |
| **Monolithic files if “fully working” overemphasized** | Explicit “prefer smaller working loop over large shell” |
| **Mistaking manual baseline for telemetry** | Label reruns as local/manual; no production claims |
| **False confidence from one model/run** | Same model family + multiple recipes before recipe YAML changes |

---

## 11. Non-goals

This proposal does **not** authorize or include:

- Implementation in this document
- Recipe YAML or registry pack edits
- Routing or intent changes
- New tests or CI steps
- Generated app output committed to the repo
- Production telemetry claims
- Autonomous Hermes recipe mutation
- Build Registry v2 default enablement
- Reference checker implementation for generated-output quality
- Builder Studio or frontend changes

---

## 12. Recommended next steps

1. ~~Commit the baseline review~~ — done (`84feac88` on `main`).
2. **Create this proposal** — current task.
3. **If approved:** implement the smallest `_SCAFFOLD_SYSTEM_PROMPT` hardening patch (§5).
4. **Rerun the same baseline matrix** (prompts and recipes in [GENERATED_QUALITY_BASELINE_REVIEW.md](./GENERATED_QUALITY_BASELINE_REVIEW.md)); store output under `/tmp/`.
5. **Document before/after** in a short follow-up generated review or baseline delta note.
6. **Only then** consider recipe-specific refinements (`CARD_DECK_RECIPE_REFINEMENT_PROPOSAL.md`) or a standalone [STATEFUL_GAME_MINIMUM_LOOP_CHECKLIST.md](./STATEFUL_GAME_MINIMUM_LOOP_CHECKLIST.md) if prompt-only hardening is insufficient.

---

## 13. References

- [GENERATED_QUALITY_BASELINE_REVIEW.md](./GENERATED_QUALITY_BASELINE_REVIEW.md)
- [game.card-deck-turn-based.generated-review.md](./outcome-reports/game.card-deck-turn-based.generated-review.md)
- [OUTCOME_REPORT_INDEX.md](./outcome-reports/OUTCOME_REPORT_INDEX.md)
- [WAVE_3_CARD_DECK_CHECKPOINT.md](./WAVE_3_CARD_DECK_CHECKPOINT.md)
- [REGISTRY_REFERENCE_CHECKER_PROPOSAL.md](./REGISTRY_REFERENCE_CHECKER_PROPOSAL.md)
- [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md)
- [ADR-0018: Build Kit Evolution Loop with Hermes](../adr/0018-build-kit-evolution-loop-with-hermes.md)

**Implementation touchpoints (for future work only):**

- `src/ham/builder_llm_scaffold.py` — `_SCAFFOLD_SYSTEM_PROMPT`, `_SCAFFOLD_SYSTEM_PROMPT_STRICT`
- `src/ham/build_registry/scaffold_context.py` — `resolve_scaffold_context` (optional §8 option C)
- `tests/test_builder_llm_scaffold_registry_manual_smoke.py` — message smoke (unchanged by prompt-only patch unless assertions added later)
