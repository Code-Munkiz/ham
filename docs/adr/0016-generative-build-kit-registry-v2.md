# ADR-0016: Generative Build Kit Registry v2

## Status

**Proposed**

No runtime, test, or schema-file implementation is authorized by this ADR. Current Lane A builder behavior remains unchanged until a follow-up ADR or implementation PR explicitly lands wiring.

---

## Context

HAM already ships a **partially aligned** Builder Kit system for Lane A (workspace chat → scaffold → source snapshot → Workbench preview).

### What exists today

| Fact | Detail |
|------|--------|
| Builder Kit JSON | Six app-archetype kits under `src/ham/data/builder_kits/` (`landing-page`, `dashboard`, `todo`, `calculator`, `tetris`, `generic`). |
| Runtime loader | `src/ham/builder_kits.py` loads kits at import; exposes `get_kit`, `get_kit_for_template_kind`, `render_kit_context`. |
| LLM scaffolding | `src/ham/builder_llm_scaffold.py` injects kit context into a single OpenRouter scaffold call. |
| Kit routing | `src/ham/builder_kit_router.py` maps free-form prompts to a kit id via regex (`select_kit_for_prompt`). |
| Chat integration | `src/ham/builder_chat_hooks.py` → `maybe_chat_scaffold_for_turn` is the canonical Lane A entry. |
| Resource hints | `src/ham/data/builder_resources/resources.json` lists licensed UI/libs referenced by kits. |

### What is *not* template cloning

The legacy **deterministic** calculator/Tetris generators in `src/ham/builder_chat_scaffold.py` are **retired at runtime**. All template kinds route through the LLM scaffold path with matching kit metadata (see module header and `src/ham/builder_template_kinds.py`, where `_REGISTRY` is empty and `select_scaffold_path` always returns `"llm"`).

HAM does **not** ship checked-in starter file trees per kit. Output is **generated per prompt**.

### What is still shallow

Current kits are **one-layer app-archetype metadata**:

- `stack_recipe`, `design_recipe`, `validation_checklist`, `safety_constraints` are flat string lists.
- Composition across **features**, **mechanics**, **component contracts**, **validators**, and **recovery playbooks** does not exist.
- Intent classification and kit selection are **regex heuristics**, not registry-owned taxonomy.
- Clarifying questions are narrow (`src/ham/builder_mutation_router.py`), not kit-driven.
- Build phases exist in the Plan schema (`src/ham/builder_plan.py`, `src/ham/builder_planner.py`) but the chat happy path often **bypasses** the planner for net-new builds.
- Post-scaffold verification is **calculator-biased** (`src/ham/builder_artifact_verifier.py`); kit checklists are prompt hints, not enforced per kit.
- Recovery is **user retry + one JSON-reparse retry** in scaffold — not executable playbooks.
- Game support is a **single** `tetris.json` archetype kit, not a mechanics library or Game Pack.

### Separate lane: Builder Studio / custom builders

**Custom Builder** profiles (`src/api/custom_builders.py`, `docs/CUSTOM_BUILDER_STUDIO_SPEC.md`) are **coding-agent recipes** for Lane B (conductor, OpenCode, managed snapshots, `ControlPlaneRun`). They are an **internal cookbook** for *how HAM executes repo work*, not *what app HAM generates for normie users*.

This ADR does **not** merge Custom Builder Studio into the Build Kit Registry.

### Related docs (some stale)

- `docs/adr/0011-llm-scaffold-staged-by-template-kind.md` still describes a deterministic path for calculator/tetris that has since been retired.
- `docs/MANUS_PARITY_ROADMAP.md` still references deterministic-only scaffolds in places.

Registry v2 design should use **generative / playbook** language and avoid implying template cloning.

---

## Decision

HAM will evolve toward a **Generative Build Kit Registry v2**: an **internal, proprietary playbook system** that guides the AI through **intent classification, module composition, phased planning, code generation, validation, recovery, and normie-friendly progress** — **without** shipping static app templates.

### Core principles

1. **Generative, not clone-and-tweak.** Kits describe *how to think and build*, not *which files to copy*.
2. **Composable layers.** App types, features, mechanics, components, stacks, validators, and recovery rules are **separate registry entries** composed per request.
3. **Lane A ownership.** Registry v2 serves workspace chat → Workbench preview (Lane A). Lane B harnesses consume different profiles.
4. **Invisible kit selection by default.** Normie users describe intent; HAM composes internally. Power-user kit pickers are out of scope until product explicitly requests them.
5. **Executable recovery where possible.** Recovery playbooks prefer deterministic repair steps (re-scaffold slice, bootstrap repair, verifier-guided patch) over prose-only “try again.”
6. **Strangler migration.** v1 `BuilderKit` JSON remains loadable; v2 composes alongside or wraps v1 until migration completes.

---

## Non-goals

This ADR explicitly does **not** authorize:

| Non-goal | Rationale |
|----------|-----------|
| Starter-template cloning | Contradicts generative product direction; reintroduces maintenance and “template site” UX. |
| Public kit marketplace | Discovery, billing, and curation are product decisions deferred. |
| User-facing kit picker (normie UI) | Selection stays inferred until onboarding research supports explicit choice. |
| Giant refactor of `builder_chat_scaffold.py` | Snapshot/ZIP/artifact pipeline stays; composition orchestration adds beside it. |
| Merging Builder Studio / custom coding agents into Build Kits | Different lanes, different data models, different user stories. |
| Game Pack **runtime** implementation | This ADR defines shape and pilot only; no mechanics engine or template games. |
| Checked-in starter app or game source trees | No `starters/`, no `templates/tetris/`, no clone baselines. |
| Replacing BYO OpenRouter for scaffold/plan | Cost model unchanged unless a future ADR says otherwise. |

---

## Registry concepts

Registry v2 is organized into **layers**. Each entry is a versioned document with a stable `id`, human `title`, and machine-consumable guidance for prompts, planners, validators, and recovery runners.

| Layer | Purpose | Example ids (conceptual) |
|-------|---------|--------------------------|
| **app_type** | Top-level product shape; intent anchor; default assumptions | `app_type.landing`, `app_type.game`, `app_type.crud-list` |
| **feature_kit** | Cross-cutting product features optional per build | `feature.waitlist-capture`, `feature.dark-mode-toggle` |
| **mechanic** | Behavioral recipe (especially games & interactive apps) | `mechanic.score`, `mechanic.economy`, `mechanic.save_load` |
| **component_contract** | UI/structure contract the generator should satisfy | `component.game_shell`, `component.upgrade_card` |
| **stack_kit** | Framework/tooling defaults and constraints | `stack.vite-react-tailwind`, `stack.dom-game-minimal` |
| **validator** | Post-generate checks (static, harness, or heuristic) | `validator.no_negative_currency`, `validator.hero_above_fold` |
| **recovery_playbook** | Known failure → ordered repair steps | `recovery.stale_interval_or_bad_tick_loop`, `recovery.scaffold_json_invalid` |
| **progress_label** | Normie-facing phase names for activity stream / chat | `progress.understanding_request`, `progress.building_preview` |
| **learning_hook / telemetry event** | Structured outcome signals for Hermes / analytics | `telemetry.kit_composition`, `telemetry.validation_failed` |

**Composition** produces a **BuildRecipe** (working name): an ephemeral bundle of registry entry ids + resolved parameters for one user turn or Plan.

---

## Proposed schema shape (conceptual)

Illustrative only — not implemented, not validated by CI.

### app_type — `app_types/game.yaml` (conceptual)

```yaml
# CONCEPTUAL — not implemented
id: app_type.game
version: "1.0.0"
title: Interactive browser game
intent_patterns:
  - "\\b(game|playable|clicker|idle|incremental|arcade)\\b"
default_assumptions:
  - "DOM-first React; no WebGL unless user explicitly asks"
  - "Local state only; mock persistence via localStorage when save_load mechanic selected"
clarifying_questions:
  - when: "intent_confidence < medium"
    ask: "Do you want a simple clicker/idle game, or something with levels and movement?"
optional_feature_kits: [feature.settings-panel]
required_stack_kit: stack.dom-game-minimal
compatible_mechanics: [mechanic.score, mechanic.economy, mechanic.upgrades, mechanic.save_load]
component_contracts: [component.game_shell]
default_validators: [validator.app_boots_no_console_errors]
default_recovery: [recovery.scaffold_json_invalid]
progress_labels:
  - progress.understanding_request
  - progress.composing_recipe
  - progress.generating_code
  - progress.validating
  - progress.preparing_preview
safety:
  - no-network-egress
  - no-eval
```

### mechanic — `mechanics/score.yaml` (conceptual)

```yaml
# CONCEPTUAL — not implemented
id: mechanic.score
version: "1.0.0"
title: Score tracking
description: >
  Maintain a numeric score state, display it in a HUD, update on defined game events.
planner_hints:
  - "Expose score in React state; avoid global singletons"
  - "HUD must be visible without scrolling on 360px viewport"
generator_hints:
  - "Include increment/decrement or event-driven score updates as described in user prompt"
validators: [validator.score_renders_numeric]
telemetry_events: [telemetry.mechanic_applied]
```

### mechanic — `mechanics/timer.yaml` (conceptual)

```yaml
# CONCEPTUAL — not implemented
id: mechanic.timer
version: "1.0.0"
title: Interval / tick loop
description: >
  Time-based updates using requestAnimationFrame or setInterval with cleanup.
planner_hints:
  - "Clear intervals on unmount; guard against stale closures"
recovery_playbooks: [recovery.stale_interval_or_bad_tick_loop]
```

### component_contract — `components/game-shell.yaml` (conceptual)

```yaml
# CONCEPTUAL — not implemented
id: component.game_shell
version: "1.0.0"
title: Game shell layout
structure:
  - "Header or HUD region for score/status"
  - "Primary playfield (flex-centered)"
  - "Optional footer for controls/help"
accessibility:
  - "Focusable controls where keyboard input is used"
style_guidance:
  - "Readable contrast; mobile-safe tap targets"
```

### validator — `validators/local-storage-save-load.yaml` (conceptual)

```yaml
# CONCEPTUAL — not implemented
id: validator.local_storage_roundtrip
version: "1.0.0"
title: Save/load roundtrip
kind: harness_heuristic  # static | harness_heuristic | playwright
applies_when: [mechanic.save_load]
check: >
  Generated code writes game state to localStorage on change and restores on mount
  without throwing; keys must not store secrets.
on_fail: recovery.save_load_schema_mismatch
```

### recovery — `recovery/stale-interval.yaml` (conceptual)

```yaml
# CONCEPTUAL — not implemented
id: recovery.stale_interval_or_bad_tick_loop
version: "1.0.0"
title: Fix runaway or stale timer loop
triggers:
  - validator: mechanic.timer
  - symptom: preview_frozen_or_cpu_spike
steps:
  - action: prompt_patch
    instruction: "Add cleanup in useEffect; ensure tick callback uses functional setState"
  - action: re_validate
    validator: validator.app_boots_no_console_errors
max_attempts: 2
normie_message: "I adjusted the game timer so the preview stays responsive."
```

### Composed BuildRecipe (ephemeral, conceptual)

```yaml
# CONCEPTUAL — produced at runtime, not stored as a template
build_recipe_id: br_20260522_example
user_prompt_hash: "…"
app_type: app_type.game
feature_kits: []
mechanics: [mechanic.score, mechanic.economy, mechanic.upgrades, mechanic.save_load]
component_contracts: [component.game_shell, component.upgrade_card]
stack_kit: stack.dom-game-minimal
validators: [validator.no_negative_currency, validator.local_storage_roundtrip]
recovery_playbooks: [recovery.stale_interval_or_bad_tick_loop, recovery.scaffold_json_invalid]
assumptions_applied: ["DOM-first React", "localStorage persistence"]
clarifications_asked: []
```

---

## Runtime flow (future)

Target orchestration for Lane A once registry v2 is wired. **None of this replaces current behavior until explicitly implemented.**

```txt
User prompt
  → intent classification (registry-aware taxonomy + confidence)
  → registry composition (select app_type, optional features/mechanics/components/stack)
  → clarifying questions OR default assumptions (confidence/policy gated)
  → phased build plan (Plan steps derived from composed recipe + progress_labels)
  → scaffold / generate (LLM with composed playbook context — not file clone)
  → validate (run kit-linked validators; static + harness)
  → recover if needed (execute recovery_playbook steps; bounded attempts)
  → preview (existing snapshot + cloud/local runtime — unchanged contract)
  → summarize (normie-friendly progress_label completion copy)
  → record telemetry (learning_hook events for Hermes / analytics)
```

### Module ownership (proposed)

| Stage | Likely owner module (future) | Today |
|-------|------------------------------|-------|
| Intent + composition | **New:** `build_kit_registry.py` (name TBD) | `builder_chat_intent.py`, `builder_kit_router.py` |
| Clarify / assume | Registry + `builder_mutation_router.py` | Regex-only clarify |
| Phased plan | `builder_planner.py` + registry step templates | Often bypassed on net-new chat build |
| Generate | `builder_llm_scaffold.py` | Kit context string only |
| Validate | `builder_verifier.py`, `builder_artifact_verifier.py` + registry validators | Calculator-biased artifact checks |
| Recover | **New:** recovery runner (calls playbooks) | Single JSON retry |
| Preview | `builder_chat_scaffold.py`, `builder_chat_cloud_runtime.py` | Shipped |
| Telemetry | `builder_usage_event_store.py` + Hermes hooks | Partial / TBD |

---

## Migration from current v1 BuilderKit

Strangler mapping — v1 kits remain valid during transition.

| v1 field (`BuilderKit` / JSON) | v2 destination | Notes |
|--------------------------------|----------------|-------|
| `kit_id` | `app_type.id` or legacy alias | e.g. `landing-page` → `app_type.landing` |
| `app_archetype` | `app_type.title` / taxonomy tag | Human label |
| `supported_template_kinds` | `app_type.legacy_template_kinds` | Compatibility for `template_kind` in Plan metadata |
| `stack_recipe` | `stack_kit.packages` + hints | Split into structured stack module |
| `design_recipe` | `component_contract` + style guidance | Patterns become contracts, not prose lists |
| `expected_files` | `app_type.expected_artifacts` | Still generative targets, not template paths |
| `expected_routes` | `app_type.expected_routes` | Unchanged semantics |
| `allowed_capabilities` | `app_type.capabilities` | Policy tokens |
| `validation_checklist` | One or more `validator` entries | Executable validators replace plain-English-only lists |
| `safety_constraints` | `app_type.safety` + recovery triggers | Safety may invoke recovery on violation |
| `recommended_resources` | `stack_kit.resource_refs` | Continue pointing at `builder_resources` catalog |
| `examples` | `app_type.example_prompts` | Drive onboarding; currently empty in all v1 JSON |
| `legacy_parity_only` | **Deprecate** | Misleading post-deterministic retirement |
| `render_kit_context()` output | `BuildRecipe.render_playbook_context()` | Richer composed narrative for LLM |

**Compatibility rule:** `get_kit_for_template_kind()` continues to resolve v1 ids until callers migrate to composition API.

---

## Game Pack pilot

**Game Pack** is the first **serious pilot** for registry v2 — not because games are the only use case, but because they stress **mechanics composition**, **validators**, and **recovery** in ways flat landing-page kits do not.

### What Game Pack is not

- Not a library of Tetris/Snake/Platformer **templates**
- Not checked-in game source trees
- Not “pick a game → clone repo”

### What Game Pack is

- A **recipe system**: compose mechanics + contracts + validators + recovery for **custom** games from natural language
- Phased: **DOM-native, low-risk** games before realtime physics / WebGL / multiplayer

### Pilot candidate: `game.idle-incremental`

| Module | Conceptual id | Role |
|--------|---------------|------|
| app_type | `app_type.game` | Intent anchor; DOM-first defaults |
| feature (optional) | `feature.settings-panel` | Mute/reset if user asks |
| mechanic | `mechanic.score` | Points / primary currency display |
| mechanic | `mechanic.economy` | Income rates, costs, purchasing |
| mechanic | `mechanic.upgrades` | Upgrade cards/buttons with escalating costs |
| mechanic | `mechanic.save_load` | localStorage persistence |
| component_contract | `component.game_shell` | HUD + playfield layout |
| component_contract | `component.upgrade_card` | Repeatable upgrade UI pattern |
| stack_kit | `stack.dom-game-minimal` | Vite + React + TS + Tailwind (aligns with current bootstrap) |
| validator | `validator.no_negative_currency` | Economy invariants |
| validator | `validator.local_storage_roundtrip` | Save/load sanity |
| recovery | `recovery.stale_interval_or_bad_tick_loop` | Timer/tick bugs in idle loops |
| recovery | `recovery.scaffold_json_invalid` | Reuse global scaffold parse recovery |
| progress_label | `progress.*` | Normie activity stream |

**Pilot scope boundary:** incremental/clicker-style DOM games only. Defer: physics engines, canvas sprite sheets, multiplayer, audio-heavy games.

**Relation to v1:** Existing `tetris.json` remains until v2 Game Pack proves mechanics composition; Tetris may later decompose into mechanics (`piece_rotation`, `line_clear`, `keyboard_input`) rather than a monolithic archetype kit.

---

## Risks

| Risk | Mitigation |
|------|------------|
| **Schema overengineering** | Pilot one app type (`game.idle-incremental`) + one non-game (`landing`) before generalizing; require 2+ consumers per new layer type. |
| **“Kit” confused with “template”** | Ban starter trees in registry; ADR + doc glossary; deprecate `template_kind` naming over time. |
| **Stale docs** | Follow-up docs PR for ADR-0011, MANUS parity row #2, PHASE_2_DESIGN §9 status notes. |
| **Duplicate builder concepts** | Keep glossary: Build Kit Registry (Lane A) vs Custom Builder (Lane B). |
| **Planner bypassing phases** | When wiring v2, net-new chat builds must emit at least minimal phased Plan from registry `progress_labels`. |
| **Validation not enforced per kit** | Validators must be typed (`static` / `harness` / `playwright`); checklist strings alone insufficient for v2 compliance. |
| **Recovery devolves to prompt-only** | Playbooks require machine-readable `steps[]` with bounded `max_attempts`; normie_message is output, not the fix. |
| **OpenRouter unavailable** | Registry does not remove BYO gate; composition should fail with same honest `model_access_required` signal. |

---

## Recommended next steps

Small, sequential, **docs-first** — no runtime until schema review passes.

1. **Review this ADR** with product + builder lane owners; resolve open questions below.
2. **Stale docs cleanup** (separate docs PR): mark ADR-0011 historical; update MANUS parity scaffold row to “LLM + kit metadata.”
3. **Define minimal schema files** for one pilot only (`game.idle-incremental`) under a agreed path (see open questions) — YAML or JSON, **no Python loader**.
4. **Second pilot schema** (`app_type.landing` or migrate `landing-page.json` field mapping on paper).
5. **Glossary entry** in `docs/PHASE_2_DESIGN.md` or `AGENTS.md`: Build Kit Registry v2 vs Custom Builder vs v1 `BuilderKit`.
6. **Defer runtime wiring** until: (a) composition API sketch approved, (b) validator/recovery execution contract agreed, (c) pilot schemas reviewed.

---

## Open questions

1. **Registry file path:** Should v2 live under `src/ham/data/build_kits_v2/`, `src/ham/data/build_registry/`, or split `docs/build_registry/` (spec) vs `src/ham/data/` (runtime)? *Recommendation:* spec prototypes in `docs/build_registry/` until loader exists, then promote to `src/ham/data/build_registry/`.

2. **Evolve vs replace loader:** Should `builder_kits.py` grow composition methods, or should a new module (e.g. `build_kit_registry.py`) own v2 while v1 re-exports compatibility shims? *Recommendation:* new module owns composition; v1 loader untouched until strangler complete.

3. **Hermes learning / telemetry:** Which events feed Hermes critique vs operator analytics? Proposed: emit `telemetry.kit_composition`, `telemetry.validation_failed`, `telemetry.recovery_applied` with `{app_type, mechanics[], outcome}` — no secrets, no raw prompts in durable store without policy review.

4. **Invisible kit selection:** Should v2 stay fully inferred for normie users? *Default yes*; optional operator debug surface may show composed recipe in Workbench technical drawer later.

5. **Clarify vs assume:** When should HAM ask vs apply `default_assumptions`? *Proposal:* ask when `intent_confidence == low` OR destructive/recovery-prone OR missing mechanic required for stated goal; otherwise assume and state assumptions in plan summary (“I’m assuming a simple browser clicker…”).

6. **Validator execution surface:** Reuse `scripts/ham-builder-qa/` Playwright harness, extend artifact verifier, or both? Pilot likely needs **both** static heuristics and one harness case.

---

## Consequences

- Registry v2 is the **target architecture** for generative app building on Lane A; v1 kits remain operational.
- Game Pack pilot validates mechanics/recovery design before expanding to SaaS, auth, or network-backed kits.
- Custom Builder Studio and coding-agent harnesses **stay separate**; no merge pressure from this ADR.
- Implementation PRs must reference this ADR and include a migration note for any v1 field deprecation.
- Reversing this ADR means continuing with v1 one-layer kits only — no wire-format breakage because v2 is not yet wired.

---

## References

- `src/ham/builder_kits.py` — v1 registry loader
- `src/ham/builder_llm_scaffold.py` — LLM scaffold + `render_kit_context`
- `src/ham/builder_kit_router.py` — regex kit selection
- `src/ham/builder_chat_hooks.py` — Lane A orchestration
- `docs/adr/0011-llm-scaffold-staged-by-template-kind.md` — historical staged migration (partially superseded by deterministic retirement)
- `docs/CUSTOM_BUILDER_STUDIO_SPEC.md` — Lane B custom builders (orthogonal)
- `docs/PHASE_2_DESIGN.md` § Subsystem 9 — LLM scaffolds + Builder Kits
- `docs/capabilities/capability_bundle_directory_v1.md` — agent capability bundles (related but distinct from app build kits)
