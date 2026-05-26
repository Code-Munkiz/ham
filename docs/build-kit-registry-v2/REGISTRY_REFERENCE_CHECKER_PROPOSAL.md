# Build Registry v2 Reference Checker Proposal

Design proposal for a **lightweight reference checker** (and optional JSON Schema layer) for the Game Pack registry. This document does **not** implement tooling, change CI, alter runtime behavior, or modify registry YAML.

**Context:** 11 recipes, 247 modules, all routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`; v1 default when flag off; manual outcome reports indexed at [outcome-reports/OUTCOME_REPORT_INDEX.md](outcome-reports/OUTCOME_REPORT_INDEX.md).

---

## 1. Executive summary

Build Registry v2 has reached **11 recipes** and **247 indexed modules**.

Existing validation proves recipes can **load**, **compose**, and **render** within budget via `scripts/validate_game_pack_registry.py` and `tests/test_build_registry.py`. That baseline is necessary but not a formal **reference contract** across the whole pack index.

The next guardrail should be a **boring, lightweight reference checker** — optionally backed by JSON Schema later — whose job is to catch registry mistakes early:

- Missing or stale references
- Duplicate or mistyped module IDs
- Invalid or incomplete required fields
- Render budget drift
- Accidental template-like language or executable-validator confusion

**This proposal defines scope and phases only.** No implementation, CI enforcement, or runtime wiring is authorized from this document alone.

---

## 2. Problem statement

| Pain | Why it matters now |
|------|-------------------|
| **Manual `registry-pack.yaml` indexing** | Every new recipe adds ~20–30 module entries; omission or typo breaks compose silently until someone runs validation |
| **Large module surface (247+)** | Drift between indexed IDs and on-disk files compounds with each Wave |
| **Render budgets** | Recipes near 12k need consistent measurement; truncation hides content loss |
| **`applies_to` staleness** | Component contracts and mechanics reference app types that may rename or lag STATUS |
| **ID typos** | `mechanic.deck-draw-pile` vs `mechanic.deck_draw_pile` fails at compose time, not at edit time |
| **Required field divergence** | App types, validators, and recovery modules share patterns (`non_template_statement`, `runner`, `severity`) that can drift |
| **Non-template constraints** | Generative playbook posture must stay explicit; checker can flag missing anti-template language |
| **Conceptual vs executable validators** | Validators/recovery are `runner: conceptual` today — must not be mistaken for build-time executors |
| **Routing vs authoring separation** | Recipe YAML must not imply routing; routing lives in `intent.py` and tests |

The registry should not become a **YAML petting zoo with opinions**. A checker should enforce **boring consistency**, not product behavior.

---

## 3. Current validation baseline

| Layer | What it does today | Gap |
|-------|-------------------|-----|
| **`scripts/validate_game_pack_registry.py`** | Loads pack from `--pack-root`, runs `validate_registry_pack`, optional `--app-type` compose, optional `--render-sample`; exit 1 on failure with `--check` | Single app-type compose by default; no pack-wide orphan/drift report; no STATUS/intent cross-check |
| **`src/ham/build_registry/`** | Loader, reference validation, compose order, render budget truncation | Logic exists but not exposed as a dedicated “reference audit” CLI |
| **`tests/test_build_registry.py`** | Pack load (module count), per-recipe compose/render/budget, adaptive policy fields | Not a exhaustive reference matrix; updated manually when recipes land |
| **`tests/test_build_registry_intent.py`** | Routing positives/negatives, metadata, scaffold e2e | Separate from YAML reference integrity |
| **Authoring workflow** | Human edits YAML + `registry-pack.yaml` + STATUS + tests | No single “did I forget to index a file?” command |

**Conclusion:** Validation is **useful and green**, but there is **no formal schema/reference contract** document or dedicated checker script yet.

---

## 4. Proposed checker scope

### In scope

- Validate `registry-pack.yaml` module index references resolve to existing YAML files
- Ensure every loaded module has **required core fields** for its `kind` (id, kind, name, schema_version, etc.)
- Ensure **IDs match filenames** where convention applies (e.g. `mechanic.deck-draw-pile.yaml` → `id: mechanic.deck-draw-pile`)
- Ensure **`applies_to` app type ids** exist in `module_index.app_types`
- Ensure **app type `composed_modules`** reference modules that exist in the pack
- Ensure recipes **compose** in declared dependency order (delegate to existing compose)
- **Render budget:** error on overflow; warning when within ~90% of default 12k cap
- **Duplicate IDs** across the pack
- **Orphan detection (optional):** YAML files on disk not listed in `registry-pack.yaml`
- **Anti-template language:** warn if `non_template_statement` missing on app types (and optionally other kinds per AUTHORING_GUIDE)
- **Conceptual modules:** warn if validator/recovery lacks `runner: conceptual` (or equivalent documented convention)

### Out of scope

- Runtime execution, API, frontend, Builder Studio
- Scaffold / LLM output quality scoring
- Production telemetry or outcome-facts ingestion
- Hermes autonomous edits or auto-fix of YAML
- **Routing decisions** — checker may flag doc/test mismatches, not change `intent.py`
- Template/starter file detection beyond explicit field conventions

---

## 5. JSON Schema proposal

**Do not create these files yet.** When checker behavior stabilizes, optional schemas could live under e.g. `docs/build-kit-registry-v2/schemas/`:

| Schema file (proposed) | Targets |
|------------------------|---------|
| `build-registry-pack.schema.json` | Root `registry-pack.yaml` — `module_index`, `compose_defaults` |
| `build-registry-app-type.schema.json` | `app-types/*.yaml` — composed_modules, build_phases, safety_constraints |
| `build-registry-module.schema.json` | Shared base for mechanics, validators, recovery, progress, learning hooks |
| `build-registry-component-contract.schema.json` | `component-contracts/*.yaml` — expected_props, binds_mechanics |

**Likely schema targets by directory:**

- `app-types/` — app type files
- `mechanics/` — mechanic modules
- `component-contracts/` — component contracts
- `validators/` — validator modules
- `recovery-playbooks/` — recovery modules
- `progress-labels/` — progress label modules
- `learning-hooks/` — learning hook modules
- `registry-pack.yaml` — pack index

Schemas should **compose** (app type extends module base) and stay **versioned** with `schema_version: "0.1"`. JSON Schema is a **Phase 2+** artifact — after the imperative checker proves which rules matter.

---

## 6. Checker behavior

**Proposed future command:**

```bash
python3 scripts/check_build_registry_references.py \
  --pack docs/build-kit-registry-v2/game-pack/registry-pack.yaml
```

**Optional future flags:**

| Flag | Purpose |
|------|---------|
| `--app-type game.card-deck-turn-based` | Scope compose/render budget check to one recipe |
| `--strict` | Treat warnings as errors (local dev only) |
| `--warn-only` | Default Phase 2 mode — never exit non-zero on warnings |
| `--json` | Machine-readable report for CI artifacts |
| `--check-render-budget` | Compose + measure render length per app type (or `--app-type`) |
| `--check-orphans` | Report YAML files not indexed in `registry-pack.yaml` |
| `--check-status` | Compare app types in pack vs [STATUS.md](STATUS.md) recipe table |
| `--check-intent` | Compare routed app types in STATUS vs `intent.py` (doc consistency only) |

**Initial mode:** **warning-only** locally unless `--strict` is passed explicitly. Reuse `load_registry_pack` / `validate_registry_pack` where possible — do not fork compose logic.

---

## 7. Warning vs blocking policy

| Phase | Deliverable | CI |
|-------|-------------|-----|
| **Phase 1 — docs proposal** | This document | None |
| **Phase 2 — local warning-only checker** | `check_build_registry_references.py`; human runs before landing recipes | None |
| **Phase 3 — CI non-blocking / reporting** | Upload JSON report or echo warnings (`continue-on-error: true`) | Optional later |
| **Phase 4 — CI blocking** | Promote only after low false-positive rate and one cleanup pass | Explicit PR required |

**Do not jump directly to blocking CI.** Existing `validate_game_pack_registry.py --check` may remain the compose gate; the reference checker adds **breadth**, not immediate merge blocking.

---

## 8. Suggested checks

| Check | Why it matters | Initial severity |
|-------|----------------|------------------|
| Registry reference exists | Indexed id must resolve to a YAML file | **Error** |
| Duplicate module IDs | Two files must not share `id:` | **Error** |
| ID / filename mismatch | Easier navigation and grep | **Warning** |
| Missing required fields | Compose/render assumes kind-specific fields | **Error** (core) / **Warning** (optional) |
| Invalid `applies_to` | Stale app type refs in mechanics/components | **Error** |
| Orphaned modules | File on disk not in index | **Warning** |
| Missing `non_template_statement` | Generative posture on app types | **Warning** |
| Render budget overflow | Truncation loses playbook content | **Error** (when `--check-render-budget`) |
| Render budget near-cap (~90%) | Headroom before truncation | **Warning** |
| Validator/recovery executable language | `runner` not `conceptual` or missing | **Warning** |
| App type not listed in STATUS docs | Doc drift | **Warning** (`--check-status`) |
| Routed recipe missing intent test | Routing untested | **Warning** (`--check-intent`) |
| Schema-only recipe accidentally routed | STATUS vs `intent.py` mismatch | **Warning** |
| Routed app type not in registry | `intent.py` references missing app type | **Error** (`--check-intent`) |

Severity defaults assume **Phase 2 warn-only** unless `--strict`.

---

## 9. Interaction with routing

- The checker **must not decide routing** — no prompt matching, no flag interpretation beyond consistency audits.
- It **may detect mismatches**, e.g.:
  - STATUS claims “Routed: Yes” but `intent.py` has no matcher
  - `intent.py` exports an app type id absent from `registry-pack.yaml`
  - Tests in `test_build_registry_intent.py` missing for a STATUS-listed routed recipe
- **Routing remains explicit** — implemented in `src/ham/build_registry/intent.py`, tested in `tests/test_build_registry_intent.py`, documented in [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md).
- **v2 remains opt-in** behind `HAM_BUILD_REGISTRY_V2_ENABLED`; checker does not enable v2 by default.

---

## 10. Interaction with outcome reports

- [Manual outcome reports](outcome-reports/OUTCOME_REPORT_INDEX.md) are **learning artifacts**, not telemetry.
- The checker **must not score outcome quality** or generated-build behavior.
- **Future optional check:** if [OUTCOME_REPORT_INDEX.md](outcome-reports/OUTCOME_REPORT_INDEX.md) links a report path, verify the file exists.
- Outcome reports **must not automatically mutate** recipes, routing, or schemas.

---

## 11. Risks

| Risk | Mitigation |
|------|------------|
| **Overbuilding tooling too early** | Phase 2 = one script, reuse existing loader/validate |
| **Schema rigidity slowing authoring** | Defer JSON Schema until checker rules stabilize |
| **False positives / noise** | Warn-only default; tune before CI |
| **Checker becomes hidden runtime dependency** | Keep script in `scripts/`; HAM runtime never imports it |
| **Conceptual vs executable validator confusion** | Explicit `runner: conceptual` warnings |
| **CI blocking too soon** | Phase 4 requires explicit promotion PR |
| **Drift toward templates** | Flag missing `non_template_statement`; no starter-file checks in v1 |

---

## 12. Recommendation

1. **Accept this proposal** as the design baseline (docs-only land).
2. **Next implementation** (if approved): small `scripts/check_build_registry_references.py` wrapping existing `load_registry_pack` / `validate_registry_pack` plus incremental checks.
3. **Start warning-only** — no CI, no exit 1 on warnings by default.
4. **Focus first on:** references, duplicate IDs, missing files, required fields, render budget.
5. **Defer JSON Schema files** until checker behavior is clear and false-positive rate is understood.
6. **Do not add CI enforcement** in the first implementation PR.

---

## 13. Non-goals

This proposal does **not** authorize:

- Implementation from this document alone
- CI workflow changes
- Runtime or API dependency on the checker
- Frontend / Builder Studio / scaffold behavior changes
- Auto-fix of registry YAML
- Recipe or routing mutation
- Production telemetry claims
- Hermes autonomous PRs
- Default v2 enablement

---

## 14. References

| Doc / path | Purpose |
|------------|---------|
| [STATUS.md](STATUS.md) | Live recipe/module/routing snapshot |
| [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md) | Recipe authoring rules and required fields |
| [ROUTING_STRATEGY.md](ROUTING_STRATEGY.md) | Routing approval policy |
| [OUTCOME_FACTS.md](OUTCOME_FACTS.md) | Future machine-readable outcomes (separate from checker) |
| [WAVE_3_CARD_DECK_CHECKPOINT.md](WAVE_3_CARD_DECK_CHECKPOINT.md) | Wave 3 completion; recommended reference checker |
| [outcome-reports/OUTCOME_REPORT_INDEX.md](outcome-reports/OUTCOME_REPORT_INDEX.md) | Manual outcome report index |
| [game-pack/registry-pack.yaml](game-pack/registry-pack.yaml) | Module index to validate |
| [scripts/validate_game_pack_registry.py](../../scripts/validate_game_pack_registry.py) | Current validate/compose/render CLI |
| [tests/test_build_registry.py](../../tests/test_build_registry.py) | Registry regression tests |
| [ADR-0016](../adr/0016-generative-build-kit-registry-v2.md) | Registry design |
| [ADR-0017](../adr/0017-build-registry-v2-opt-in-scaffold-wiring.md) | Opt-in scaffold wiring |
| [ADR-0018](../adr/0018-build-kit-evolution-loop-with-hermes.md) | Future Hermes critique loop |
