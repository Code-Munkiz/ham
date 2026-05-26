# Wave 3 Gate Fix Review: game.card-deck-turn-based

> **Card-deck quality hardening follow-up · Local operator run · Not production telemetry**

**Review date:** 2026-05-26 (UTC)

Prior reviews:

- [game.card-deck-turn-based.wave3-gate-review.md](./game.card-deck-turn-based.wave3-gate-review.md) (Conditional pass)
- [game.card-deck-turn-based.generated-review.md](./game.card-deck-turn-based.generated-review.md) (original shell-only baseline)

---

## 1. Previous conditional-pass gap

The prior fix pass improved victory wiring but left deck seeding broken:

- `useEffect` built 10 cards and dispatched `NEW_GAME` with `deck: shuffledDeck`
- Reducer `NEW_GAME` returned `initialState` and ignored the payload
- `deck`/`hand` stayed empty at runtime
- Post-repair inspector reported `empty_deck_seed@src/App.tsx`

---

## 2. What changed in this final pass

Extended `src/ham/scaffold_quality.py`:

| Change | Code | Purpose |
|--------|------|---------|
| Ignored seed payload | `ignored_seed_payload` | Flag NEW_GAME/RESET/START dispatches with deck/hand data when reducer returns static empty/default state without reading `action.payload` / `action.deck` |
| Card-deck repair prompt | expanded focus block | Explicit payload→reducer wiring, non-empty start deck/hand, no disconnected card arrays |
| Victory pattern tweak | `missing_victory_wiring` | Accept inline `enemyHealth <= 0` win UI |

Prior detectors retained: `empty_deck_seed`, `missing_victory_wiring`, DRAW_CARD no-op refinement.

Tests: **34** scaffold quality tests (+4 new cases).

---

## 3. Tests run

```bash
pytest tests/test_scaffold_quality.py -q
# 34 passed

pytest tests/test_builder_llm_scaffold_registry_manual_smoke.py \
  tests/test_build_registry.py tests/test_build_registry_intent.py \
  tests/test_build_registry_scaffold_context.py \
  tests/test_builder_llm_scaffold_registry_context.py -q
# 435 passed
```

New coverage: ignored `NEW_GAME` payload, applied payload not overflagged, populated seed + empty reducer flagged, repair prompt seed-payload guidance.

---

## 4. Final card-deck rerun

**Output:** `/tmp/ham-card-deck-wave3-gate-review-final/`

| Check | Result |
|-------|--------|
| Route | `game.card-deck-turn-based` ✓ |
| v2 context | yes (~10,793 chars) |
| Files | 13 |
| Repair guard | ran (no remaining issues logged) |
| Post-output inspector | **0 issues — clean** |

### Generated behavior (static review)

| Requirement | Observed |
|-------------|----------|
| Non-empty deck | `src/cards.ts` — 5 card definitions; `initialState.drawPile: cardDeck` |
| Playable hand path | `useEffect` dispatches `DRAW_CARD` on start/turn |
| Play → discard | `PLAY_CARD` filters hand, pushes to `discardPile` |
| HP mutation | damage cards reduce `enemyHp` |
| Victory | `gameWon: newHp <= 0` + `ResultsPanel` |
| Restart | **Partial** — win/loss panel only; no explicit play-again control |

---

## 5. Deck seeding — fixed?

**Yes.** Cards live in `cards.ts` and seed `drawPile` directly; `DRAW_CARD` moves cards into hand. No ignored-payload `NEW_GAME` pattern on this run.

---

## 6. Victory wiring — remains fixed?

**Yes.** `PLAY_CARD` sets `gameWon` when enemy HP reaches zero; `ResultsPanel` renders win/loss text.

---

## 7. Inspector status

| Issue | Final rerun |
|-------|-------------|
| `ignored_seed_payload` | absent |
| `empty_deck_seed` | absent |
| `missing_victory_wiring` | absent |
| `noop_reducer_action` (DRAW_CARD) | absent |
| `import_export_mismatch` | absent |

**Inspector: clean** (0 issues post-output).

---

## 8. Remaining gaps

1. **No restart/new-round control** in `ResultsPanel` on this run (minor).
2. **`drawPile.pop()` mutates shared `cardDeck` array** — playable but not ideal immutability.
3. **LLM variance** — single-run evidence; not production telemetry.

---

## 9. Final gate decision

**Pass** — safe to discuss next Wave 3 recipe direction.

Card-deck generated output on this rerun meets acceptance: routed v2 context, non-empty deck, drawable hand, play/discard/HP/win loop, clean inspector. Restart is the only minor gap.

---

## 10. Recommendation

1. **Proceed with Wave 3 recipe-direction discussion.**
2. Keep optional card-deck polish (restart button, immutable deck copy) as low-priority backlog — not blocking.
3. **Do not** add recipes or routing from this fix alone.

---

## 11. References

- [game.card-deck-turn-based.wave3-gate-review.md](./game.card-deck-turn-based.wave3-gate-review.md)
- [GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md](../GENERATED_QUALITY_FINAL_GAP_PASS_REVIEW.md)
- [GENERATED_QUALITY_REPAIR_GUARD_V2_REVIEW.md](../GENERATED_QUALITY_REPAIR_GUARD_V2_REVIEW.md)
