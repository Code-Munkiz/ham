# Dashboard UI Core Readiness Review

> **Readiness / ambiguity gate only · Not recipe approval · Not routing approval · Not implementation authorization · Not runtime enablement**

Readiness and ambiguity review for the first dashboard build-kit lane: **`site.dashboard-ui-core`**. This review defines candidate lane intent, ambiguity classes, routing signals/exclusions, scope recommendation, generated gate expectations, and suggested schema module themes — **before** any YAML lands. It builds on [DASHBOARD_KIT_RESEARCH.md](./DASHBOARD_KIT_RESEARCH.md) and [DASHBOARD_BUILD_KIT_DIRECTION.md](./DASHBOARD_BUILD_KIT_DIRECTION.md) and does **not** add a recipe, routing, templates, schema, runtime changes, or default v2 enablement.

**Review date:** 2026-05-28 (UTC)
**Latest pushed commit:** `66fa1964` — `docs(builder): add dashboard build kit direction`
**Baseline:** DOM-native game-kit phase complete (16 recipes / 376 modules); **Landing Page Core website stage complete** — website pack exists with **`site.landing-page-core`** (29 modules, routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`); v1 Builder Kit JSON remains default when the flag is off.

For research see [DASHBOARD_KIT_RESEARCH.md](./DASHBOARD_KIT_RESEARCH.md). For direction see [DASHBOARD_BUILD_KIT_DIRECTION.md](./DASHBOARD_BUILD_KIT_DIRECTION.md). For live registry status see [STATUS.md](./STATUS.md).

---

## 1. Executive summary

**`site.dashboard-ui-core` is recommended as the first dashboard lane.**

- It is a **bounded, read-only / mostly static dashboard surface** — KPI cards, one or two basic charts, a simple table, and optional static filters.
- It should be **authored schema-only next** if scope stays tight (read-only, no backend/auth/CRUD) and routing remains deferred.
- **This review does not add a recipe, routing, templates, or implementation.** It is a readiness/ambiguity gate that defines the boundaries before schema work begins.

---

## 2. Current baseline

| Dimension | State |
|-----------|-------|
| **Game-kit phase** | **Complete** — 16 DOM-native game recipes / 376 modules |
| **Landing Page Core** | **Complete** — `site.landing-page-core` schema, validation, routing, and generated gate landed; final gate **Pass** |
| **Website pack** | **Exists** — first recipe `site.landing-page-core` (29 modules) under `website-pack/` |
| **`site.landing-page-core` routing** | Routes narrowly behind `HAM_BUILD_REGISTRY_V2_ENABLED` on clear static landing/marketing intent; gate passed |
| **`pack.site` validation / checker** | **Supported** — `scripts/validate_game_pack_registry.py` + `scripts/check_build_registry_references.py` accept `--pack` / `--pack-root` |
| **Dashboard research + direction** | **Landed** — [DASHBOARD_KIT_RESEARCH.md](./DASHBOARD_KIT_RESEARCH.md) (`671132a9`), [DASHBOARD_BUILD_KIT_DIRECTION.md](./DASHBOARD_BUILD_KIT_DIRECTION.md) (`66fa1964`) |
| **Default lane** | **v1** Builder Kit JSON preserved when flag is off or unset |
| **Build Registry v2** | **Opt-in** preserved — `HAM_BUILD_REGISTRY_V2_ENABLED` off by default |

---

## 3. Candidate lane intent

`site.dashboard-ui-core` produces a single, coherent, **read-only dashboard surface**:

- **Read-only dashboard surface** — presents state; does not mutate it.
- **KPI cards** — a bounded top row of headline metrics (label, value, unit).
- **Basic line / bar chart areas** — one or two trend/comparison regions with axis labels and units.
- **Simple table / datagrid** — a readable detail table with headers and bounded columns.
- **Optional static / local filters** — controls that map to a visible region, using local sample data only.
- **Empty / loading / error state guidance** — for any async-looking component.
- **Responsive grid** — predictable stacking; no fixed-width or horizontal-scroll traps.
- **Accessibility semantics** — landmarks/headings, table headers, labeled controls, non-color-only status.
- **No backend / auth / CRUD / payments / admin permissions.**

---

## 4. Why this is the right first dashboard lane

- **Bridges landing pages and richer app surfaces** — a natural next step up from `site.landing-page-core` without jumping to full apps.
- **Proves dashboard IA without admin complexity** — exercises inverted-pyramid layout, KPI/chart/table regions, and grid discipline in isolation.
- **Teaches KPI / chart / table composition** — the core dashboard vocabulary that every later lane reuses.
- **Lower risk than CRUD / admin / analytics workbench** — no backend, auth, mutation, or dynamic querying to get wrong.
- **Establishes future dashboard anti-pattern gates** — gives the generated gate a concrete, bounded surface to calibrate detectors against before higher-risk lanes open.

---

## 5. Why this is risky

Even a read-only dashboard is higher risk than a landing page:

- **Component soup** — widgets dumped on a page with no IA or priority.
- **Fake charts** — chart chrome with no real or meaningful series.
- **Meaningless sample data** — arbitrary arrays that tell no domain story.
- **KPI spam** — undifferentiated metric-card walls that bury the few numbers that matter.
- **Dead filters / search** — controls that change nothing visible.
- **Unreadable tables** — too many columns, tiny text, missing headers.
- **Mobile ignored** — fixed-width grids and horizontal scroll traps.
- **Inaccessible charts / tables** — no table headers, no chart text alternative.
- **Admin / app scope creep** — drift into CRUD, auth, user management, or live data.

---

## 6. Ambiguity classes

| Class | Examples | Routing posture |
|-------|----------|-----------------|
| **Generic dashboard request** | "build a dashboard", "make a dashboard UI" | **Weak alone** — require read-only / overview + KPI/chart/table signals before routing |
| **Analytics workbench** | "exploratory analytics", "ad-hoc query builder", "pivot/drill-down explorer" | **Defer / do not route** |
| **Admin panel / backoffice** | "admin panel", "user management", "settings/permissions console" | **Defer / do not route** |
| **SaaS app dashboard** | "SaaS app dashboard with login and billing" | **Possible future sibling** — do not steal if auth/billing/app-state heavy |
| **Operations dashboard** | "ops monitoring", "incident/alerting console" | **Future / niche** — do not route initially |
| **User portal dashboard** | "logged-in user portal", "account home" | **Future sibling** — do not route initially |
| **CRM / project management** | "CRM pipeline", "kanban project board", "deal tracker" | **Defer** |
| **Fintech / trading dashboard** | "trading dashboard", "order book", "live prices" | **Defer** |
| **Game HUD** | "in-game HUD", "score/health overlay" | **Preserve game/HUD handling** — do not route to dashboard lane |
| **Landing page with dashboard screenshot** | "marketing page that shows a product dashboard image" | **Preserve landing-page route** if marketing intent is primary |
| **Data dashboard with backend / live data** | "dashboard wired to my API / live database" | **Fallback / clarify** — out of first-lane scope |

---

## 7. Strong positive signals for future routing

Routing should require **combined** read-only dashboard signals, for example:

- "read-only dashboard"
- "dashboard overview"
- "KPI cards"
- "metrics overview"
- "line/bar chart"
- "simple data table"
- "status / monitoring overview" (static)
- "static dashboard mockup"
- "local sample data dashboard"
- "no backend / no auth"

A strong route combines an overview/read-only intent **plus** at least KPI/metrics **and** chart/table signals — not a single term.

---

## 8. Weak signals that should not route alone

These terms are insufficient on their own and must not route:

- "dashboard"
- "app"
- "admin"
- "analytics"
- "metrics"
- "chart"
- "table"
- "data"
- "report"
- "portal"
- "overview"

---

## 9. Explicit exclusions

The following must **not** route to `site.dashboard-ui-core` (fall back to v1, clarify, or route to the correct lane):

- Admin CRUD
- User management
- Auth / accounts
- Backend / API / database wiring
- Payments / billing management
- Analytics workbench / ad-hoc querying
- CRM / project management
- Ecommerce admin
- Trading / fintech / order book
- Real-time monitoring / streaming
- Map / geospatial operations
- Game HUD
- Landing-page marketing screenshot
- Exact clone / pixel-perfect dashboard clone

---

## 10. Candidate scope recommendation

| Element | Recommendation |
|---------|----------------|
| **Page count** | One dashboard page |
| **Layout** | 12-column responsive layout |
| **KPI cards** | **3–5 max** |
| **Charts** | **1–2 max** (line/bar) |
| **Table** | **1 simple table max** |
| **Filters** | Optional local / static filter bar (mapped to a visible region) |
| **Structure** | Semantic `header` / `main` / `nav` structure |
| **States** | Empty / loading / error state examples |
| **Data** | Meaningful sample data |
| **Backend / auth / CRUD** | **None** |
| **Advanced chart types** | **None** |
| **Real-time updates** | **None** |
| **Admin forms** | **None** |

---

## 11. Generated quality expectations

A future generated gate should require:

- Dashboard shell / regions present
- Bounded KPI row
- Chart / table sections present
- Meaningful sample data
- Axis labels / units where applicable
- No fake / meaningless chart data
- Filter mapping if filters appear
- Empty / loading / error states represented
- Table readable and bounded
- Responsive stacking guidance
- Semantic headings / `nav` / `main` / table structure
- No color-only status meaning
- No dashboard / component soup
- No backend / live data claims

---

## 12. Suggested schema module themes

Possible modules to mirror the website-pack structure (themes only — no YAML authored here):

**App-type / layout / section modules:**

- `dashboard-layout-grid`
- `dashboard-kpi-row`
- `dashboard-chart-region`
- `dashboard-table-region`
- `dashboard-filter-bar`
- `dashboard-sample-data`
- `dashboard-empty-loading-error-states`
- `dashboard-responsive-structure`
- `dashboard-accessibility-basics`
- `dashboard-anti-component-soup`

**Component modules:**

- `components/kpi-card`
- `components/chart-card`
- `components/simple-data-table`
- `components/filter-bar`
- `components/status-badge`

**Validators (conceptual first):**

- KPI count bound
- chart semantics (axis labels / units)
- table readability / bounded columns
- dead filter / search detection
- sample-data relevance
- responsive layout
- accessibility basics

**Recovery playbooks:**

- KPI spam
- fake charts
- dead filters
- dense / unreadable table
- component soup
- admin / app scope drift

**Plus:** a `progress` label (`progress.site-dashboard-ui-core`) and a `learning` hook (`learning.site-dashboard-ui-core`).

---

## 13. Readiness decision

**Ready to author `site.dashboard-ui-core` schema-only next** — conditional on:

- **Scope remains read-only / static** — no backend, auth, CRUD, payments, admin permissions, advanced charts, or real-time data.
- **Routing remains deferred** — routing must **not** be added in the same step as schema.
- **Generated gate required after future routing** — the lane is not "complete" until a `/tmp/` generated gate review passes under the canonical dashboard prompt.
- **Admin / analytics / CRUD / backend remain deferred** — the `app.*` siblings stay out of scope until core dashboard IA and gates are proven.

---

## 14. Recommended next step

1. **Author `site.dashboard-ui-core` schema-only** in `website-pack/` (no routing).
2. **Keep render under 12k**, preferably **under 11.4k** chars.
3. **Validate website-pack and run the reference checker** (load / compose / render budget; orphan/reference checks where supported).
4. **Do not route** until explicit approval.
5. **Add conservative routing only after tests** — separate PR, intent tests, conservative negatives; flag stays off by default.
6. **Run a generated gate review** before declaring the lane complete.

Do **not** combine schema and routing in one PR.

---

## 15. Non-goals

This readiness review does **not** authorize or imply:

- A recipe from this review
- Routing from this review
- Backend / auth / CRUD work
- An admin panel
- An analytics workbench
- A SaaS app dashboard yet
- Real-time data
- Maps / geospatial
- A trading dashboard
- A Playwright / ARIA CI gate yet
- Committing generated output (artifacts stay under `/tmp/` only)
- Default v2 enablement

---

## 16. References

- [DASHBOARD_KIT_RESEARCH.md](./DASHBOARD_KIT_RESEARCH.md)
- [DASHBOARD_BUILD_KIT_DIRECTION.md](./DASHBOARD_BUILD_KIT_DIRECTION.md)
- [LANDING_PAGE_CORE_COMPLETION_CHECKPOINT.md](./LANDING_PAGE_CORE_COMPLETION_CHECKPOINT.md)
- [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](./WEBSITE_DESIGN_QUALITY_PRINCIPLES.md)
- [WEBSITE_PACK_STRUCTURE_PLAN.md](./WEBSITE_PACK_STRUCTURE_PLAN.md)
- [STATUS.md](./STATUS.md)
