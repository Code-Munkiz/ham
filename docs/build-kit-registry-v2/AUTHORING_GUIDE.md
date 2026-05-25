# Build Kit Registry v2 — Authoring Guide

**Status:** Documentation only. **Schema version:** `0.1`

This guide explains how to add new **generative Build Kit recipes** to the Game Pack pilot under `docs/build-kit-registry-v2/game-pack/`. It is for humans and agents authoring schema modules — not for shipping starter code or changing runtime behavior.

Related docs:

- [ADR-0016: Generative Build Kit Registry v2](../adr/0016-generative-build-kit-registry-v2.md)
- [ADR-0017: Opt-in scaffold wiring](../adr/0017-build-registry-v2-opt-in-scaffold-wiring.md)
- [Game Pack README](game-pack/README.md)
- Loader/composer package: `src/ham/build_registry/` (unwired except opt-in scaffold path)

---

## 1. Purpose

Build Kit Registry v2 recipes are **generative playbooks**: structured YAML that tells HAM *how* to compose guidance for custom code generation. They are **not** templates, starter repos, or checked-in game source.

Use this guide when:

- Adding a new app type (recipe) to the Game Pack pilot
- Adding reusable mechanics, contracts, validators, or recovery modules
- Extending tests and validation so the registry stays machine-checkable

Do **not** use this guide to:

- Create `App.tsx`, Vite starters, or clone baselines
- Wire chat routing or enable v2 by default
- Claim validators or recovery playbooks are executable unless a separate wiring task says so

---

## 2. Core principles

| Principle | Meaning |
|-----------|---------|
| **Generative playbooks** | Modules describe behavior, contracts, and validation *intent*. HAM generates unique source from prompt + composed context. |
| **No starter source files** | Never add game code, scene files, or “example implementations” to the repo as part of recipe authoring. |
| **No template cloning** | Do not check in copy-paste React components “for reference.” Use `non_template_statement` on every module. |
| **Recipe ≠ routing** | Adding a recipe to the pack does **not** route user prompts to it. Routing is a separate, reviewed phase. |
| **Routing needs approval** | Prompt → `registry_v2_app_type` mapping lives in `src/ham/build_registry/intent.py` (or future equivalents) and requires explicit scope + tests. |
| **Validators/recovery are conceptual** | `runner: conceptual` modules document future checks/repairs. They do not run in production unless separately wired. |
| **Default behavior unchanged** | `HAM_BUILD_REGISTRY_V2_ENABLED` stays off by default. v1 Builder Kits remain the production fallback unless a dedicated task opts in. |

---

## 3. Registry anatomy

All Game Pack modules live under `docs/build-kit-registry-v2/game-pack/` and are indexed by **`registry-pack.yaml`** (`pack.game`).

| Directory / file | Kind | Role |
|------------------|------|------|
| **`registry-pack.yaml`** | `registry_pack` | Authoritative index (`module_index`), compose defaults, render section order. Every module id must appear here. |
| **`app-types/`** | `app_type` | Recipe root: intent, safety, `composed_modules`, `build_phases`, acceptance/out-of-scope. |
| **`stack-kits/`** | `stack_kit` | Technology stack playbook (e.g. DOM React + Vite guidance). |
| **`mechanics/`** | `mechanic` | Behavioral recipes (economy, timer, question set). Declare `depends_on` for compose order. |
| **`component-contracts/`** | `component_contract` | UI/layout contracts — props, states, a11y notes. Not source files. |
| **`validators/`** | `validator` | Conceptual pass/fail rules. Link `recovery_playbooks` when repair is known. |
| **`recovery-playbooks/`** | `recovery_playbook` | Conceptual repair steps (`steps[]`, `max_attempts`). |
| **`progress-labels/`** | `progress_label` | Normie-friendly phase copy; `source_phase_owner` must match an app type. |
| **`learning-hooks/`** | `learning_hook` | Future telemetry/event shapes — not emitted today. |

**Loader rule:** Every `*.yaml` under the pack (except `registry-pack.yaml`) must have an `id` listed in `module_index`. Orphan files and missing index entries both fail validation.

---

## 4. Required recipe workflow

Follow this order when adding a new app type (e.g. `game.example-recipe`):

1. **Choose recipe id** — `{domain}.{kebab-name}` (e.g. `game.trivia-timer`). Must be unique in `module_index.app_types`.
2. **Check reusable modules** — Scan existing mechanics, contracts, stack kits, validators. Prefer reuse (see §6).
3. **Create app-type file** — `app-types/game.example-recipe.yaml` with all required fields (§7).
4. **Add missing mechanics** — One YAML per new mechanic under `mechanics/`.
5. **Add missing component contracts** — Under `component-contracts/`.
6. **Add validators** — Under `validators/`; set `severity`, `runner: conceptual`, link recovery.
7. **Add recovery playbooks** — Under `recovery-playbooks/` with non-empty `steps[]`.
8. **Add progress labels** — `progress-labels/` with `phase_message_map` covering every `build_phases` id on the app type.
9. **Add learning hooks** — `learning-hooks/` (event name shapes only).
10. **Update `registry-pack.yaml`** — Add every new id to the correct `module_index` list. Bump `compose_defaults.max_modules` if the pack grows.
11. **Update README** — Add the recipe to `game-pack/README.md` (layout, composition example) when it is a pilot milestone.
12. **Add tests** — Extend `tests/test_build_registry.py` (compose order, render markers, budget, regression for existing recipes).
13. **Run validation** — Commands in §8.

---

## 5. Naming conventions

| Entity | Pattern | Example |
|--------|---------|---------|
| App type id | `{domain}.{kebab-name}` | `game.idle-incremental`, `game.trivia-timer` |
| Mechanic id | `mechanic.{kebab-name}` | `mechanic.timer` |
| Component id | `component.{kebab-name}` | `component.question-card` |
| Validator id | `validator.{kebab-name}` | `validator.timer-cleanup` |
| Recovery id | `recovery.{kebab-name}` | `recovery.stale-timer-or-uncleared-timeout` |
| Progress label id | `progress.{kebab-name}` | `progress.trivia-timer` |
| Learning hook id | `learning.{kebab-name}` | `learning.trivia-timer` |
| Stack kit id | `stack.{kebab-name}` | `stack.dom-game-minimal` |
| Filename | kebab-case, matches topic | `question-set.yaml`, `timer-cleanup.yaml` |
| Schema version | `"0.1"` on pack and every module | Must match `EXPECTED_SCHEMA_VERSION` in loader |

**Tags:** Use `tag:...` in `applies_to` for cross-cutting reuse (e.g. `tag:dom-casual-game`). Prefer stable ids over free-form prose in reference fields.

---

## 6. Reuse policy

### Prefer reuse when

| Module | Reuse when |
|--------|------------|
| **`stack.dom-game-minimal`** | DOM React game, client-only, no canvas/WebGL/multiplayer — matches most Game Pack MVP recipes. |
| **`component.game-shell`** | Standard header / main / footer layout for a single-page casual game. |
| **`mechanic.score`** | Any recipe with a primary score or currency display (idle coins, trivia points). |
| **`component.resource-counter`** | HUD for primary numeric display; for non-currency scores, document “Score/Points” in guidance (see trivia example). |

### Create a new module when

- Behavior is materially different (e.g. `mechanic.question-set` vs `mechanic.economy`)
- UI contract has different props/states (e.g. `component.choice-list` vs `component.upgrade-card`)
- Validation goal is recipe-specific (timer cleanup vs passive income tick)
- Reusing would force misleading `depends_on` or `applies_to` links

**Rule:** Extend `applies_to` on shared modules to include your new app type id when reuse is intentional. Do not fork a module “just for wording” — update guidance bullets instead.

---

## 7. Required app-type fields

Every `app-types/*.yaml` should include at minimum:

| Field | Notes |
|-------|--------|
| `id` | Same as filename stem conceptually (e.g. `game.trivia-timer`) |
| `kind` | `app_type` |
| `schema_version` | `"0.1"` |
| `name` | Human-readable title |
| `status` | e.g. `proposed` |
| `description` | What the generated app should do |
| `non_template_statement` | Explicit: no checked-in source, no clone baseline |
| `legacy_v1_fallback` | v1 kit id for strangler fallback (e.g. `generic`) |
| `stack_kit_id` | Must resolve in pack (usually `stack.dom-game-minimal`) |
| `safety_constraints` | Non-empty list (network, eval, accounts, etc.) |
| `composed_modules` | Lists of mechanic, contract, validator, recovery ids + scalar progress/learning |
| `build_phases` | Ordered phases with unique `id` and `order`; optional `phase.recover` |
| `acceptance_criteria` | Testable outcomes for the generated app |
| `out_of_scope` | Explicit MVP exclusions |

Recommended extras: `guidance`, `default_assumptions`, `user_prompt_examples`, `intent_signals` (for future routing design — not auto-wired).

**Progress labels:** `progress_label.source_phase_owner` must equal your app type id; `phase_message_map` keys must match `build_phases[].id` exactly.

---

## 8. Validation and tests

### Automated tests

```bash
pytest tests/test_build_registry.py -q
```

New recipes should add cases for:

- `compose_build_recipe(pack, "<your-app-type>")` mechanic/component order
- `render_playbook_context(recipe)` contains key module ids and safety constraints
- Render length `<= 12_000` characters (default budget)
- Existing recipes still compose (regression)

### Validation script

Idle (regression):

```bash
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/game-pack \
  --app-type game.idle-incremental \
  --check
```

Trivia (second recipe):

```bash
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/game-pack \
  --app-type game.trivia-timer \
  --check
```

For a **new** app type, run the same command with `--app-type <your-id> --check` before landing.

Optional render inspection:

```bash
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/game-pack \
  --app-type game.trivia-timer \
  --render-sample /dev/stdout
```

The loader validates: required fields, cross-references, dependency cycles (per recipe mechanic/component lists), progress label phase coverage, and **no orphan YAML**.

---

## 9. Definition of done

Before considering a recipe complete:

- [ ] All new YAML files listed in `registry-pack.yaml` `module_index`
- [ ] No orphan YAML (every file indexed; every index entry has a file)
- [ ] All `depends_on`, `composed_modules`, and `stack_kit_id` references resolve
- [ ] No dependency cycles among recipe mechanics or components
- [ ] `validate_registry_pack()` passes
- [ ] `compose_build_recipe()` succeeds for the new app type
- [ ] Rendered playbook context ≤ 12k chars (or document intentional exception with ADR)
- [ ] `tests/test_build_registry.py` updated and green
- [ ] Validation script passes for new and existing pilot app types
- [ ] No starter templates or game source files added
- [ ] No runtime, routing, API, or CI changes unless explicitly in scope
- [ ] `game-pack/README.md` and/or `registry-pack.yaml` description updated
- [ ] **`game.idle-incremental` and other existing recipes still validate**

---

## 10. Routing policy

**Adding a recipe does not route prompts to it.**

Current production path:

- v1 Builder Kits via `select_kit_for_prompt()` and scaffold context resolver fallback
- v2 playbook context only when **`HAM_BUILD_REGISTRY_V2_ENABLED`** is truthy **and** metadata includes `registry_v2_app_type`

Today, only **idle/incremental** prompts are routed (Phase 2E in `src/ham/build_registry/intent.py`). **`game.trivia-timer` is schema-only** — not routed.

Routing changes require a **separate task** with:

| Requirement | Detail |
|-------------|--------|
| **Narrow matching** | Conservative prompt patterns; explicit negative guards (no Tetris, no generic “game”) |
| **Feature flag** | Opt-in via `HAM_BUILD_REGISTRY_V2_ENABLED`; never default-on without product approval |
| **Tests** | Intent unit tests + scaffold message tests; no live LLM |
| **Default-off** | Unset/false flag → no `registry_v2_app_type` metadata; v1 behavior unchanged |
| **ADR alignment** | See ADR-0017 for scaffold wiring sequence |

Recipe authoring PRs should **not** include routing unless the task explicitly covers routing.

---

## 11. Examples (pilot recipes)

### `game.idle-incremental`

**Why it’s a good example:** First recipe; proves economy loop, persistence, and tick-loop failure modes on DOM stack.

**Composition (summary):**

- **Stack:** `stack.dom-game-minimal`
- **Mechanics:** score → economy → upgrades → save-load
- **Contracts:** game-shell, resource-counter, upgrade-card, save-status
- **Validators:** no-negative-currency, passive-income-tick, local-storage-roundtrip
- **Recovery:** stale-interval-or-bad-tick-loop, invalid-local-storage-json

**Routed:** Yes — behind flag + idle/clicker intent (not trivia, not generic game).

### `game.trivia-timer`

**Why it’s a good example:** Second recipe shape; reuses score + shell + stack; adds timer/progression graph distinct from idle.

**Composition (summary):**

- **Stack:** `stack.dom-game-minimal`
- **Mechanics:** question-set → score → timer → answer-validation → progression
- **Contracts:** game-shell, resource-counter, question-card, choice-list, timer-display, results-summary
- **Validators:** timer-cleanup, score-calculation, question-progression
- **Recovery:** stale-timer-or-uncleared-timeout, broken-question-progression

**Routed:** No — schema and validation only; demonstrates reuse without expanding prompt routing.

---

## 12. Common mistakes

| Mistake | Fix |
|---------|-----|
| Forgetting `registry-pack.yaml` | Every new module id must be in `module_index` |
| Duplicating stack package lists | Reference `stack.dom-game-minimal`; don’t paste `default_dependencies` into app types |
| Vague `applies_to` prose | Use app type ids (`game.trivia-timer`) or `tag:...` tokens |
| Creating templates | Playbooks only; use `non_template_statement` |
| Adding routing in a recipe PR | Split routing to a flagged, tested follow-up |
| Exceeding 12k render budget | Trim guidance bullets; split rarely-used detail to linked docs |
| Missing recovery links on validators | Set `recovery_playbooks:` on validators that expect repair |
| Executable-sounding validators | Keep `runner: conceptual`; don’t imply CI runs them unless wired |
| Progress label drift | Every `build_phases[].id` needs a `phase_message_map` entry |
| YAML syntax in TypeScript-like props | Quote strings with colons (e.g. `"onSelect: (id) => void"`) |
| Breaking idle when adding trivia | Always run idle compose + tests as regression |

---

## 13. Future evolution

Planned directions (not required for current authoring):

- **JSON Schema / CI reference checker** — Stricter structural validation beyond Python loader rules
- **Hermes-assisted recipe improvement** — Learning hooks feed quality signals; no emitter today
- **Additional Game Pack recipes** — Platformer, card games, etc., each following this guide
- **Non-game packs** — Separate `registry-pack.yaml` roots (e.g. SaaS, dashboard) with their own indexes
- **Validator runners** — Promote selected validators from `conceptual` to `harness` / `playwright` when execution exists
- **Controlled routing expansion** — One recipe at a time, flag-gated, with manual smoke tests

When those land, update this guide and `game-pack/README.md` — do not assume they exist during authoring today.

---

## Quick reference — module counts

After landing `game.trivia-timer`, the pilot pack has **33 indexed modules** and **2 app types**. New recipes increase the index count; keep `compose_defaults.max_modules` realistic for composed recipe size.

**Package entry points:** `load_registry_pack`, `validate_registry_pack`, `compose_build_recipe`, `render_playbook_context` in `src/ham/build_registry/`.

**Scaffold opt-in (when wired):** `resolve_scaffold_context()` in `src/ham/build_registry/scaffold_context.py` — requires flag + `plan.metadata["registry_v2_app_type"]`.
