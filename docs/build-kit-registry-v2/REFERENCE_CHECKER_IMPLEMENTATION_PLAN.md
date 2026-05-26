# Build Registry v2 Reference Checker Implementation Plan

Implementation plan for a **lightweight local reference checker** for the Game Pack registry. Wave 3 is closed; this document defines **how to implement** the checker next — it does **not** implement tooling, change CI, alter runtime behavior, or modify registry YAML.

**Context:** `origin/main` at `25240bbb` — fourteen recipes, 323 indexed modules, all routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`; v1 default when flag off. See [WAVE_3_COMPLETION_CHECKPOINT.md](./WAVE_3_COMPLETION_CHECKPOINT.md).

**Design baseline:** [REGISTRY_REFERENCE_CHECKER_PROPOSAL.md](./REGISTRY_REFERENCE_CHECKER_PROPOSAL.md)

---

## 1. Executive summary

**Wave 3 is complete.** Build Registry v2 now has **14 recipes** and **323 modules**. Existing validation (`scripts/validate_game_pack_registry.py`, `tests/test_build_registry.py`) proves load/compose/render works, but **manual registry/index maintenance is now a real drift risk** at this scale.

The next step should be a **lightweight local reference checker** — boring consistency checks for references, duplicates, orphans, and render-budget headroom — before adding more recipes or Wave 4 strategy/sim lanes.

**This plan does not implement the checker or change CI.** Initial implementation should be **local and warning/report oriented**: humans run it before landing registry edits; hard errors exit nonzero locally; warnings do not block merges until a later CI phase.

---

## 2. Why this is next

| Pressure | Why it matters at 14 recipes / 323 modules |
|----------|---------------------------------------------|
| **Manual `registry-pack.yaml` indexing** | Every recipe adds ~20–30 module entries; omission or typo breaks compose only when someone runs validation |
| **Large module surface** | Stale references, duplicate IDs, and filename/id mismatches compound with each Wave |
| **Recipe/module ID drift** | `mechanic.deck-draw-pile` vs `mechanic.deck_draw_pile` fails at compose time, not edit time |
| **Render budgets** | Recipes target ~12k chars; near-cap truncation hides content loss |
| **Routed recipes need registry consistency** | `intent.py`, STATUS, tests, and YAML must agree on which app types exist and are routed |
| **Outcome/report references can drift** | [OUTCOME_REPORT_INDEX.md](./outcome-reports/OUTCOME_REPORT_INDEX.md) links can go stale |
| **More recipes without tooling** | Wave 4+ increases maintenance risk unless reference checks exist first |

The registry should not become a **YAML petting zoo with opinions**. The checker enforces **boring consistency**, not product behavior or LLM output quality.

---

## 3. Implementation scope

### In scope for first implementation

| Check | Purpose |
|-------|---------|
| **Registry-pack referenced files exist** | Every id in `module_index` resolves to an on-disk YAML file |
| **Duplicate module IDs** | No two loaded modules share the same `id:` |
| **App type IDs match filenames** | e.g. `game.deck-builder-lite.yaml` → `id: game.deck-builder-lite` |
| **Module IDs match filenames** | Where convention applies (mechanics, validators, etc.) |
| **`applies_to` app types exist** | Mechanics/components reference valid app type ids |
| **App types reference existing modules** | `composed_modules` ids exist in the pack |
| **Composed module references exist** | Compose graph references resolve |
| **Render budget check per app type** | Reuse compose + render; error on overflow |
| **Near-budget warning** | Warn when render length ≥ ~90% of default 12k cap |
| **Orphan module warning** | YAML on disk under game-pack folders not listed in index |
| **Non-template statement presence** | Warn when convention requires `non_template_statement` (app types, pack root) |
| **Routed app type exists in registry** | Cross-check STATUS / intent-listed routed ids against pack index |
| **Schema-only app type accidentally routed** | Warn if detectable doc/status vs intent mismatch |
| **Outcome report index links exist** | If easy: verify paths linked from `OUTCOME_REPORT_INDEX.md` exist |

### Out of scope

- Runtime execution, API, frontend, Builder Studio
- LLM output quality or scaffold repair behavior
- Generated app validation
- Production telemetry or outcome-facts ingestion
- Auto-fixing registry YAML
- CI blocking (first implementation)
- Hermes autonomous edits
- Routing decisions (checker may **detect** mismatches; it does not change `intent.py`)

---

## 4. Proposed script

**Future script path:**

```
scripts/check_build_registry_references.py
```

**Command shape:**

```bash
python3 scripts/check_build_registry_references.py \
  --pack docs/build-kit-registry-v2/game-pack/registry-pack.yaml
```

The script should derive `--pack-root` as the parent directory of `registry-pack.yaml` (aligning with existing `load_registry_pack(pack_root)` in `src/ham/build_registry/`).

**Optional flags:**

| Flag | Purpose |
|------|---------|
| `--app-type game.deck-builder-lite` | Scope compose/render budget to one recipe |
| `--strict` | Treat warnings as errors (local dev only) |
| `--warn-only` | Default mode — exit 0 on warnings, nonzero only on hard errors |
| `--json` | Machine-readable report |
| `--check-orphans` | Report YAML files not indexed in `registry-pack.yaml` |
| `--check-render-budget` | Compose + measure render length (all app types or `--app-type`) |

**Default behavior:**

- **Warning/report mode first** — print issues grouped by severity; exit nonzero only for hard errors unless `--strict`
- **Strict mode later** — opt-in for local pre-land discipline
- **CI unchanged in first implementation** — no workflow edits in the first PR

**Reuse existing logic:** delegate to `load_registry_pack`, `validate_registry_pack`, `compose_build_recipe`, and `render_playbook_context` from `src/ham/build_registry/` where possible. Do not fork compose/render logic.

---

## 5. Suggested data model

Keep the checker **simple and report-oriented** — no database, no runtime registration.

### `CheckIssue`

| Field | Type | Description |
|-------|------|-------------|
| `code` | str | Stable machine id, e.g. `missing_referenced_file`, `duplicate_module_id` |
| `severity` | str | `info` \| `warning` \| `error` |
| `path` | str \| None | File or logical path related to the issue |
| `message` | str | Human-readable explanation |
| `suggestion` | str \| None | Optional fix hint |

### `CheckResult`

| Field | Type | Description |
|-------|------|-------------|
| `issues` | list[CheckIssue] | All findings |
| `warnings` | list[CheckIssue] | Filtered `severity == warning` |
| `errors` | list[CheckIssue] | Filtered `severity == error` |
| `summary_counts` | dict | e.g. `{ "error": 0, "warning": 3, "info": 1 }` |

### Severity defaults (first implementation)

| Finding | Severity |
|---------|----------|
| Missing referenced file | **error** |
| Duplicate IDs | **error** |
| Invalid app type / compose reference | **error** |
| Render over budget | **error** |
| Near budget (~90%) | **warning** |
| Orphan modules | **warning** |
| Missing `non_template_statement` | **warning** |
| ID/filename mismatch | **warning** |
| Docs/STATUS mismatch | **warning** |
| Outcome report link missing | **warning** |

---

## 6. First implementation checklist

Implement in this order:

1. **Load `registry-pack.yaml`** — parse index lists (`app_types`, `mechanics`, `component-contracts`, etc.).
2. **Resolve paths relative to pack root** — parent of `registry-pack.yaml`.
3. **Verify referenced files exist** — map each indexed id to expected YAML path per existing loader conventions.
4. **Load YAML files safely** — reuse `load_registry_pack` or shared loader helpers.
5. **Collect IDs and detect duplicates** — across all loaded modules.
6. **Validate app type files** — required fields, `composed_modules`, `non_template_statement`.
7. **Validate module files** — kind-specific required fields per [AUTHORING_GUIDE.md](./AUTHORING_GUIDE.md).
8. **Validate `applies_to`** — referenced app type ids exist in index.
9. **Validate compose references** — `compose_build_recipe` succeeds for each app type (or `--app-type` scope).
10. **Run render budget check** — reuse `render_playbook_context`; compare length to 12_000 default and ~10_800 near-cap threshold.
11. **Report orphan files** — scan `app-types/`, `mechanics/`, etc. for YAML not in index (when `--check-orphans`).
12. **Print summary** — human-readable grouped report; optional `--json`.
13. **Exit nonzero only for hard errors** in default local mode (`--warn-only`).
14. **Leave CI unchanged** — document command in STATUS / this plan; no `.github/workflows` edits yet.

---

## 7. Test plan

**New test module (recommended):**

```
tests/test_build_registry_reference_checker.py
```

| Test case | Approach |
|-----------|----------|
| Valid current registry has no hard errors | Run checker against real `game-pack/`; assert `errors == []` |
| Missing referenced module detected | `tmp_path` fixture with broken index entry |
| Duplicate IDs detected | Fixture with two files sharing `id:` |
| Invalid `applies_to` detected | Fixture referencing nonexistent app type |
| Missing composed module detected | Fixture with stale `composed_modules` entry |
| Render over budget detected | Fixture or mocked render length above cap |
| Orphan warning detected | Fixture with extra YAML file not in index |
| JSON output shape | If `--json` implemented, assert schema keys |
| Strict vs warn-only behavior | Same fixture; strict exits 1 on warnings, warn-only exits 0 |

**Test principles:**

- Use **temp fixtures** where possible — do not mutate real registry files.
- Keep tests **fast and deterministic** — no live LLM, no network.
- Current registry green path should stay green after checker lands.

---

## 8. Relationship to existing validator

| Tool | Role today | After checker lands |
|------|------------|---------------------|
| **`scripts/validate_game_pack_registry.py`** | Load pack, `validate_registry_pack`, optional single `--app-type` compose/render; `--check` exits 1 on failure | **Keep** — compose/render smoke for one app type |
| **`tests/test_build_registry.py`** | Per-recipe compose/render/budget regression (323 modules, 14 recipes) | **Keep** — pytest guardrail |
| **`check_build_registry_references.py` (new)** | Pack-wide reference audit, orphans, duplicates, doc drift warnings | **Complement** — breadth and drift, not replacement |

The new checker should **not replace** `validate_game_pack_registry.py` immediately. It focuses on **references, drift, orphans, and report quality** across the full index. Future consolidation can happen after behavior stabilizes and false-positive rate is understood.

**Note:** Existing validator uses `--pack-root` (directory); new checker uses `--pack` (path to `registry-pack.yaml`) but resolves the same pack root internally.

---

## 9. CI strategy

| Phase | Deliverable | CI |
|-------|-------------|-----|
| **Phase 1** | Local script only (`check_build_registry_references.py`) | None |
| **Phase 2** | Document command in STATUS / authoring workflow | None |
| **Phase 3** | Optional non-blocking CI step (`continue-on-error: true`); JSON artifact | Explicit PR |
| **Phase 4** | Blocking CI only after low false-positive rate + cleanup pass | Explicit PR |

**Do not jump directly to blocking CI.** Existing `validate_game_pack_registry.py --check` and `tests/test_build_registry.py` remain the compose gate; the reference checker adds **breadth**, not immediate merge blocking.

---

## 10. Risks

| Risk | Mitigation |
|------|------------|
| **Overbuilding tooling** | One script; reuse loader/compose/render; defer JSON Schema |
| **False positives** | Warn-only default; tune severity before CI |
| **Slowing recipe authoring** | Fast local command; clear suggestions on issues |
| **Schema rigidity too early** | Imperative checker first; JSON Schema Phase 2+ |
| **Checker becomes hidden runtime dependency** | Keep in `scripts/` only; HAM runtime never imports it |
| **Conceptual vs executable validator confusion** | Warn on missing `runner: conceptual` for validator/recovery modules |
| **CI noise if introduced too early** | Phase 3+ only; non-blocking first |

---

## 11. Recommendation

1. **Implement the checker next** as a small local script — not another recipe.
2. **Start with:** references, duplicates, file existence, `applies_to`, compose references, render budget.
3. **Add as warnings:** orphans, missing `non_template_statement`, STATUS/doc mismatches, outcome report link checks.
4. **Do not add CI** in the first implementation PR.
5. **Do not add more recipes** until the checker exists and passes cleanly on the current 14-recipe / 323-module registry.
6. **Defer JSON Schema files** until checker rules stabilize ([REGISTRY_REFERENCE_CHECKER_PROPOSAL.md](./REGISTRY_REFERENCE_CHECKER_PROPOSAL.md) §5).

---

## 12. Non-goals

This plan does **not** authorize:

- Implementation from this document alone
- CI workflow changes
- Runtime or API dependency on the checker
- Frontend / Builder Studio / scaffold behavior changes
- Auto-fix of registry YAML
- Recipe or routing mutation
- Production telemetry claims
- Generated app validation
- Autonomous Hermes PRs
- Default v2 enablement

---

## 13. References

| Doc / path | Purpose |
|------------|---------|
| [WAVE_3_COMPLETION_CHECKPOINT.md](./WAVE_3_COMPLETION_CHECKPOINT.md) | Wave 3 closeout; recommends registry hardening next |
| [REGISTRY_REFERENCE_CHECKER_PROPOSAL.md](./REGISTRY_REFERENCE_CHECKER_PROPOSAL.md) | Design proposal and phased rollout |
| [STATUS.md](./STATUS.md) | Live recipe/module/routing snapshot |
| [AUTHORING_GUIDE.md](./AUTHORING_GUIDE.md) | Required fields and authoring conventions |
| [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md) | Routing approval policy (checker does not decide routing) |
| [game-pack/registry-pack.yaml](./game-pack/registry-pack.yaml) | Module index to validate |
| [scripts/validate_game_pack_registry.py](../../scripts/validate_game_pack_registry.py) | Current validate/compose/render CLI |
| [tests/test_build_registry.py](../../tests/test_build_registry.py) | Registry regression tests (323 modules) |
