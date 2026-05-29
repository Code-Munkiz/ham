# SaaS Dashboard Core Pack Placement Decision

> **Placement decision only · Not recipe approval · Not routing approval · Not schema · Not implementation · Not runtime enablement**

Pack placement decision for the next dashboard sibling lane **`app.saas-dashboard-core`**, to be resolved **before** any schema authoring. It compares keeping the lane in the existing `website-pack/` (`pack.site`) versus creating a future `app-pack/`, grounded in the actual loader, validator, reference checker, and scaffold-context resolution code. It builds on [SAAS_DASHBOARD_CORE_RESEARCH.md](./SAAS_DASHBOARD_CORE_RESEARCH.md) and [SAAS_DASHBOARD_CORE_READINESS_REVIEW.md](./SAAS_DASHBOARD_CORE_READINESS_REVIEW.md).

**Decision date:** 2026-05-29 (UTC)
**Latest pushed commit:** `14a6ddf8` — `docs(builder): add saas dashboard core readiness review`
**Baseline:** `site.landing-page-core` and `site.dashboard-ui-core` complete and routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`; SaaS dashboard research + readiness complete; v1 default; v2 opt-in; build-kit internals invisible.

**This document adds no recipe, routing, schema, runtime, or tests.** It is a placement decision only.

---

## 1. Executive summary

- A placement decision is **needed before schema authoring** so the recipe lands in the right pack with the right tooling support.
- This doc compares **`website-pack/` (`pack.site`)** vs a **future `app-pack/`**, grounded in the real validator, reference checker, and scaffold-context code.
- **Finding:** schema authoring + validation + reference checking support an `app.*` recipe inside `pack.site` **with no runtime changes**. The **only** gap is `resolve_pack_root`, which today maps only `site.*` → website-pack — relevant at the **later routing step**, not at schema authoring.
- **This doc adds no recipe, routing, schema, runtime, or tests.**

---

## 2. Current baseline

- **Website pack** has `site.landing-page-core` and `site.dashboard-ui-core` (59 modules under `pack.site`).
- **`pack.site` validates and reference-checks** — `scripts/validate_game_pack_registry.py` and `scripts/check_build_registry_references.py` both support website-pack.
- **SaaS dashboard research + readiness complete** — `13c4dfc5`, `14a6ddf8`.
- **v1 default preserved** when the flag is off or unset.
- **v2 opt-in** — `HAM_BUILD_REGISTRY_V2_ENABLED` off by default.
- **No generated output committed** — gate artifacts live under `/tmp/` only.

---

## 3. Placement options

| Option | Description | Pros | Risks | Required changes |
|--------|-------------|------|-------|------------------|
| **A. Add `app.saas-dashboard-core` to existing `website-pack/`** | Author the recipe + modules under `pack.site` | No new pack scaffolding; reuses proven validator/checker; smallest step; `pack.site` already claims "app-surface" scope | Mild naming tension (`pack.site` = "Website Pack" hosting an `app.*` id); `resolve_pack_root` needs a small change before routing | **Schema/validate/check: none.** Routing later: extend `resolve_pack_root` to map `app.` prefix (or use metadata `registry_v2_pack_root` override) |
| **B. Create a new `app-pack/`** | Stand up `pack.app` with its own folders | Clean semantic home for app-surface lanes; no site-pack naming tension | New pack id must be added to `SUPPORTED_PACK_IDS`; new index-directory mapping in checker; more scaffolding for a single lane; premature with one lane | Add `pack.app` to `validate.SUPPORTED_PACK_IDS`; add `APP_PACK_INDEX_DIRECTORY` + `index_directory_for_pack_id` branch; `resolve_pack_root` mapping; new registry-pack.yaml + folders |
| **C. Rename/reframe lane as `site.saas-dashboard-core`** | Keep `site.` prefix so existing tooling routes it unchanged | Zero runtime changes (incl. `resolve_pack_root`); fits existing site-pack conventions exactly | Misrepresents an app-like surface as a "site"; weakens the `app.*` boundary that helps prevent admin/CRUD drift | None (works with current tooling as-is) |
| **D. Pause schema until app-pack architecture is ready** | Defer authoring until a deliberate `app-pack` design exists | Avoids forcing app-surface lanes into site pack | Stalls a ready, bounded lane; over-engineers for one recipe | Future `app-pack` design + scaffolding |

---

## 4. Compatibility assessment

Grounded in the current code:

- **App type ID prefix compatibility.** The validator (`src/ham/build_registry/validate.py`) keys on the **pack id** (`SUPPORTED_PACK_IDS = {"pack.game", "pack.site"}`) and module **`kind`** (`app_type`, `validator`, …). It does **not** enforce or branch on the recipe-id prefix. An `app.saas-dashboard-core` module with `kind: app_type` validates cleanly inside `pack.site`.
- **Loader / checker assumptions.** The reference checker (`scripts/check_build_registry_references.py`) already recognizes the `app.` prefix: `APP_TYPE_REF = re.compile(r"^(?:game|app|site)\.[a-z0-9-]+$")`. Its directory layout is selected by **pack id** (`index_directory_for_pack_id("pack.site")` → `WEBSITE_PACK_INDEX_DIRECTORY`), not by recipe prefix. App-type files use the **full id** as filename (`app.saas-dashboard-core.yaml`), consistent with `site.dashboard-ui-core.yaml`.
- **registry-pack structure.** `website-pack/registry-pack.yaml` (`id: pack.site`) indexes modules under `app_types`, `stack_kits`, `mechanics` (→ `sections/`), `component_contracts` (→ `components/`), `validators`, `recovery_playbooks` (→ `recovery/`), `progress_labels`, `learning_hooks`. An `app.*` app type slots into `app_types` with no structural change.
- **Section/component/validator/recovery folder conventions.** Website-pack maps `mechanics`→`sections`, `component_contracts`→`components`, `recovery_playbooks`→`recovery` (see `WEBSITE_PACK_INDEX_DIRECTORY`). New SaaS modules follow the same folders; no new conventions required.
- **Scaffold context pack resolution.** **This is the one gap.** `resolve_pack_root` (`src/ham/build_registry/scaffold_context.py`) maps `app_type_id.startswith("site.")` → website-pack; **everything else falls through to game-pack**. An `app.saas-dashboard-core` id would resolve to **game-pack** and fail to compose — *unless* a metadata `registry_v2_pack_root` override is supplied, or `resolve_pack_root` is extended to map the `app.` prefix. This matters only at **routing/scaffold-resolution time** (a later step), not at schema authoring, validation, or reference checking.
- **Test impact.** Schema-only authoring would add a new recipe + modules; `tests/test_website_pack_registry.py` module counts and load/compose/render assertions would need updating, and a not-routed assertion would be appropriate until routing is approved. No existing test requires a runtime change for schema-only.
- **Routing impact (later).** Routing requires an explicit matcher in `src/ham/build_registry/intent.py` plus the `resolve_pack_root` mapping above — both deliberately deferred to a separate post-schema step.

---

## 5. Product / domain assessment

- **Why more app-like than `site.dashboard-ui-core`.** A SaaS dashboard implies a logged-in product workspace: app shell, account/workspace context, usage/plan affordances, activity, resources — versus a read-only overview surface.
- **Why it can still be static / app-shell-light.** All of the above can be rendered as a **static** product home with local sample data, a shell frame, and illustrative (non-functional) nav/shortcuts — no fetched data, no sessions.
- **Why it must not become admin / backend / auth / billing / CRUD.** Those introduce real product semantics (mutation, accounts, payments, permissions) that are out of scope for a generative static kit and carry the highest drift risk.
- **Whether `app.*` naming helps enforce the boundary.** Yes — an `app.` prefix signals "app-surface, bounded" and keeps a clear semantic line from `site.*` marketing/overview lanes and from a future, separately gated admin lane. This is the main argument **against** Option C (`site.` rename), which would blur that boundary.

---

## 6. Recommended decision

**Recommended: Option A — author `app.saas-dashboard-core` schema-only in `website-pack/` (`pack.site`).**

This is safe **for schema authoring, validation, and reference checking with no runtime changes**: the validator is recipe-prefix-agnostic (keys on `pack.site` + `kind`), and the reference checker already allows the `app.` prefix and selects website-pack layout by pack id.

Be explicit about the one caveat:

- **If current runtime/checker support is clean → proceed schema-only in `website-pack/`.** It is clean for schema/validate/check. Proceed.
- **The single runtime gap is `resolve_pack_root`** (maps only `site.` → website-pack today). This is a **routing-time** concern, not a schema-authoring blocker. Before the lane is *routed*, make a small, deliberate change — either extend `resolve_pack_root` to map the `app.` prefix to website-pack, or supply a metadata `registry_v2_pack_root` override — as part of the separate routing step.
- **Do not force it.** If, during schema authoring, the lane cannot stay static/app-shell-light (it starts demanding auth/billing/CRUD), **stop** and reconsider — do not expand site-pack scope to accommodate a real app.
- **`app-pack/` is deferred, not rejected.** A single bounded lane does not justify new pack scaffolding now; revisit when the triggers in §8 appear.

---

## 7. Guardrails for schema authoring if proceeding in website-pack

- **Schema-only first** — no routing in the same step.
- **No routing** — defer the `intent.py` matcher and the `resolve_pack_root` `app.` mapping to a separate approved step.
- **No templates** — generative playbook modules only; no starter source trees.
- **Render under 12k, prefer under 11.4k chars** — mirrors `site.dashboard-ui-core` (11,358).
- **Use website-pack folders** (`app-types`, `stack-kits`, `sections`, `components`, `validators`, `recovery`, `progress-labels`, `learning-hooks`) unless a new folder is clearly justified.
- **Strong anti-auth/billing/CRUD guidance** — encode `safety_constraints` (e.g. `no-user-accounts-for-mvp`, `no-backend-api-for-mvp`, `no-crud-mutation-for-mvp`, `no-payment-processing-for-mvp`, `no-admin-permissions-for-mvp`, `static-sample-data-only-for-mvp`) mirroring `site.dashboard-ui-core`.
- **App-shell-light only** — shallow shell + context; no deep multi-route app.
- **Validate + reference-check** — run `validate` + `check_build_registry_references.py --pack docs/build-kit-registry-v2/website-pack/registry-pack.yaml --check-orphans --check-render-budget`.
- **Generated gate later** — only after routing approval; `/tmp/` output, never committed.

---

## 8. What would justify `app-pack/` later

- **Multiple app-shell lanes** (SaaS + admin + portal + operations) rather than a single bounded recipe.
- **Real app workflows** beyond static overview surfaces.
- **Admin / CRUD** lanes (create/update/delete, user management).
- **Auth / permissions** (sessions, RBAC) entering scope.
- **Backend / API assumptions** baked into recipes.
- **Multi-screen app flows** (routing between app views).
- **Richer app state** (stateful interactions beyond static rendering).
- **App-specific loader/checker conventions** that diverge from website-pack's section/component layout.

When two or more of these appear, design `pack.app` deliberately (add to `SUPPORTED_PACK_IDS`, add an `APP_PACK_INDEX_DIRECTORY` + checker branch, and a `resolve_pack_root` mapping) rather than overloading `pack.site`.

---

## 9. Non-goals

This decision does **not** authorize or imply:

- A recipe from this doc
- Routing from this doc
- Runtime / API / frontend changes
- Tests from this doc
- `app-pack/` creation from this doc (deferred unless explicitly approved later)
- Default Build Registry v2 enablement
- Exposing build-kit internals to normal users

---

## 10. References

- [SAAS_DASHBOARD_CORE_RESEARCH.md](./SAAS_DASHBOARD_CORE_RESEARCH.md)
- [SAAS_DASHBOARD_CORE_READINESS_REVIEW.md](./SAAS_DASHBOARD_CORE_READINESS_REVIEW.md)
- [WEBSITE_PACK_STAGE_CHECKPOINT.md](./WEBSITE_PACK_STAGE_CHECKPOINT.md)
- [DASHBOARD_UI_CORE_COMPLETION_CHECKPOINT.md](./DASHBOARD_UI_CORE_COMPLETION_CHECKPOINT.md)
- [STATUS.md](./STATUS.md)
