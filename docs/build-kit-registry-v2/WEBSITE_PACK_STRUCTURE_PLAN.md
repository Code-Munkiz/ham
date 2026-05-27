# Website Pack Structure Plan

> **Structure plan only · Not recipe approval · Not routing approval · Not directory implementation**

Implementation plan for a **separate Build Registry v2 `website-pack/`** alongside the existing **`game-pack/`**. This document defines proposed folder layout, naming conventions, validation posture, and sequencing for the first website recipe **`site.landing-page-core`**. It does **not** create directories, YAML modules, routing, templates, or runtime changes.

**Plan date:** 2026-05-27 (UTC)  
**Baseline:** `origin/main` at `bff12d57` — sixteen game recipes / 376 modules (Game Pack); website direction, design doctrine, and landing-page readiness reviews landed; **no website-pack yet**.

For readiness gate see [LANDING_PAGE_CORE_READINESS_REVIEW.md](./LANDING_PAGE_CORE_READINESS_REVIEW.md). For design doctrine see [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](./WEBSITE_DESIGN_QUALITY_PRINCIPLES.md).

---

## 1. Executive summary

**Use a separate `website-pack/`** under `docs/build-kit-registry-v2/` — do **not** mix website/design-system modules into `game-pack/`.

**This is a plan only.** No files or directories are created by this document.

**First candidate recipe:** **`site.landing-page-core`** — one-page static marketing/landing playbook (hero → sections → CTA; no backend).

**Sequence after this plan:** commit plan → create pack skeleton + schema-only first recipe → focused tests → validate/reference-check → route only after approval → generated gate review.

---

## 2. Proposed folder structure

Target root: **`docs/build-kit-registry-v2/website-pack/`**

```text
docs/build-kit-registry-v2/website-pack/
├── registry-pack.yaml          # pack.site root manifest (module_index, compose_defaults, render_sections)
├── README.md                   # pack purpose, non-template statement, conventions pointer
├── CONVENTIONS.md              # optional; mirror game-pack CONVENTIONS if needed at skeleton land
├── app-types/                  # site.landing-page-core.yaml, future site.* recipes
├── sections/                   # section.* modules (hero, value prop, features, proof, CTA, FAQ)
├── components/                 # component.* reusable blocks (hero-block, feature-grid, cta-band, …)
├── stack-kits/                 # stack.dom-marketing-minimal (shared DOM/Tailwind baseline)
├── validators/                 # validator.* (conceptual runners initially)
├── recovery/                   # recovery.* playbooks (generic hero, weak CTA, mobile ignored, …)
├── progress-labels/            # progress.site-landing-page-core (phase copy for build_phases)
└── learning-hooks/             # learning.site-landing-page-core (outcome-facts hooks, optional)
```

**Not in v1 skeleton (defer):**

- `templates/` or `starters/` — forbidden by registry policy
- `assets/` — no checked-in design assets in pack
- Multi-recipe lanes until landing-core proves the pattern

### Mapping note (implementation follow-up)

Today’s loader and reference checker (`src/ham/build_registry/models.py`, `scripts/check_build_registry_references.py`) index **`module_index`** keys:

`app_types`, `stack_kits`, `mechanics`, `component_contracts`, `validators`, `recovery_playbooks`, `progress_labels`, `learning_hooks`

**At skeleton land**, choose one of:

| Approach | Detail |
|----------|--------|
| **A. Semantic folders, legacy index keys** | Store YAML under `sections/` but list ids under `module_index.mechanics` (or `component_contracts`) until loader gains `sections` key |
| **B. Extend loader/checker** | Add `sections` to `MODULE_INDEX_KEYS` + `INDEX_DIRECTORY` in a small follow-up PR before first YAML lands |

**This plan recommends documenting Approach B as the target** but allows Approach A for the **first schema-only land** if minimal loader diff is deferred — **do not block skeleton on checker extension**; run `validate_game_pack_registry.py --pack-root website-pack` once pack exists.

---

## 3. Naming conventions

| Prefix / kind | Use | Example ids |
|---------------|-----|-------------|
| **`site.*`** | App types (recipes) | `site.landing-page-core` |
| **`section.*`** | Page section playbooks | `section.landing-hero`, `section.landing-value-proposition`, `section.landing-feature-block` |
| **`component.*`** | Reusable UI blocks | `component.hero-block`, `component.feature-grid`, `component.testimonial-strip`, `component.cta-band`, `component.faq-list` |
| **`stack.*`** | Shared stack kit | `stack.dom-marketing-minimal` |
| **`validator.*`** | Conceptual quality checks | `validator.landing-section-presence`, `validator.cta-clarity`, `validator.no-lorem-ipsum` |
| **`recovery.*`** | Recovery playbooks | `recovery.generic-hero-slop`, `recovery.weak-cta-hierarchy`, `recovery.mobile-layout-ignored` |
| **`progress.*`** | Build phase operator copy | `progress.site-landing-page-core` |
| **`learning.*`** | Outcome / critique hooks | `learning.site-landing-page-core` |

**Pack manifest id:** `pack.site` (parallel to `pack.game`).

**File naming:**

- App types: `app-types/site.landing-page-core.yaml` (full id in filename — matches game-pack `app-types/game.*.yaml` pattern where checker uses `use_full_id: true`)
- Other modules: slug filename from id suffix — e.g. `sections/landing-hero.yaml` for `section.landing-hero`

**Avoid:** `game.*` prefixes, gameplay mechanic names (`mechanic.score`), and generic `web.*` unless an ADR renames the lane.

---

## 4. First recipe target

**`site.landing-page-core`**

| Dimension | Scope |
|-----------|--------|
| **Surface** | One-page static marketing/landing page |
| **Sections** | Hero, value proposition, 2–4 feature/value blocks, social proof (optional), CTA, FAQ or final conversion (optional) |
| **Interaction** | Static links/buttons — no live form POST, no auth |
| **Backend** | **None** |
| **Forms** | **No live handling** — placeholder buttons/links only |
| **Payments / CMS** | **None** |
| **Templates** | **None** — generative playbook only; `non_template_statement` on pack and app type |
| **legacy_v1_fallback** | `generic` (mirror game app types) |

See [LANDING_PAGE_CORE_READINESS_REVIEW.md](./LANDING_PAGE_CORE_READINESS_REVIEW.md) §3, §10, §12 for module themes and gate expectations.

---

## 5. Relationship to game-pack

| Topic | Posture |
|-------|---------|
| **Separation** | Website design modules must not live under `docs/build-kit-registry-v2/game-pack/` |
| **Why** | Avoid mixing gameplay mechanics (grid ticks, deck state) with section rhythm, typography, and conversion flow |
| **Reuse patterns** | Mirror **shape** of game-pack: `registry-pack.yaml`, app-type compose graph, validators/recovery as conceptual modules, progress labels tied to `build_phases` |
| **Reuse code paths** | Same unwired loader/composer/renderer (`src/ham/build_registry/*`) with **`--pack-root website-pack`** when wired; today game-pack is default in tests and scaffold context |
| **Do not restructure game-pack** | No moves, renames, or index changes to existing 376 modules |
| **Routing namespace** | `site.*` vs `game.*` — future intent router must keep lanes disjoint |

**Game Pack remains** the DOM-native **game** lane. **Website Pack** is a new **marketing/design-system** lane.

---

## 6. Validator / reference-check implications

| Tool | Current state | Website-pack implication |
|------|---------------|------------------------|
| **`scripts/validate_game_pack_registry.py`** | `--pack-root` accepts any pack dir with `registry-pack.yaml` | **Reuse as-is** for first website-pack validation after skeleton (rename to neutral script name is optional later) |
| **`scripts/check_build_registry_references.py`** | Default `--pack` points at game-pack; `INDEX_DIRECTORY` maps index keys → folders | **Not extended in this plan** — run against website-pack manually once skeleton exists; extend `sections` mapping in implementation PR if needed |
| **`tests/test_build_registry.py`** | `GAME_PACK_ROOT` constant | Add **`WEBSITE_PACK_ROOT`** + focused cases in a **later PR** after skeleton (not this plan) |
| **CI** | Game pack validation warning-only on idle app type | **No CI changes in this plan** — website validation stays local until pack lands |
| **Validators in YAML** | `runner: conceptual` | Same — generated gate + doctrine precede executable validators |

**First implementation tests (after skeleton, not now):**

- Load `website-pack/registry-pack.yaml`
- Compose/render `site.landing-page-core` under 12k cap
- Orphan + duplicate id checks via reference checker when pack path supported

Reference checker remains **game-pack-oriented** until a follow-up adds `--pack-root` parity or second default pack entry — **document only here**.

---

## 7. Routing posture

**No routing from this plan.**

Future **`site.landing-page-core`** routing requires:

- Separate approval per [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md)
- Conservative combined signals (hero + features/value + CTA) — see [LANDING_PAGE_CORE_READINESS_REVIEW.md](./LANDING_PAGE_CORE_READINESS_REVIEW.md) §7–§9
- Explicit negatives for dashboard, ecommerce, CMS, game, and generic “website/homepage/page” alone
- **`HAM_BUILD_REGISTRY_V2_ENABLED`** remains off by default
- **`src/ham/build_registry/intent.py`** changes in a **dedicated routing PR** with `tests/test_build_registry_intent.py` coverage

**Preserve all sixteen game routes** — website matchers must not steal game or app-builder prompts.

---

## 8. Render budget posture

| Rule | Value |
|------|--------|
| **Hard cap** | **12,000 chars** (`DEFAULT_RENDER_CHAR_BUDGET`) — unchanged unless ADR revises |
| **Target** | **Under 11,400 chars** (90% near-budget threshold used by reference checker) |
| **Compression** | Short module `guidance` bullets; avoid pasting full [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](./WEBSITE_DESIGN_QUALITY_PRINCIPLES.md) into YAML |
| **Compose discipline** | Landing-core should compose **fewer modules than city-builder** — prefer 1 app type + stack + 6–10 section/component refs + 2–4 validators |
| **Trim trigger** | If compose/render exceeds 90%, trim recovery/progress copy before dropping section modules |

Game-pack near-budget trims ([STATUS.md](./STATUS.md)) are the model — core mechanics (here: section requirements) preserved, prose tightened.

---

## 9. Recommended next steps

1. **Commit this plan** (`WEBSITE_PACK_STRUCTURE_PLAN.md`).
2. **Create `website-pack/` skeleton** — `registry-pack.yaml`, `README.md`, empty index sections, **`site.landing-page-core` schema-only** (no routing).
3. **Add focused registry tests** — load/compose/render for `site.landing-page-core`; orphan check when checker supports pack path.
4. **Validate / reference-check** — `validate_game_pack_registry.py --pack-root docs/build-kit-registry-v2/website-pack --app-type site.landing-page-core --check`; reference checker when extended or with manual orphan review.
5. **Do not route** until explicit human approval + intent tests.
6. **Generated gate review** — `/tmp/` scaffold under canonical landing prompt; outcome report; optional future `scaffold_quality.py` website family.

**Do not** combine steps 2 and 5 in one PR.

---

## 10. Non-goals

This plan does **not** authorize or imply:

- Creating `website-pack/` directories or YAML in this document alone
- Landing **`site.landing-page-core`** recipe content beyond future schema work
- Routing or `intent.py` changes
- Runtime, API, frontend, or Builder Studio changes
- Scaffold quality guard extensions
- Templates or starter source files
- CI workflow changes
- Game-pack restructure or module moves
- Default v2 enablement
- Reference checker / loader code changes (deferred to skeleton PR)

---

## 11. References

| Document / asset | Relevance |
|------------------|-----------|
| [WEBSITE_DESIGN_SYSTEM_DIRECTION.md](./WEBSITE_DESIGN_SYSTEM_DIRECTION.md) | Workstream direction; separate pack recommendation |
| [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](./WEBSITE_DESIGN_QUALITY_PRINCIPLES.md) | Design doctrine; gate criteria |
| [LANDING_PAGE_CORE_READINESS_REVIEW.md](./LANDING_PAGE_CORE_READINESS_REVIEW.md) | Ambiguity gate; first recipe scope; module themes |
| [DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md](./DOM_NATIVE_GAME_KIT_COMPLETION_CHECKPOINT.md) | Game-kit closeout baseline |
| [STATUS.md](./STATUS.md) | Live Game Pack status, render budgets, validation commands |
| [game-pack/registry-pack.yaml](./game-pack/registry-pack.yaml) | Manifest pattern to mirror (`pack.game` → `pack.site`) |

**Related code (read-only context — not modified by this plan):**

- `scripts/validate_game_pack_registry.py` — pack-root validation CLI
- `scripts/check_build_registry_references.py` — reference + render-budget checker (game-pack default)
- `tests/test_build_registry.py` — loader/compose/render tests (game-pack rooted)
- `src/ham/build_registry/` — unwired pilot loader/composer/renderer
