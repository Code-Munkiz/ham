# Generated Quality Final Gap Pass Review

> **Local/manual generated-output review · Not production telemetry · Final gap hardening trial**

**Review date:** 2026-05-26 (UTC)

Prior baseline: [GENERATED_QUALITY_REPAIR_GUARD_V2_REVIEW.md](./GENERATED_QUALITY_REPAIR_GUARD_V2_REVIEW.md)

---

## 1. What changed

Extended `src/ham/scaffold_quality.py` for the remaining acceptance gaps:

| Change | Detail |
|--------|--------|
| **Timer enforcement (project-level)** | Detects 60-second prompts; flags timer code lacking explicit `60` / `60000` / countdown comparison (e.g. `elapsedSeconds < 60`); accepts `useState(60)`, duration constants, and ms values |
| **Result/win completeness** | New `missing_result_state` when win/survive/final-score prompts lack visible result/win/loss markers |
| **Repair prompt (conditional)** | Timer focus block when `timer_duration_mismatch`; result-state focus when `missing_result_state`; stronger closure guidance (compute next state first) |
| **Post-repair reporting** | Logs remaining issues after one repair pass (warning) without adding retries |

**Preserved:** `HAM_SCAFFOLD_QUALITY_REPAIR=false`, v1 fallback, no routing/recipe/registry/API/frontend/CI changes.

---

## 2. Tests run

```bash
pytest tests/test_scaffold_quality.py -q
# 23 passed

pytest tests/test_builder_llm_scaffold_registry_manual_smoke.py \
  tests/test_build_registry.py tests/test_build_registry_intent.py \
  tests/test_build_registry_scaffold_context.py \
  tests/test_builder_llm_scaffold_registry_context.py -q
# 435 passed
```

New coverage: elapsed-only timer flagged; `60000` / `elapsedSeconds < 60` not overflagged; missing result state flagged; result UI not overflagged; conditional repair focus blocks; post-repair remaining-issue log.

---

## 3. Two-sample rerun matrix

Output root: `/tmp/ham-generated-quality-baseline-final-gap-pass/`

| Recipe | Route OK | Quality | Inspector (updated) | Timer gap | Result gap |
|--------|----------|---------|---------------------|-----------|------------|
| `game.typing-speed-racer` (v2) | yes | **Partially playable** | clean | **Improved** — reducer uses `elapsedSeconds < 60`, final results + play-again | N/A |
| `game.card-deck-turn-based` (v2) | yes | **Partially playable** | clean | N/A | **Improved** — inline `enemyHp <= 0` → "You Win!" |

**Regression check:** Neither sample regressed to Shell only.

**Post-repair log (typing):** One repair pass ran; initial output triggered `timer_duration_mismatch`; repaired output uses explicit 60-second tick boundary in reducer.

---

## 4. Gap improvement summary

| Gap | Before final pass | After final pass |
|-----|-------------------|------------------|
| Typing 60s timer | Elapsed counter ending at `>= 59`; inspector flagged | Reducer stops at `elapsedSeconds < 60`; results panel on finish |
| Card-deck win state | No win/result UI in v2 rerun | Visible win when `enemyHp <= 0` |
| Inspector coverage | Timer only; no result check | Both timer + `missing_result_state` |
| Post-repair visibility | Repair success only logged | Remaining issues logged at WARNING |

---

## 5. Remaining known limitations

- **LLM variance** — one repair pass cannot guarantee timer/result fixes every run.
- **Non-reducer closure bugs** — draw/play using stale `deck`/`hand` still possible; repair prompt guidance only.
- **Shallow loops** — resource sim depth unchanged (not in this two-sample scope).
- **No CI enforcement** — guard remains opt-in repair helper, not merge gate.

---

## 6. Recommendation

**Commit** this final gap pass (guard + tests + review). The two unresolved samples now meet acceptance targets on this rerun. Defer recipe/routing changes and additional repair retries unless a future baseline shows regression.

---

## 7. Non-goals confirmed

- No generated app output committed
- No routing, recipe YAML, registry YAML, API, frontend, Builder Studio, CI, v1 JSON, or template changes
- No commit performed as part of authoring this review
