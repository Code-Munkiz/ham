# Game Pack — Build Kit Registry v2 schema pilot

**Status:** Non-runtime schema pilot only. **Schema version:** `0.1`

This directory holds **design data** for the first [Generative Build Kit Registry v2](../../adr/0016-generative-build-kit-registry-v2.md) Game Pack pilot: **`game.idle-incremental`**.

## Root manifest

**[`registry-pack.yaml`](registry-pack.yaml)** (`pack.game`) is the authoritative index:

- Lists all module ids by kind in `module_index`
- Defines `compose_defaults` (compose order, max modules, default stack kit, validator/recovery policy)
- Defines `render_sections` for future playbook context assembly
- Carries `schema_version: "0.1"` and `non_runtime_notice`

All cross-references should resolve through the pack manifest. See **[CONVENTIONS.md](CONVENTIONS.md)**.

## What this is

- **Generative playbook modules** — app types, mechanics, component contracts, **stack kits**, validators, recovery playbooks, progress labels, and learning hooks.
- **Intended** to guide future registry **composition** (intent → modules → phased plan → generate → validate → recover).
- **Documentation under `docs/`** — not loaded by HAM at runtime today.

## What this is not

- **Not starter templates.** HAM must not clone these YAML files or any checked-in game source tree.
- **Not generated game files.** No `App.tsx`, no asset bundles, no prefab scenes.
- **Not wired.** No loader in `src/ham/`, no changes to v1 `src/ham/data/builder_kits/*.json`, no chat/scaffold integration.
- **Not a claim of implementation.** Registry v2 composition, validation execution, and recovery runners are **proposed** in ADR-0016 only.
- **Validators and recovery remain conceptual.** `runner: conceptual` and `check_type: conceptual` — they describe intent, not live execution.

Use vocabulary: **module**, **playbook**, **contract**, **mechanic**. Avoid “template” except when stating these are **not** templates.

## Build phases ownership

- **`app_type.build_phases`** (`game.idle-incremental`) owns phase structure (ids, order, optional flags).
- **`progress_label`** (`progress.idle-incremental`) maps those phase ids to normie-friendly copy via `phase_message_map` and `source_phase_owner`.
- Progress labels do **not** redefine phases independently.

## Why `game.idle-incremental` first

| Reason | Detail |
|--------|--------|
| **DOM-native** | React + Tailwind UI; no canvas/WebGL/physics engine required for MVP proof. |
| **Low technical risk** | Single-page local state; aligns with existing Lane A safety (`no-network-egress`). |
| **Mechanics reuse** | Score, economy, upgrades, and save/load compose cleanly and recur in other casual games. |
| **No asset pipeline** | No spritesheets, audio packs, or level editors in scope. |
| **Strong Game Pack proof** | Exercises composition, validators, tick-loop recovery, and persistence — without Tetris-style monolithic archetype kits. |

## Pilot module layout

```txt
docs/build-kit-registry-v2/game-pack/
  README.md
  CONVENTIONS.md
  registry-pack.yaml          # pack.game — root manifest (schema_version 0.1)
  app-types/game.idle-incremental.yaml
  stack-kits/dom-game-minimal.yaml
  mechanics/{score,economy,upgrades,save-load}.yaml
  component-contracts/{game-shell,resource-counter,upgrade-card,save-status}.yaml
  validators/{no-negative-currency,passive-income-tick,local-storage-roundtrip}.yaml
  recovery-playbooks/{stale-interval-or-bad-tick-loop,invalid-local-storage-json}.yaml
  progress-labels/idle-incremental.yaml
  learning-hooks/idle-incremental.yaml
```

## Conceptual composition example

When a user says *“Build me a simple idle clicker where I earn coins and buy upgrades”*, a **future** composer would assemble:

```txt
registry_pack: pack.game
schema_version: 0.1
app_type:     game.idle-incremental
stack_kit:    stack.dom-game-minimal
mechanics:    mechanic.score → mechanic.economy → mechanic.upgrades → mechanic.save-load
contracts:    component.game-shell, component.resource-counter, component.upgrade-card, component.save-status
validators:   validator.no-negative-currency, validator.passive-income-tick, validator.local-storage-roundtrip
recovery:     recovery.stale-interval-or-bad-tick-loop, recovery.invalid-local-storage-json
progress:     progress.idle-incremental
learning:     learning.idle-incremental
```

Full id graph and dependency fields: [CONVENTIONS.md](CONVENTIONS.md#example-composition--gameidle-incremental).

HAM would then **generate custom code** from the composed playbook context — not copy a starter repo.

## Relation to v1 Builder Kits

v1 `tetris.json` / `calculator.json` remain **unchanged** one-layer archetype metadata. This pilot explores **decomposed mechanics** as the path forward for games. App type includes **`legacy_v1_fallback: generic`** for strangler routing when wired. See ADR-0016 § Game Pack pilot.

## Next steps (out of scope for this folder)

1. Promote approved YAML to `src/ham/data/build_registry/` **only after** loader/composer ADR is accepted.
2. Wire composition into Lane A chat scaffold — **separate implementation PR**.
3. Expand validator `runner` enum beyond `conceptual` when harness exists.
