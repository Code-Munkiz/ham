# Build Registry v2 — Status & Handoff

Practical snapshot of where Build Kit Registry v2 stands. For authoring rules see [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md). For architecture see [ADR-0016](../adr/0016-generative-build-kit-registry-v2.md), [ADR-0017](../adr/0017-build-registry-v2-opt-in-scaffold-wiring.md), and [ADR-0018](../adr/0018-build-kit-evolution-loop-with-hermes.md).

---

## 1. Current status

- **Build Registry v2 exists and is tested** — loader, composer, renderer, opt-in scaffold wiring, and narrow prompt routing are in place.
- **Game Pack has three recipes** — `game.idle-incremental`, `game.trivia-timer`, and `game.branching-narrative` (51 indexed modules total).
- **Idle recipe is narrowly routable** behind `HAM_BUILD_REGISTRY_V2_ENABLED` when prompt intent clearly matches idle/incremental/clicker/tycoon patterns.
- **Trivia and branching narrative recipes are schema-only** — validated YAML that composes and renders; not wired to chat routing.
- **Default behavior remains v1** — when the flag is unset or false, Lane A uses existing Builder Kit JSON (`src/ham/data/builder_kits/`).
- **No templates or starter source files** — recipes are generative playbooks only; HAM does not clone checked-in starter trees per kit.

---

## 2. What exists

| Asset | Location |
|-------|----------|
| **ADRs** | [0016](../adr/0016-generative-build-kit-registry-v2.md) (registry design), [0017](../adr/0017-build-registry-v2-opt-in-scaffold-wiring.md) (opt-in scaffold wiring), [0018](../adr/0018-build-kit-evolution-loop-with-hermes.md) (future Hermes evolution loop) |
| **Authoring Guide** | [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md) |
| **Game Pack** | [game-pack/](game-pack/) — **3 recipes**, **51 modules** |
| **Outcome facts / evolution loop docs** | [OUTCOME_FACTS.md](OUTCOME_FACTS.md), [examples/outcome-facts/](examples/outcome-facts/), [examples/hermes-critique-prompt.md](examples/hermes-critique-prompt.md) |
| **Validation script** | `scripts/validate_game_pack_registry.py` |
| **Internal package** | `src/ham/build_registry/` (`loader`, `validate`, `compose`, `render`, `scaffold_context`, `intent`) |
| **Tests** | `tests/test_build_registry.py` (19 cases), `tests/test_build_registry_scaffold_context.py`, `tests/test_builder_llm_scaffold_registry_context.py`, `tests/test_builder_llm_scaffold_registry_manual_smoke.py`, `tests/test_build_registry_intent.py` |
| **CI** | `.github/workflows/ci.yml` — warning-only `pytest tests/test_build_registry.py` + idle app-type validation (`continue-on-error: true`) |

---

## 3. Recipes

| Recipe id | Status | Routed? | Route gate | Render length | Notes |
|-----------|--------|---------|------------|---------------|-------|
| `game.idle-incremental` | Validated | Yes (narrow) | `HAM_BUILD_REGISTRY_V2_ENABLED` + idle/clicker/tycoon prompt match | ~8.8k chars | Pilot recipe; v2 playbook context injected at scaffold when routing succeeds |
| `game.trivia-timer` | Validated | No | — (not routed) | ~9.6k chars | Schema-only; explicit routing approval required before wiring |
| `game.branching-narrative` | Validated | No | — (not routed) | ~10.3k chars | DOM-native branching story/state graph recipe; schema-only |

All three renders are under the 12k default budget.

---

## 4. Runtime behavior

- **v1 Builder Kits remain default** for all Lane A scaffolds unless v2 path is explicitly enabled.
- **Build Registry v2 affects scaffold context only** when **both** are true:
  1. `HAM_BUILD_REGISTRY_V2_ENABLED` is truthy
  2. Plan metadata includes `registry_v2_app_type` (set by routing or manual metadata)
- **Idle routing** (`src/ham/build_registry/intent.py`) adds `registry_v2_app_type: game.idle-incremental` only when the flag is on and the user prompt clearly matches idle/incremental/clicker/tycoon intent (with negative-pattern exclusions for trivia, SaaS, etc.).
- **Non-idle prompts remain v1** — SaaS, dashboard, generic, trivia, branching narrative, and ambiguous prompts do not get v2 metadata from routing today.
- **Bad v2 app types fall back to v1** — load/validate/compose/render failures silently use the app type’s `legacy_v1_fallback` kit (pilot: `generic`).

---

## 5. Validation commands

```bash
pytest tests/test_build_registry.py -q
```

```bash
pytest tests/test_build_registry.py \
       tests/test_build_registry_scaffold_context.py \
       tests/test_builder_llm_scaffold_registry_context.py \
       tests/test_builder_llm_scaffold_registry_manual_smoke.py \
       tests/test_build_registry_intent.py -q
```

```bash
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/game-pack \
  --app-type game.idle-incremental \
  --check
```

```bash
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/game-pack \
  --app-type game.trivia-timer \
  --check
```

```bash
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/game-pack \
  --app-type game.branching-narrative \
  --check
```

Optional render sample:

```bash
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/game-pack \
  --app-type game.idle-incremental \
  --render-sample /dev/stdout
```

---

## 6. Safety boundaries

- **No template cloning** — recipes guide generation; no checked-in starter file trees.
- **No starter source trees** per app type.
- **No autonomous recipe mutation** — YAML changes are normal human-reviewed git commits only ([ADR-0018](../adr/0018-build-kit-evolution-loop-with-hermes.md)).
- **No auto-merge** of recipe or routing changes.
- **No default v2 routing** — flag off by default; trivia and branching narrative not routed.
- **No user-facing kit picker** for registry v2 app types.
- **No validator/recovery execution yet** — validator and recovery modules are conceptual (`runner: conceptual`); not executed at build time.
- **Hermes may critique/propose future changes only** through reviewed patches — no runtime recipe editing today.

---

## 7. How to add a recipe

Follow [AUTHORING_GUIDE.md](AUTHORING_GUIDE.md). Summary:

1. Create an app type YAML under `game-pack/app-types/`.
2. Reuse or add mechanics, component contracts, validators, recovery, progress, and learning modules as needed.
3. Index every YAML file in `game-pack/registry-pack.yaml`.
4. Add or extend tests in `tests/test_build_registry.py` (and routing tests if routing is later approved).
5. Validate **all affected app types** after pack-wide edits.
6. **Do not add routing** unless explicitly requested and approved (separate from schema work).

---

## 8. How routing works today

- **Module:** `src/ham/build_registry/intent.py`
- **`select_registry_v2_app_type_for_prompt(prompt)`** — pure regex; returns `game.idle-incremental` or `None`.
- **`enrich_plan_metadata_with_registry_v2(metadata, prompt, env=...)`** — copies metadata and sets `registry_v2_app_type` only when flag + intent match.
- **Currently supports one routed app type:** `game.idle-incremental` only.
- **`game.trivia-timer` and `game.branching-narrative` are schema-only** — validate and compose in tests/CLI; no intent-router wiring yet.
- **Routing is narrow and flag-gated** — negative patterns block trivia, SaaS, dashboard, etc.
- **Adding a recipe does not automatically route it** — new app types require explicit intent logic and approval per ADR-0017 / Authoring Guide routing policy.

Wiring entry point: `src/ham/builder_chat_scaffold.py` calls `enrich_plan_metadata_with_registry_v2()` before LLM scaffold.

---

## 9. Next recommended steps

Outcome facts format, manual example reports, and Hermes critique prompt are **already documented** ([OUTCOME_FACTS.md](OUTCOME_FACTS.md), [examples/](examples/)).

Possible next steps:

1. **Add flag-gated routing** for `game.trivia-timer` or `game.branching-narrative` only after explicit approval (do not bundle with schema-only landings).
2. **Add `game.memory-match` or `game.word-daily`** as recipe #4 following the Authoring Guide.
3. **Consider making CI registry validation blocking** once v2 usage increases (today warning-only for idle app type + registry tests).
4. **Add manual outcome report examples** for trivia and branching narrative (idle success example exists under [examples/outcome-facts/](examples/outcome-facts/)).
5. **Later:** outcome facts → Hermes critique report → proposed patch workflow (no auto-apply).

---

## 10. Recent commits

Build Registry v2–related commits on `main` (newest first):

| Commit | Subject |
|--------|---------|
| `d800c597` | docs(builder): add branching narrative game recipe |
| `23b76f2e` | docs(builder): add hermes build kit critique prompt |
| `a7c20d88` | docs(builder): add example build outcome facts |
| `082fdfb7` | docs(builder): define build registry outcome facts |
| `548887e7` | docs(builder): add build registry status handoff |
| `aab6e78b` | docs(builder): define hermes build kit evolution loop |
| `fa898adc` | docs(builder): add build kit authoring guide |
| `0dae7995` | docs(builder): add trivia game pack recipe |
| `ce2e6689` | feat(builder): route idle game prompts to registry v2 |
| `37104a45` | test(builder): add registry scaffold opt-in smoke coverage |
| `213771f4` | feat(builder): wire opt-in build registry scaffold context |
| `7bdf1406` | feat(builder): add unwired registry scaffold context resolver |
| `e9c3c00e` | docs(builder): design opt-in build registry wiring |
| `2a456666` | ci(builder): validate game pack registry pilot |
| `97493d70` | feat(builder): add unwired build registry loader |
| `b101b1ad` | tools(builder): validate game pack registry pilot |
| `09591b42` | docs(builder): tighten game pack pilot schema |
| `4fea59f8` | docs(builder): add game pack registry v2 pilot |
| `b0ab86f4` | docs(builder): clarify generative build kit registry direction |

---

## 11. Known non-goals / deferrals

- No recipe marketplace
- No UI kit picker for registry v2
- No default Build Registry v2 enablement (`HAM_BUILD_REGISTRY_V2_ENABLED` stays off unless operator sets it)
- No auto-generated PRs from Hermes yet
- No executable validator runners yet
- No recovery runner yet
- No promotion of registry YAML from `docs/build-kit-registry-v2/` to `src/ham/data/` yet
- No telemetry / outcome-facts capture implementation yet (ADR-0018 future phases)
