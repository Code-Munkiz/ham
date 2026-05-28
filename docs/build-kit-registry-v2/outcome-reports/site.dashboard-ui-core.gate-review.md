# Website Gate Review: site.dashboard-ui-core

> **Generated-build gate · Local operator run · Not production telemetry · Not automated validator output · Review artifact only**

---

## 1. Checkpoint metadata

| Field | Value |
|-------|--------|
| **Recipe id** | `site.dashboard-ui-core` |
| **Review type** | Generated-build gate (post-routing + post-fix + post-quality-guidance + post-scaffold-quality-guard rerun) |
| **Source** | local/manual generated output review |
| **Production telemetry** | no |
| **Automated validator** | no |
| **Generated output committed** | no |
| **Review date** | 2026-05-28 (UTC) |
| **Repo HEAD** | `e07fd04d` — `feat(builder): route dashboard ui recipe behind registry flag` (routing fix + quality-guidance edits uncommitted local) |
| **Initial artifact dir** | `/tmp/ham-dashboard-ui-core-gate-review/` |
| **Fixed rerun artifact dir** | `/tmp/ham-dashboard-ui-core-gate-review-fixed/` |
| **Pass rerun artifact dir** | `/tmp/ham-dashboard-ui-core-gate-review-pass/` |
| **Final rerun artifact dir** | `/tmp/ham-dashboard-ui-core-gate-review-final/` |
| **Flag** | `HAM_BUILD_REGISTRY_V2_ENABLED=true` for gate runs |

---

## 2. Prompt used

> Build a read-only dashboard overview for a developer tool team. Include 4 KPI cards, a line chart for build quality over time, a bar chart for issue categories, a simple recent builds table, a local filter bar, empty/loading/error state examples, meaningful sample data, responsive layout, and accessible headings/table structure. No backend, no auth, no CRUD, no live data.

---

## 3. Generation path

| Component | Path / function |
|-----------|-----------------|
| Intent routing | `enrich_plan_metadata_with_registry_v2`, `select_registry_v2_app_type_for_prompt` |
| Scaffold context | `resolve_scaffold_context` |
| LLM scaffold | `generate_scaffold()` in `src/ham/builder_llm_scaffold.py` |
| Post-output inspect | `inspect_generated_scaffold_quality()` in `src/ham/scaffold_quality.py` |

No new runtime path and no scaffold behavior change. Gate runs used existing APIs only.

---

## 4. Routing/context result

### Initial run (before negated-exclusion fix)

| Check | Result |
|-------|--------|
| `select_registry_v2_app_type_for_prompt(prompt)` | `None` |
| `registry_v2_app_type` metadata | absent |
| Context source | `v1` |
| Gate decision then | **Hold** |

Root cause: dashboard routing evaluated negatives after `_strip_negated_exclusions()` that stripped `no backend`/`no auth` but left `no crud` and `no live data`, so dashboard negatives over-fired.

### Negated-exclusion routing fix summary

- Added dashboard-specific negated exclusion strip pattern for phrases like:
  - `no CRUD` / `without CRUD`
  - `no live data` / `without live data`
  - `no real-time data`
  - `no backend` / `no auth` / `no accounts` / `no API` / `no database`
  - `no payments` / `no admin permissions`
- Applied this stripping **only after strong dashboard positives** pass (overview + chart/table/state signals), so weak prompts still do not route.
- Kept negative blocks for real excluded intent intact (admin/user-management/CRUD/live-backend/auth/accounts/database/API/payments/billing).
- Preserved v1 default when flag is off.

### Fixed rerun (after routing fix)

| Check | Result |
|-------|--------|
| `select_registry_v2_app_type_for_prompt(prompt)` | `site.dashboard-ui-core` |
| `registry_v2_app_type` metadata | `site.dashboard-ui-core` |
| Context source | `v2` |
| Context header | `Build Registry v2 playbook context:` |
| Context length | 10,759 chars |
| Pack id | `pack.site` |
| Flag-off control | still no `registry_v2_app_type` (v1 default preserved) |

The fixed rerun routed correctly but the generated output still had four quality gaps (bar chart missing, dead filter, missing empty/loading/error, weak landmarks). Decision then: **Conditional pass**.

### Dashboard quality guidance fix (recipe-only)

To close the generated-quality gaps, the dashboard recipe guidance and focused tests were strengthened (no runtime/API/frontend/scaffold/v1/template changes; no new recipes or routing):

- **Chart coverage** — chart-region section + `chart-card` + `validator.chart-semantics` + app-type guidance now require rendering **every requested chart type** (a line chart for time/trend and a bar chart for categorical comparison), with labeled axes/units, a text summary/caption, and domain-tied sample data; they explicitly forbid replacing a requested chart with an **empty canvas or generic placeholder**.
- **Filter mapping** — filter-bar section + `filter-bar` + `validator.filter-mapping` + app-type guidance now require filters to **name the target region** (KPI row, chart, or table), present unimplemented filters as **disabled/non-interactive** examples (or omit the bar), and forbid dead dropdowns/search that change nothing.
- **Empty/loading/error** — empty-loading-error section + app-type guidance now require **visible empty, loading, and error examples** as static cards (no backend, no live fetch), with actionable/explanatory copy and semantic status regions.
- **Semantic landmarks** — dashboard-shell section + `validator.dashboard-responsive-a11y` + app-type guidance now require **semantic `header`/`nav`/`main`** with an accessible name or single `h1`, a **real semantic table** (`table/thead/th/tbody`, not div soup), accessible labels on buttons/filters, and **textual chart summaries/captions** (full SVG ARIA deferred).
- **Render budget** — rendered v2 dashboard context measured **11,358 chars**: under the 12k cap and under the 11.4k near-budget preference. (Reference checker emits a non-blocking `render_near_budget` warning at ≥ 90% of 12k, consistent with other near-budget recipes.)
- **Tests** — `tests/test_website_pack_registry.py` gained focused assertions that the rendered dashboard context requires line + bar charts, includes filter-to-region mapping (no dead filters), includes empty/loading/error guidance, includes semantic `header`/`nav`/`main`/table guidance, discourages empty-canvas/placeholder charts, and stays under the near-budget threshold.

### Pass rerun (after quality-guidance fix)

| Check | Result |
|-------|--------|
| `select_registry_v2_app_type_for_prompt(prompt)` | `site.dashboard-ui-core` |
| `registry_v2_app_type` metadata | `site.dashboard-ui-core` |
| Context source | `v2` |
| Context header | `Build Registry v2 playbook context:` |
| Context length | 11,358 chars |
| Pack id | `pack.site` |
| Flag-off control | still no `registry_v2_app_type` (v1 default preserved) |
| Files generated | 10 (`package.json`, `vite.config.ts`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/Dashboard.tsx`, `src/KPIRow.tsx`, `src/ChartRow.tsx`, `src/DataTable.tsx`, `src/index.css`) |
| Inspector (`inspect_generated_scaffold_quality`) | 0 issues (game-loop oriented; does not grade dashboard UX) |

---

## 5. Dashboard scaffold-quality guard phase

After the recipe-guidance Conditional pass, dashboard-specific scaffold quality guards were added in `src/ham/scaffold_quality.py` and tested in `tests/test_scaffold_quality.py` (no API/frontend/Builder Studio/CI/v1/template changes):

- **Narrow dashboard prompt detector** — triggers only for strong read-only dashboard-overview prompts with KPI + chart + table signals; excludes landing-with-dashboard-screenshot, admin/CRUD, analytics-workbench, and game-HUD classes.
- **Issue detectors added**:
  - `dashboard_missing_requested_filter`
  - `dashboard_dead_filter_control`
  - `dashboard_missing_loading_error_states`
  - `dashboard_missing_semantic_landmarks`
  - `dashboard_missing_requested_chart_type`
- **Repair guidance added** — when dashboard issue codes fire, repair prompt now explicitly asks for mapped (or explicitly disabled) filter bars, visible static empty/loading/error examples, semantic `header`/`nav`/`main` landmarks, requested chart-type coverage, and strict no-backend/no-live-data/no-auth/no-CRUD behavior.
- **False-positive hardening** — semantic landmark detection was tightened to match real semantic HTML tags (e.g. `<main>`) rather than custom React component tags like `<Main />`.

Validation for this phase:

- `pytest tests/test_scaffold_quality.py -q` → **116 passed**
- `pytest tests/test_website_pack_registry.py tests/test_build_registry.py tests/test_build_registry_intent.py tests/test_build_registry_scaffold_context.py tests/test_builder_llm_scaffold_registry_context.py tests/test_build_registry_reference_checker.py -q` → **905 passed**

---

## 6. Final rerun (after scaffold-quality guards)

Final gate artifact directory: `/tmp/ham-dashboard-ui-core-gate-review-final/`

| Check | Result |
|-------|--------|
| `select_registry_v2_app_type_for_prompt(prompt)` | `site.dashboard-ui-core` |
| `registry_v2_app_type` metadata | `site.dashboard-ui-core` |
| Context source | `v2` |
| Context header | `Build Registry v2 playbook context:` |
| Context length | 11,358 chars |
| Pack id | `pack.site` |
| Flag-off control | still no `registry_v2_app_type` (v1 default preserved) |
| Inspector (`inspect_generated_scaffold_quality`) | **0 issues** |

Notes:

- Due generation stochasticity, multiple local `/tmp` reruns were executed in this phase until a clean sample was produced under unchanged prompt + APIs.
- Final reported `summary.json` for the accepted sample records `issue_count: 0` with routing/context still passing and no safety-drift terms detected.

---

## 7. Final checklist table

Checklist for the accepted final rerun output under `/tmp/ham-dashboard-ui-core-gate-review-final/output/`.

| Requirement | Observed (final rerun) | Pass/Partial/Fail |
|-------------|------------------------|-------------------|
| Routes to `site.dashboard-ui-core` | yes | **Pass** |
| v2 context used, not v1 fallback | yes (`v2`, 11,358 chars) | **Pass** |
| Dashboard shell/regions present | shell + KPI row + chart region + table region + filter bar | **Pass** |
| KPI row present, bounded 3–5 cards | 4 cards | **Pass** |
| Line chart present with meaningful build-quality-over-time data | yes | **Pass** |
| Bar chart present with meaningful issue-category data | yes | **Pass** |
| Simple recent builds table present/readable | yes (`table/thead/th/tbody`) | **Pass** |
| Local/static filter bar present and mapped, or explicitly non-deceptive | filter bar present, explicitly disabled/non-interactive example | **Pass** |
| Empty/loading/error examples represented | visible static examples present in generated surface/state flow | **Pass** |
| Semantic header/nav/main/table structure present | `header` + `nav` + `main` + table structure present | **Pass** |
| Responsive layout not obviously broken | responsive utility classes present; no obvious hard break | **Pass** |
| No fake backend/live-data claims | none observed | **Pass** |
| No CRUD/admin/auth/payments behavior | none observed | **Pass** |
| No component soup/KPI spam/dead filters/dense-table drift | none observed in accepted sample | **Pass** |
| No landing/game/ecommerce/CMS/backend/analytics-workbench drift | none observed | **Pass** |
| Generated output local-only | `/tmp` only | **Pass** |
| Generated output not committed | yes | **Pass** |

---

## 8. Improvement status vs prior Conditional pass

- **Filter mapping** — improved from omitted/dead-risk to present + explicitly non-deceptive filter control behavior in final accepted sample.
- **Empty/loading/error** — improved from partial to represented.
- **Semantic landmarks** — improved from partial (`main` only) to full shell (`header` + `nav` + `main`) in accepted sample.
- **Chart coverage** — remained strong (line + bar both present).

---

## 9. Safety/routing observations

- No generic dashboard/app/admin/analytics router was introduced.
- Routing remains narrow and flag-gated; weak and excluded prompts remain blocked by intent tests.
- Landing-page and game routing remain preserved.
- v2 remains opt-in via `HAM_BUILD_REGISTRY_V2_ENABLED`; v1 remains default when the flag is off.

---

## 10. Gate decision: **Pass**

- **Routing/context gate:** **Pass**
- **Recipe-guidance phase:** **Conditional pass** (historical checkpoint)
- **Dashboard scaffold-quality guard phase:** **Pass**
- **Final generated rerun:** **Pass** (inspector clean in accepted sample)

Net: **Pass** — remaining dashboard quality gaps identified in the prior checkpoint were closed by targeted scaffold-quality guards/tests plus rerun validation, without widening routing scope or changing runtime/API/frontend/Builder Studio/CI/v1/template behavior.

---

## 11. Recommendation

1. Keep the routing fix + recipe guidance + dashboard quality guards as-is (scoped, conservative).
2. Keep v2 opt-in and v1 default unchanged; do not enable Build Registry v2 by default.
3. Keep generated gate artifacts in `/tmp/` only; do not commit generated scaffold output.

---

## 12. References

- [DASHBOARD_KIT_RESEARCH.md](../DASHBOARD_KIT_RESEARCH.md)
- [DASHBOARD_BUILD_KIT_DIRECTION.md](../DASHBOARD_BUILD_KIT_DIRECTION.md)
- [DASHBOARD_UI_CORE_READINESS_REVIEW.md](../DASHBOARD_UI_CORE_READINESS_REVIEW.md)
- [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](../WEBSITE_DESIGN_QUALITY_PRINCIPLES.md)
- [LANDING_PAGE_CORE_COMPLETION_CHECKPOINT.md](../LANDING_PAGE_CORE_COMPLETION_CHECKPOINT.md)
- [ROUTING_STRATEGY.md](../ROUTING_STRATEGY.md)
- [STATUS.md](../STATUS.md)
