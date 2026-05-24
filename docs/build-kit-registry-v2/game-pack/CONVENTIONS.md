# Build Kit Registry v2 — Game Pack pilot conventions

**Status:** Schema documentation only. **Not loaded at runtime.**

This file defines naming, layout, and authoring rules for YAML modules under
`docs/build-kit-registry-v2/game-pack/`. See [README.md](README.md) and
[ADR-0016](../../adr/0016-generative-build-kit-registry-v2.md).

---

## Canonical ID convention

Every module has a stable **`id`** used in composition graphs and cross-references:

```txt
{kind_prefix}.{slug}
```

| Kind | ID prefix | Example |
|------|-----------|---------|
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
| `game.idle-incremental` | `app-types/game.idle-incremental.yaml` |
| `mechanic.save-load` | `mechanics/save-load.yaml` |
| `stack.dom-game-minimal` | `stack-kits/dom-game-minimal.yaml` |
| `validator.local-storage-roundtrip` | `validators/local-storage-roundtrip.yaml` |

Exception: app type files include the full `game.*` prefix in the filename for clarity.

Every file starts with:

```yaml
# CONCEPTUAL SCHEMA PILOT — not loaded at runtime
```

---

## Directory-to-kind mapping

| Directory | `kind` value |
|-----------|----------------|
| `app-types/` | `app_type` |
| `mechanics/` | `mechanic` |
| `component-contracts/` | `component_contract` |
| `stack-kits/` | `stack_kit` |
| `validators/` | `validator` |
| `recovery-playbooks/` | `recovery_playbook` |
| `progress-labels/` | `progress_label` |
| `learning-hooks/` | `learning_hook` |

---

## Cross-reference convention

- References use **canonical `id` strings**, not filenames.
- Optional shorthand in README diagrams (e.g. `score`) must map to `mechanic.score` in composed recipes.
- **Validators** list `recovery_playbooks:` as id arrays.
- **Recovery playbooks** list `re_validate` targets as validator ids.
- **App types** list `composed_modules` with full ids where possible.

Before adding a reference, confirm the target module file exists in this pilot tree.

---

## Status values

| Status | Meaning in this pilot |
|--------|------------------------|
| `proposed` | **Only status used today.** Design data; not approved for runtime promotion. |

Future statuses (`approved`, `deprecated`) may appear when a loader exists — not in this pilot.

---

## Language rules

### Not templates

- Every module includes **`non_template_statement`**.
- Authoring must **not** describe cloning, copying, or checking in starter app/game source trees.
- Use **module**, **playbook**, **contract**, **mechanic**, **stack kit**.
- Word **template** is allowed only when explicitly negating template behavior (e.g. “not a template”).

### Conceptual validators

- Validators in this pilot set **`check_type: conceptual`**.
- They describe **pass/fail intent** for a future runner — not executable tests in this folder.
- Do not claim CI, Playwright, or artifact verifier integration exists yet.

### No runtime claims

- Do not state that HAM **loads**, **composes**, or **executes** these YAML files today.
- Do not state Registry v2 is **implemented**.
- Prefer: “future composer,” “when wired,” “conceptual,” “proposed.”

---

## Avoiding dangling references

1. Every **`id` referenced** in `composed_modules`, `recovery_playbooks`, `recommended_stack`, or validator links must have a **YAML file** in this pilot (or be documented as intentionally external).
2. Adding a new app type requires listing only modules that exist or will be added in the same change.
3. **`stack_kit_id`** on app types must match a file under `stack-kits/`.
4. Run a repo search for referenced ids before commit.

---

## Example composition — `game.idle-incremental`

Full id graph for the current pilot (future `BuildRecipe`):

```yaml
# Conceptual — not emitted by HAM today
build_recipe:
  app_type: game.idle-incremental
  stack_kit: stack.dom-game-minimal
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
