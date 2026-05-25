# Build Registry v2 — Routing Strategy

Design policy for when Game Pack recipes may receive **prompt → app type** routing. This document does **not** implement routing; it defines approval criteria and rollout discipline.

Related: [STATUS.md](STATUS.md), [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md), [ADR-0017](../adr/0017-build-registry-v2-opt-in-scaffold-wiring.md).

---

## 1. Purpose

**Recipe authoring** and **prompt routing** are separate concerns.

- A recipe in `docs/build-kit-registry-v2/game-pack/` is **schema + generative playbook guidance** — validated YAML that composes and renders.
- **Routing** is optional runtime behavior: matching a user prompt to `registry_v2_app_type` so opt-in v2 scaffold context may apply.

**A recipe existing in the registry does not mean HAM should automatically route prompts to it.** New app types land as schema-only (Phase R0) unless an explicit routing change is approved, tested, and merged.

---

## 2. Current routing state

| Recipe | Routed? | Notes |
|--------|---------|--------|
| `game.idle-incremental` | **Yes** (narrow) | Only recipe with intent-router wiring today |
| `game.trivia-timer` | No | Schema-only |
| `game.branching-narrative` | No | Schema-only |
| `game.memory-match` | No | Schema-only |

**Gates in production today:**

1. **`HAM_BUILD_REGISTRY_V2_ENABLED`** must be truthy (default: off / unset).
2. Prompt must match **idle/incremental** positive patterns in `src/ham/build_registry/intent.py` and pass negative-pattern exclusions.
3. **`enrich_plan_metadata_with_registry_v2()`** sets `registry_v2_app_type` on plan metadata; scaffold resolver consumes it when flag + metadata align.

**Default lane:** v1 Builder Kits (`src/ham/data/builder_kits/`) remain default when the flag is unset, false, or intent does not match.

**Wiring entry point:** `src/ham/builder_chat_scaffold.py` → `intent.enrich_plan_metadata_with_registry_v2()` → `scaffold_context.resolve_scaffold_context()`.

---

## 3. Routing principles

| Principle | Meaning |
|-----------|---------|
| **Default-off** | `HAM_BUILD_REGISTRY_V2_ENABLED` stays off unless operator explicitly enables it. No silent v2 for all users. |
| **Narrow intent matching** | Prefer specific regex / keyword patterns over broad “game” detection. |
| **Conservative positive matches** | Route only when prompt clearly describes the recipe archetype. When in doubt, do not route. |
| **Explicit negative matches** | Block known false-positive domains (SaaS, dashboard, other game genres) before positive match. |
| **v1 fallback preserved** | Every app type keeps `legacy_v1_fallback` (pilot: `generic`). v2 load/compose/render failures fall back to v1 silently. |
| **No generic “game” routing** | Never route on `\bgame\b` alone. |
| **No routing from recipe creation alone** | Landing a YAML recipe is Phase R0; routing requires separate approval + code + tests. |
| **No routing without tests** | Selector tests, metadata enrichment tests, and smoke coverage required before merge. |
| **No user-facing kit picker yet** | Operators do not choose registry v2 app types in UI; routing is prompt-derived or manual metadata only. |

---

## 4. Routing readiness checklist

A recipe may be **considered** for routing only when **all** items pass:

- [ ] Recipe validates: `validate_game_pack_registry.py --app-type <id> --check`
- [ ] Rendered playbook context ≤ 12,000 characters
- [ ] `tests/test_build_registry.py` covers compose order and render markers for the app type
- [ ] App type YAML includes `user_prompt_examples` and documented false-positive risks
- [ ] Positive and negative prompt examples reviewed (see §5)
- [ ] `legacy_v1_fallback` defined on app type
- [ ] Manual smoke or dedicated test module documents flag-on metadata → scaffold context path
- [ ] **Explicit approval** recorded (PR description, ADR note, or operator sign-off) — routing is never bundled silently with schema-only recipe landings

---

## 5. Positive and negative intent examples

Examples guide future `intent.py` patterns. They are **not** live routing rules until implemented and tested.

### `game.idle-incremental` (routed today)

**Positive (should match when flag on):**

- “Build an idle clicker game”
- “Cookie clicker style game with upgrades”
- “Incremental tycoon — earn coins and buy upgrades”
- “Passive income clicker in the browser”

**Negative (must not match):**

- “Build a generic game”
- “SaaS dashboard for analytics”
- “Crypto trading app”
- “Tetris clone”
- “Trivia quiz with timer” (explicitly excluded in current negative patterns)

**Note:** Current implementation also blocks `trivia|quiz` globally — trivia routing must reconcile negative-pattern overlap before enabling `game.trivia-timer`.

### `game.trivia-timer` (schema-only)

**Positive candidates:**

- “Timed trivia quiz with multiple choice questions”
- “Build a quiz game with a countdown timer”
- “Multiple choice trivia game”

**Negative:**

- “Customer survey form”
- “Flashcard study app” (unless prompt clearly asks for game-like quiz UI)
- “Generic education website”
- “Idle clicker” (different archetype)

### `game.branching-narrative` (schema-only)

**Positive candidates:**

- “Branching story game where choices change the ending”
- “Choose your own adventure in the browser”
- “Interactive fiction with dialogue choices”
- “Lightweight dialogue choice RPG (DOM, static story)”

**Negative:**

- “Blog with posts”
- “Chatbot assistant”
- “Generic writing / notes app”
- “AI dungeon master with live LLM story generation” (out of MVP scope — requires runtime LLM)

### `game.memory-match` (schema-only)

**Positive candidates:**

- “Memory card matching game”
- “Flip cards to find pairs”
- “Emoji match concentration game”
- “4x4 memory game in React”

**Negative:**

- “Card battler with combat”
- “Trading card collection / deck builder”
- “Generic flashcards for studying”
- “Solitaire” (different mechanic)

---

## 6. Suggested routing rollout phases

| Phase | Name | Deliverable | Routing active? |
|-------|------|-------------|-----------------|
| **R0** | Schema-only recipe | YAML + registry index + compose/render tests | No |
| **R1** | Manual metadata smoke | Operator sets `registry_v2_app_type` in plan metadata; documents scaffold context | Manual only |
| **R2** | Flag-gated intent routing | `intent.py` patterns + `test_build_registry_intent.py` + smoke tests | Yes, flag + match |
| **R3** | False-positive hardening | Expanded negative cases, cross-recipe exclusion tests | Yes, hardened |
| **R4** | Default routing (optional) | Consider only after production confidence — **if ever** | Policy decision; not planned |

**Today:** `game.idle-incremental` is at **R2**. All other Game Pack recipes are **R0**.

---

## 7. Testing requirements

Before merging routing for a new app type, require:

| Category | Tests |
|----------|--------|
| **Selector — positive** | Prompts that must return the app type id |
| **Selector — negative** | Prompts that must return `None` (other recipes, SaaS, ambiguous) |
| **Metadata — flag off** | `enrich_plan_metadata_with_registry_v2()` does not set `registry_v2_app_type` |
| **Metadata — flag on** | Matching prompt sets `registry_v2_app_type`; non-match does not |
| **v1 preserved** | `template_kind` / v1 kit path unchanged when no v2 metadata |
| **v2 context** | `_build_scaffold_messages()` or smoke harness shows v2 header only when flag + metadata + valid app type |
| **Bad app type fallback** | Invalid `registry_v2_app_type` falls back to v1 (`fallback_reason` set) |
| **No live LLM/network** | Routing tests are pure string/env — no API calls |

Existing modules: `tests/test_build_registry_intent.py`, `tests/test_builder_llm_scaffold_registry_manual_smoke.py`, `tests/test_build_registry_scaffold_context.py`.

---

## 8. Failure / fallback policy

| Condition | Behavior |
|-----------|----------|
| **`HAM_BUILD_REGISTRY_V2_ENABLED` unset/false** | No `registry_v2_app_type` added; v1 kit context only |
| **Prompt does not match** | No v2 metadata; v1 remains |
| **Unknown / invalid app type in metadata** | v2 compose/render fails → silent v1 fallback via `legacy_v1_fallback` |
| **v2 disabled mid-path** | `registry_v2_disabled` fallback reason; v1 kit used |
| **Routing logic throws** | Must not break scaffold; treat as no match (fail closed to v1) |

Routing failures and fallback reasons should **not** surface as user-facing errors in the current phase — Lane A continues with v1 playbook context.

---

## 9. Non-goals

This routing strategy does **not** authorize:

- Default Build Registry v2 enablement for all users
- A generic “any game prompt” router
- User-facing kit picker or catalog UI
- Public API route to list/select registry v2 app types
- Automatic route generation from recipe YAML (`intent_signals` alone are insufficient)
- Telemetry, outcome facts capture, or Hermes-driven routing changes
- Templates, starter source trees, or clone baselines
- Routing changes without human review and tests

---

## 10. Next recommendation

**Do not route all four recipes at once.** Each app type needs its own R2 approval, negative-pattern review, and false-positive tests.

**If choosing one next candidate:** `game.trivia-timer` is the most plausible — DOM-native, static in-memory data, similar HUD patterns to idle — **but only after:**

1. Resolving negative-pattern overlap (`trivia|quiz` is currently blocked for idle routing)
2. Adding trivia-specific positive/negative tests in `test_build_registry_intent.py`
3. Manual smoke with flag on for representative prompts
4. **Explicit operator approval** in a dedicated routing PR (not bundled with docs or schema)

`game.branching-narrative` and `game.memory-match` should remain **R0** until trivia routing proves the multi-recipe exclusion model in production-like smoke.

---

## References

- [STATUS.md](STATUS.md) — current pack state (4 recipes, 71 modules)
- [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md) — § Routing policy
- [ADR-0017](../adr/0017-build-registry-v2-opt-in-scaffold-wiring.md) — opt-in scaffold wiring
- `src/ham/build_registry/intent.py` — live idle routing implementation
