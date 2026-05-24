# Build Kit Registry v2 — Game Pack pilot conventions

**Status:** Schema documentation only. **Not loaded at runtime.**

This file defines naming, layout, and authoring rules for YAML modules under
`docs/build-kit-registry-v2/game-pack/`. See [README.md](README.md) and
[ADR-0016](../../adr/0016-generative-build-kit-registry-v2.md).

---

## Root manifest

**`registry-pack.yaml`** is the root index for this schema pilot (`pack.game`).

- **`schema_version: "0.1"`** on the pack and on each module file.
- **`module_index`** lists every module id grouped by kind — the authoritative inventory.
- **`compose_defaults`** define default compose order, module cap, stack kit, validator policy, and recovery policy.
- **`render_sections`** define the order for future playbook context rendering.

**Cross-reference rule:** every id referenced in any module must appear in
`registry-pack.yaml` `module_index` and have a corresponding YAML file. Run a repo
search before commit.

---

## Canonical ID convention

Every module has a stable **`id`** used in composition graphs and cross-references:

```txt
{kind_prefix}.{slug}
```

| Kind | ID prefix | Example |
|------|-----------|---------|
| registry_pack | `pack.` | `pack.game` |
| app_type | `game.` or `app.` | `game.idle-incremental` |
| mechanic | `mechanic.` | `mechanic.score` |
| component_contract | `component.` | `component.game-shell` |
| stack_kit | `stack.` | `stack.dom-game-minimal` |
| validator | `validator.` | `validator.no-negative-currency` |
| recovery_playbook | `recovery.` | `recovery.stale-interval-or-bad-tick-loop` |
| progress_label | `progress.` | `progress.idle-incremental` |
| learning_hook | `learning.` | `learning.idle-incremental` |

- **Slug** segments use **kebab-case** (`save-load`, not `save_load`).
- IDs are **stable contracts**; filenames may omit the kind prefix (see below).

---

## Filename convention

```txt
{directory}/{slug}.yaml
```

- **Slug** = the portion after the first dot in `id`, or the full logical name for app types.
- Use **kebab-case** matching the id slug.

| id | File path |
|----|-----------|
| `pack.game` | `registry-pack.yaml` |
| `game.idle-incremental` | `app-types/game.idle-incremental.yaml` |
| `mechanic.save-load` | `mechanics/save-load.yaml` |
| `stack.dom-game-minimal` | `stack-kits/dom-game-minimal.yaml` |
| `validator.local-storage-roundtrip` | `validators/local-storage-roundtrip.yaml` |

Exception: app type files include the full `game.*` prefix in the filename for clarity.

Every file starts with:

```yaml
# CONCEPTUAL SCHEMA PILOT — not loaded at runtime
```

Every module includes **`schema_version: "0.1"`** matching the pack.

---

## Directory-to-kind mapping

| Directory | `kind` value |
|-----------|----------------|
| `registry-pack.yaml` (root) | `registry_pack` |
| `app-types/` | `app_type` |
| `mechanics/` | `mechanic` |
| `component-contracts/` | `component_contract` |
| `stack-kits/` | `stack_kit` |
| `validators/` | `validator` |
| `recovery-playbooks/` | `recovery_playbook` |
| `progress-labels/` | `progress_label` |
| `learning-hooks/` | `learning_hook` |

---

## Compose order

Canonical section order (from `registry-pack.yaml` `compose_defaults.compose_order`):

1. **intent** — app type description, intent signals, clarifying questions
2. **assumptions** — default assumptions, inputs, out_of_scope
3. **stack** — stack kit id and stack guidance (packages come from stack kit only)
4. **mechanics** — ordered by `depends_on` graph
5. **components** — component contracts bound to mechanics
6. **phases** — app type `build_phases` (single source of truth)
7. **validators** — conceptual check definitions
8. **recovery** — recovery playbooks linked from validators
9. **progress** — progress label phase message map (copy only)

App types may reference compose order via `compose_order_ref: pack.game#compose_defaults.compose_order`.

---

## Build phases vs progress labels

- **`app_type.build_phases`** owns phase **structure**: ids, order, optional flag, modules used.
- **`progress_label`** modules **map** those phase ids to normie-friendly copy via `phase_message_map`.
- Progress labels must set **`source_phase_owner`** to the app type id.
- Progress labels must **not** redefine phase structure independently.

---

## Standard status values

| Status | Meaning in this pilot |
|--------|------------------------|
| `proposed` | **Only status used today.** Design data; not approved for runtime promotion. |

Future statuses (`approved`, `deprecated`) may appear when a loader exists — not in this pilot.

---

## Standard dependency fields

Use on mechanics, component contracts, validators, and recovery playbooks as appropriate:

| Field | Purpose |
|-------|---------|
| **`depends_on`** | Module ids that must compose before this module (ordering + validation). |
| **`binds_components`** | Component contract ids a mechanic expects in generated UI (mechanics only). |
| **`binds_mechanics`** | Mechanic ids a component contract renders or reflects (contracts only). |
| **`provides`** | Named capability tokens this module contributes (e.g. `score_state`, `layout_regions`). |
| **`validates_modules`** | Module ids a validator checks (validators only). |
| **`repairs_validators`** | Validator ids a recovery playbook targets (recovery only). |

---

## Standard validator fields

Every validator in this pilot must include:

| Field | Pilot value | Meaning |
|-------|-------------|---------|
| **`severity`** | `blocking` | Failures prevent success copy / preview ship. |
| **`runner`** | `conceptual` | No executable runner wired today. Future: `static`, `harness`, `playwright`. |
| **`check_type`** | `conceptual` | Describes pass/fail intent only — not a live test. |

Do **not** claim validators execute, run in CI, or integrate with Playwright in this pilot.

---

## Standard recovery fields

Every recovery playbook must include:

| Field | Requirement |
|-------|-------------|
| **`max_attempts`** | Top-level integer (default `2`, matches pack `recovery_policy`). |
| **`depends_on`** | Mechanics and/or validators that trigger this playbook. |
| **`repairs_validators`** | Validator ids re-run after repair. |
| **`steps`** | Machine-oriented list: `{ id, action, detail }`. |
| **`repair_strategy`** | Human-readable guidance (may mirror `steps`; keep both). |

---

## Safety constraints

| Location | Role |
|----------|------|
| **`app_type.safety_constraints`** | Authoritative recipe-level constraints for composed builds. |
| **`stack_kit.safety_constraints_inherited`** | Stack defaults inherited by app types using that stack (subset only). |
| **`stack_kit.capabilities`** | Declarative capability tokens (local-state, no-network, etc.). |

App types own full safety constraints. Stack kits declare inherited defaults — do not duplicate the full app_type list on stack kits.

Current app_type tokens for idle pilot:

- `no-network-egress-for-mvp`
- `no-eval`
- `local-storage-only-for-mvp`
- `no-real-money-economy`

---

## Cross-reference convention

- References use **canonical `id` strings**, not filenames.
- Optional shorthand in README diagrams (e.g. `score`) must map to `mechanic.score` in composed recipes.
- **Validators** list `recovery_playbooks:` as id arrays.
- **Recovery playbooks** list `repairs_validators:` as validator id arrays.
- **App types** list `stack_kit_id` once (top level and in `composed_modules`) — packages derive from stack kit.
- **`applies_to`** must use **module ids** (`game.idle-incremental`) or **tags** (`tag:dom-casual-game`) — not vague prose.

Before adding a reference, confirm the target id exists in `registry-pack.yaml` `module_index`.

---

## Language rules

### Not templates

- Every module includes **`non_template_statement`**.
- Authoring must **not** describe cloning, copying, or checking in starter app/game source trees.
- Use **module**, **playbook**, **contract**, **mechanic**, **stack kit**.
- Word **template** is allowed only when explicitly negating template behavior (e.g. “not a template”).

### Conceptual validators

- Validators set **`runner: conceptual`** and **`check_type: conceptual`** in this pilot.
- They describe **pass/fail intent** for a future runner — not executable tests in this folder.
- Do not claim CI, Playwright, or artifact verifier integration exists yet.

### No runtime claims

- Do not state that HAM **loads**, **composes**, or **executes** these YAML files today.
- Do not state Registry v2 is **implemented**.
- Prefer: “future composer,” “when wired,” “conceptual,” “proposed.”

---

## Avoiding dangling references

1. Every **`id` referenced** must appear in **`registry-pack.yaml` `module_index`** and have a YAML file.
2. Adding a new app type requires listing modules in the pack index in the same change.
3. **`stack_kit_id`** on app types must match a file under `stack-kits/`.
4. Progress label **`phase_message_map`** keys must match **`source_phase_owner` `build_phases` ids**.
5. Run a repo search for referenced ids before commit.

---

## Example composition — `game.idle-incremental`

Full id graph for the current pilot (future `BuildRecipe`):

```yaml
# Conceptual — not emitted by HAM today
build_recipe:
  registry_pack: pack.game
  schema_version: "0.1"
  app_type: game.idle-incremental
  stack_kit_id: stack.dom-game-minimal
  mechanics:
    - mechanic.score
    - mechanic.economy
    - mechanic.upgrades
    - mechanic.save-load
  component_contracts:
    - component.game-shell
    - component.resource-counter
    - component.upgrade-card
    - component.save-status
  validators:
    - validator.no-negative-currency
    - validator.passive-income-tick
    - validator.local-storage-roundtrip
  recovery_playbooks:
    - recovery.stale-interval-or-bad-tick-loop
    - recovery.invalid-local-storage-json
  progress_labels: progress.idle-incremental
  learning_hooks: learning.idle-incremental
```

HAM would **generate custom code** from composed playbook context — not materialize this YAML as app source.

---

## Promotion path (out of scope here)

When schema review passes, modules may move to `src/ham/data/build_registry/` with the same ids and a validated loader. Until then, **`docs/build-kit-registry-v2/`** is the sole source of truth for this pilot.
