# Generated Build Review: game.card-deck-turn-based

> **Generated-build review · Local operator run · Not production telemetry · Not automated validator output · Not Hermes-generated change request**

---

## 1. Checkpoint metadata

| Field | Value |
|-------|--------|
| **Recipe id** | `game.card-deck-turn-based` |
| **Report type** | generated-build review |
| **Source** | local/manual generated output review |
| **Production telemetry** | no |
| **Automated validator** | no |
| **Hermes-generated change request** | no |
| **Review date** | 2026-05-26 (UTC) |
| **Local artifact dir** | `/tmp/ham-card-deck-generated-review/` (outside repo; not committed) |

---

## 2. Prompt used

**Exact prompt:**

> Build a browser card battle game where the player draws a hand from a shuffled deck, plays one card per turn, resolves card effects against a simple enemy, uses a discard pile, and wins by reducing the enemy health to zero.

---

## 3. Generation path

### Harness inspected (repo-established)

| Artifact | Role |
|----------|------|
| `tests/test_builder_llm_scaffold_registry_manual_smoke.py` | Opt-in smoke for `_build_scaffold_messages()` only — **no** `generate_scaffold()` network path |
| `tests/test_build_registry_intent.py` (`TestEndToEndScaffoldMessages`) | Flag-gated routing + v2 playbook injection e2e (messages only) |
| `src/ham/builder_llm_scaffold.generate_scaffold` | Public LLM scaffold API (BYO OpenRouter key) — same path used by Builder chat scaffold wiring |
| `src/ham/build_registry/intent.enrich_plan_metadata_with_registry_v2` | Production intent router metadata enrichment |

No committed one-shot operator script exists yet (OUTCOME_FACTS Phase 3 “local generator script” remains deferred). This review used a **single operator Python invocation** of the established public APIs above — not a new repo script or harness.

### Run configuration

| Setting | Value |
|---------|--------|
| **Environment flag** | `HAM_BUILD_REGISTRY_V2_ENABLED=true` |
| **API** | `generate_scaffold(plan, project_id=…, workspace_id=…)` |
| **Plan metadata** | `template_kind: generic` + intent-enriched `registry_v2_app_type` |
| **OpenRouter key** | Loaded from repo-root `.env` (not recorded) |
| **Output location** | `/tmp/ham-card-deck-generated-review/` |

### Routing result

| Check | Result |
|-------|--------|
| `select_registry_v2_app_type_for_prompt(prompt)` | `game.card-deck-turn-based` |
| `enrich_plan_metadata_with_registry_v2` | Added `registry_v2_app_type: game.card-deck-turn-based` |
| Scaffold context source | `v2` |
| Rendered v2 context length | **10,793 chars** |
| v1 Builder Kit fallback | **Not used** (no `Builder Kit context:` in messages) |

### Generation completeness

**Partially generated.**

- LLM scaffold call **succeeded** on retry (13 files, 5 assertions).
- Component **shell** and file layout were produced.
- Core **game state machine** (deck, draw, discard, effects, turn loop, victory) was **not implemented** — reducer handlers are placeholders.
- **Preview/boot was not executed** in this review pass; static inspection shows at least one import mismatch that would likely block compile.

---

## 4. Generated output summary

### Files produced (13)

| Path | Role |
|------|------|
| `index.html`, `vite.config.ts`, `package.json` | Vite + React shell |
| `src/main.tsx`, `src/index.css`, `src/App.tsx` | App entry |
| `src/components/Game.tsx` | Top-level game container (`useReducer`) |
| `src/components/Hand.tsx`, `PlayableCard.tsx` | Hand + clickable cards |
| `src/components/Opponent.tsx` | Enemy HP display |
| `src/components/ActionBar.tsx` | End Turn button |
| `src/components/EventLog.tsx` | Event log panel |
| `src/reducers/gameReducer.ts` | Intended state machine (**stubbed**) |

### Scaffold assertions (LLM-provided)

1. The game initializes with a drawn hand of cards
2. The enemy's health is displayed correctly
3. The player can play one card per turn
4. The event log records all actions taken
5. The game can determine a win/loss based on enemy health

### Observed implementation quality (static review)

- **Structure:** Sensible component decomposition matches recipe UI contracts (hand, opponent, action bar, event log).
- **State:** `initialState` only includes `enemyHp: 20`, `hand: []`, `eventLog: []` — **no** `drawPile`, `discardPile`, player HP, turn phase, or card definitions.
- **Reducer:** `PLAY_CARD` and `END_TURN` cases contain comment placeholders only; dispatch calls have **no effect** on piles, HP, or log.
- **Hand:** Renders from `state.hand`, which starts **empty** and is never populated — no shuffle/draw logic.
- **Import bug:** `src/App.tsx` uses `import { Game } from './components/Game'` but `Game.tsx` **default-exports** — likely TypeScript/build failure.
- **Safety:** No network calls, accounts, gambling, or marketplace semantics in generated source — aligned with MVP safety constraints.

Captured routing metadata and scaffold user message (including full v2 playbook injection) are in `/tmp/ham-card-deck-generated-review/routing-report.json` and `scaffold-user-message.txt`.

---

## 5. Expected-vs-observed review

| Expected behavior | Observed behavior | Pass/Partial/Fail | Notes |
|-------------------|-------------------|-------------------|-------|
| **Deck / draw pile** — shuffled deck, visible count, draw into hand | No draw pile in state; no shuffle or draw logic | **Fail** | Playbook `mechanic.deck-draw-pile` guidance present in context but not reflected in code |
| **Hand state** — cards drawn into hand, playable from hand | Hand component exists; `hand` stays empty; no card definitions | **Partial** | UI wiring only; no data |
| **Discard pile** — played cards leave hand and enter discard | No discard state or transfer logic | **Fail** | Zone absent from reducer and UI |
| **Turn loop** — player turn, play/end turn, enemy turn | `END_TURN` action dispatched but reducer no-op; no phase or enemy turn | **Fail** | ActionBar button exists; loop not implemented |
| **Card effects** — deterministic damage/heal/draw on play | `PLAY_CARD` dispatches with payload; reducer ignores it | **Fail** | PlayableCard shows `card.name` / `card.effect` but no cards instantiated |
| **Enemy / challenge state** — simple enemy HP as pressure target | `Opponent` displays static `enemyHp: 20`; never changes | **Partial** | Display-only; no enemy actions |
| **Health / victory condition** — win when enemy HP → 0 | HP never decreases; no win/loss terminal state | **Fail** | Assertion claimed but not implemented |
| **Event feedback** — log lines after play/turn | `EventLog` renders `state.eventLog`; log never updated | **Fail** | Panel present; always empty |
| **Restart / new round** — reset piles and HP after terminal state | No result state or restart control | **Fail** | Not scaffolded |
| **DOM-native / local-only** — React DOM, no backend | React + Vite; no fetch/API; local state only | **Pass** | Matches `stack.dom-game-minimal` posture |
| **Safety drift avoidance** — no gambling/marketplace/flashcard/dashboard | No excluded domains in generated copy or imports | **Pass** | Context exclusions respected in output tone |

**Overall:** Routing and v2 context injection **passed**; playable card-battle mechanics **failed** (shell-only scaffold).

---

## 6. Positive observations

- **Routing behaved correctly** behind `HAM_BUILD_REGISTRY_V2_ENABLED=true` for the exact review prompt — lowest-precedence card-deck recipe selected with strong combined signals.
- **v2 playbook injected cleanly** (~10.8k chars) with expected module ids (`mechanic.deck-draw-pile`, `mechanic.hand-state`, `mechanic.discard-pile`, `mechanic.card-turn-loop`, etc.) and **no v1 duplicate**.
- **File layout aligns with recipe UI contracts** — separate Hand, Opponent, ActionBar, EventLog, PlayableCard components rather than a monolithic file.
- **Reducer pattern chosen** (`useReducer`) matches playbook “React state / useReducer” guidance.
- **LLM assertions** explicitly name hand init, one-card-per-turn, event log, and win/loss — showing prompt + playbook were **understood at planning level** even though code was not completed.
- **Safety posture preserved** — local-only DOM game; no backend, gambling, or marketplace drift in generated source.

---

## 7. Gaps / failure modes observed

| Gap | Severity | Detail |
|-----|----------|--------|
| **Stub reducer** | High | Core `PLAY_CARD` / `END_TURN` handlers are empty placeholders |
| **Missing pile model** | High | No `drawPile`, `discardPile`, or shuffle/reshuffle logic |
| **Empty hand at runtime** | High | No initial draw despite prompt and assertions |
| **No card catalog** | High | No embedded card definitions with effects |
| **No victory terminal state** | High | Win/loss UI and HP threshold check absent |
| **No enemy turn** | Medium | Opponent is display-only |
| **Import mismatch** | Medium | Named vs default export for `Game` likely breaks build |
| **Assertions vs code gap** | Medium | LLM listed behavioral assertions but did not implement them |
| **No preview verification** | Low | This review did not npm install / vite dev the `/tmp` output |

These match several **negative outcome signals** from the manual report (cards present but no deck/hand/discard loop; effects do not change state; turns do not advance; no win/loss state).

---

## 8. Routing observations

| Observation | Assessment |
|-------------|------------|
| Exact review prompt → `game.card-deck-turn-based` | **As expected** |
| v2 context used; v1 generic kit not injected | **As expected** |
| Render length under 12k default budget | **As expected** (~10,793 chars) |
| Conservative lowest-precedence posture | **Unchanged** — prompt contained draw pile + hand + discard + turn + card play + enemy HP + victory signals |
| Cross-recipe leakage | **Not observed** in this run |

Routing behind the flag behaved as documented in [WAVE_3_CARD_DECK_CHECKPOINT.md](../WAVE_3_CARD_DECK_CHECKPOINT.md) and [CARD_DECK_AMBIGUITY_REVIEW.md](../CARD_DECK_AMBIGUITY_REVIEW.md). This review does **not** recommend broadening or tightening routing based on a single partial scaffold.

---

## 9. Recipe refinement ideas

*Documentation/YAML guidance only — not applied by this report.*

- **Emphasize “complete reducer on first scaffold”** — require initial state to include `drawPile`, `discardPile`, `hand`, `phase`, and embedded `CARDS[]` before UI polish.
- **Add explicit “minimum viable state transition” checklist** in app-type guidance — shuffle → draw opening hand → play removes from hand → discard → apply effect → check HP → enemy turn stub.
- **Strengthen event-log examples** — one template string per effect type in mechanic guidance (damage/heal/draw).
- **Call out import/export consistency** in stack guidance — default export components vs named imports (recurring LLM footgun in this run).
- **Optional “scaffold completeness” validator (future)** — conceptual check that reducer switches are non-empty and pile arrays exist (see [REGISTRY_REFERENCE_CHECKER_PROPOSAL.md](../REGISTRY_REFERENCE_CHECKER_PROPOSAL.md); not implemented).
- **Preserve ambiguity exclusions** — no change to gambling/marketplace/flashcard/pitch-deck negatives.

---

## 10. Recommendation

**Needs another generated review.**

Routing and v2 context injection worked for this prompt, but the first real LLM scaffold produced a **non-playable shell** with stubbed reducer logic and likely build errors. A follow-up generated review should:

1. Re-run `generate_scaffold` (or a full Builder chat scaffold path) with the same prompt and flag.
2. Optionally npm install + `vite build` in `/tmp` to confirm boot and capture console errors.
3. Compare whether playbook refinements (above) improve reducer completeness before proposing YAML edits.

Secondary note: if repeated runs stay shell-only, consider **minor docs/schema refinement later** to stress pile state and reducer completeness — not routing changes.

---

## 11. Related docs

- [Manual outcome report (same prompt)](./game.card-deck-turn-based.manual-outcome.md)
- [Wave 3 card deck checkpoint](../WAVE_3_CARD_DECK_CHECKPOINT.md)
- [Card deck ambiguity review](../CARD_DECK_AMBIGUITY_REVIEW.md)
- [Registry reference checker proposal](../REGISTRY_REFERENCE_CHECKER_PROPOSAL.md)
- [Routing strategy](../ROUTING_STRATEGY.md)
