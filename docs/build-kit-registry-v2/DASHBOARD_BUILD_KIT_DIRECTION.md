# Dashboard Build Kit Direction

> **Direction / planning only · Not recipe approval · Not routing approval · Not implementation authorization · Not runtime enablement**

Planning checkpoint for the next Build Registry v2 website-pack workstream: **dashboard / app-surface build kits**. This document defines scope, risks, information-architecture posture, validation rhythm, and the recommended first lane after the Landing Page Core stage closed. It builds directly on the landed research in [DASHBOARD_KIT_RESEARCH.md](./DASHBOARD_KIT_RESEARCH.md) and does **not** add recipes, routing, templates, starter source files, schema, runtime changes, or default v2 enablement.

**Direction date:** 2026-05-28 (UTC)
**Latest pushed commit:** `671132a9` — `docs(builder): add dashboard kit research`
**Baseline:** DOM-native game-kit phase complete (16 recipes / 376 modules); **Landing Page Core website stage complete** — website pack exists with **`site.landing-page-core`** (29 modules, routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`); v1 Builder Kit JSON remains default when the flag is off.

For dashboard research see [DASHBOARD_KIT_RESEARCH.md](./DASHBOARD_KIT_RESEARCH.md). For landing-page closeout see [LANDING_PAGE_CORE_COMPLETION_CHECKPOINT.md](./LANDING_PAGE_CORE_COMPLETION_CHECKPOINT.md). For live registry status see [STATUS.md](./STATUS.md).

---

## 1. Executive summary

**Dashboard / app-surface kits are the next website-pack workstream** after the landing/site foundations completed.

- Start with **`site.dashboard-ui-core`** — a bounded, read-only / mostly static dashboard surface.
- Dashboards are component-heavy and data-dense, so they need a separate direction with stricter component taxonomy, information-architecture posture, and gate criteria than landing pages.
- **This doc does not add recipes, routing, templates, or implementation.**
- Its goal is to define **scope, risks, validation posture, and next steps** so the dashboard lane follows the proven rhythm: direction → readiness → schema → validate → route approval → generated gate → quality guidance → checkpoint.

---

## 2. Current baseline

| Dimension | State |
|-----------|-------|
| **Game-kit phase** | **Complete** — 16 DOM-native game recipes / 376 modules (see [LANDING_PAGE_CORE_COMPLETION_CHECKPOINT.md](./LANDING_PAGE_CORE_COMPLETION_CHECKPOINT.md) baseline) |
| **Landing Page Core** | **Complete** — `site.landing-page-core` schema, validation, routing, and generated gate all landed; final gate **Pass** |
| **`pack.site` validation / checker** | **Supported** — `scripts/validate_game_pack_registry.py` + `scripts/check_build_registry_references.py` accept `--pack` / `--pack-root` for website-pack |
| **`site.landing-page-core` routing** | Routes narrowly behind `HAM_BUILD_REGISTRY_V2_ENABLED` on clear static landing/marketing intent; gate passed |
| **Default lane** | **v1** Builder Kit JSON when the flag is off or unset |
| **Build Registry v2** | **Opt-in** — `HAM_BUILD_REGISTRY_V2_ENABLED` off by default |
| **Latest research** | [DASHBOARD_KIT_RESEARCH.md](./DASHBOARD_KIT_RESEARCH.md) landed at `671132a9` — recommends `site.dashboard-ui-core` first |
| **Templates / starter files** | **None** — generative playbooks only |
| **Generated output** | **Not committed** — gate artifacts under `/tmp/` only |

---

## 3. Why dashboards need a separate direction

Dashboards are not a longer landing page — they are a different surface class with different failure modes.

- **Data-dense and component-heavy** — KPI rows, charts, tables, and filters coexist on one surface, unlike the linear section flow of a landing page.
- **More complex than landing pages** — comprehension and decision support replace narrative and conversion as the success metric.
- **Risk of component soup** — without disciplined IA, generation devolves into a pile of widgets with no priority or grouping.
- **Risk of fake charts / dead filters** — charts over arbitrary arrays and controls that change nothing are easy for an LLM to emit and hard to catch without explicit gates.
- **Higher accessibility and responsive needs** — tables, charts, and status indicators have stronger semantic and contrast requirements than marketing copy; dense grids break on mobile if not designed to stack.
- **Scope drift risk** — dashboard surfaces can slide into app / admin / analytics scope (CRUD, auth, live data) unless the first lane is explicitly bounded read-only.

---

## 4. Recommended first lane

**`site.dashboard-ui-core`**

**Scope (in):**

| Area | Expectation |
|------|-------------|
| **Surface** | Read-only / mostly static dashboard page |
| **KPI cards** | Bounded top-row metric cards with label, value, unit |
| **Chart areas** | One or two line/bar chart regions with axis labels and units |
| **Table / datagrid** | A simple, readable detail table with headers and bounded columns |
| **Filters** | Optional static / local filters that map to a visible region |
| **States** | Empty / loading / error state guidance for async-looking components |
| **Responsive layout** | Predictable stacking; no fixed-width or horizontal-scroll traps |
| **Accessibility** | Semantic landmarks/headings, table headers, labeled controls, non-color-only status |

**Out of scope (first lane):**

- No backend, auth, CRUD, or payments
- No admin permissions / user management
- No analytics workbench, drill-down, or dynamic querying
- No real-time / live data, websockets, or trading-grade density

---

## 5. Why not admin or analytics first

Defer the following higher-complexity lanes until core dashboard IA and gates are proven:

| Lane | Why deferred |
|------|--------------|
| **`app.admin-dashboard-core`** | CRUD, user management, settings, and permissions require backend/auth semantics |
| **`app.analytics-dashboard-core`** | Drill-down, dynamic queries, and pivots add density and interactivity complexity |
| **`app.saas-dashboard-core`** | Accounts, billing surfaces, and app shell pull in auth and stateful app semantics |
| **`app.operations-dashboard-core`** | Live status, alerting, and monitoring add liveness and density risk |
| **`app.user-portal-dashboard`** | Authenticated portal needs auth, sessions, and personal-data handling |

**Reason:** each carries too much CRUD, auth, permissions, backend, data-querying, or workflow complexity for the first dashboard lane. Prove read-only IA, region structure, and gate discipline on `site.dashboard-ui-core` before opening any of these.

---

## 6. Information architecture posture

Dashboard IA is the dominant quality lever. The first lane reads top-down by priority.

- **Inverted pyramid** — most summarized, highest-priority information first; detail deepens downward.
- **Top KPI row** — headline metrics, **max about 4–5 cards** to keep the row scannable.
- **Middle charts / trends** — time series and comparisons that explain the KPIs.
- **Lower detail / table area** — row-level records for investigation.
- **Overview-first, detail-later** — at-a-glance summary precedes deep detail.
- **Progressive disclosure** — reveal detail on demand rather than packing it all up front.
- **Avoid putting everything on one screen** — density is a tool, not a goal.

---

## 7. Component taxonomy posture

**Core first** (the first lane composes from these only):

- KPI cards
- Line / bar charts
- Simple table
- Filter / search bar **if locally mapped** to a visible region
- Header / nav shell (topnav)
- Empty / loading / error states

**Defer** (not in the first lane):

- Complex chart types (heatmaps, treemaps, multi-axis, candlesticks)
- CRUD forms
- Kanban / workflow boards
- Maps
- Real-time streams
- Permission matrices
- Trading / order-book density

---

## 8. Anti-pattern policy

The dashboard lane explicitly rejects (persistent doctrine; future gates may enforce a subset):

- **Random component gallery** — widgets with no IA or priority
- **KPI card spam** — undifferentiated metric-card walls
- **Fake charts with meaningless data** — arbitrary arrays, no labels/units
- **Dead filters / search** — controls that change nothing visible
- **Unreadable dense tables** — too many columns, tiny text, no headers
- **Generic admin panel sludge** — indistinguishable boilerplate admin shell
- **Inaccessible charts / tables** — no table headers, no chart text alternative
- **Color-only status indicators** — red/green with no label or icon
- **Mobile ignored** — fixed-width grids, horizontal scroll traps
- **Marketing fake screenshot routed as dashboard** — a decorative dashboard mock when the user actually wanted a landing page

---

## 9. Routing posture

**No routing from this document.**

- Future dashboard routing must follow [ROUTING_STRATEGY.md](./ROUTING_STRATEGY.md) **route-after-approval** discipline.
- **No generic dashboard / app / admin router** — weak terms (`dashboard`, `app`, `admin`, `panel`) alone must not route.
- **Preserve landing-page routing** — marketing prompts continue to route to `site.landing-page-core`.
- **Preserve all game routing** — dashboard matchers must not steal game or app-builder prompts.
- **Dashboard prompts need strong read-only dashboard signals** — KPI/metrics + charts + table intent, not a single weak term.
- **Excluded prompts must fall back or clarify** — admin/CRUD, analytics workbench, backend/auth, fintech/trading, and landing-with-fake-dashboard prompts fall back to v1 or route to their correct lane.
- `HAM_BUILD_REGISTRY_V2_ENABLED` remains off by default; routing lands in a dedicated PR with intent tests.

---

## 10. Generated gate criteria

A future `site.dashboard-ui-core` generated gate should check:

| Criterion | Pass expectation |
|-----------|------------------|
| **Route / context correctness** | Prompt maps to the dashboard app type; v2 context used; not landing/game/v1 fallback on a clear match |
| **Required dashboard regions** | KPI row + at least one chart + a detail table per recipe checklist |
| **Bounded KPI row** | Roughly 3–5 differentiated KPI cards; no card spam |
| **Meaningful chart / table sample data** | Domain-coherent values; axis labels and units; no arbitrary filler |
| **Filter mappings if filters exist** | Each filter/search visibly affects a data region; no dead controls |
| **Empty / loading / error states** | Async-looking components define all three states |
| **Semantic structure** | Heading hierarchy, `nav`/`main` landmarks, real table structure with headers |
| **Responsive layout** | Regions stack predictably; no horizontal scroll traps |
| **No fake backend / live data claims** | Static sample data presented honestly; no fake "live" wiring |
| **No anti-pattern drift** | §8 patterns absent or documented as false positives |
| **Artifact hygiene** | Generated output stays **under `/tmp/` only** — never committed |

---

## 11. Validation / testing posture

**Adopt now:**

- Schema / reference checks (validate YAML, compose, render budget; orphan/reference checks where supported).
- Manual generated gate review — representative prompts, `/tmp/` output, outcome report.
- Static structural checks where easy (region presence, heading/landmark/table structure).

**Defer:**

- Playwright / ARIA snapshots
- SVG chart ARIA enforcement as blocking
- Pixel-perfect visual regression
- CI-blocking generated dashboard gates
- Complex interaction testing

Mirror the game/landing warning-only CI posture — no blocking dashboard gates initially.

---

## 12. Pack placement

- **Keep the first lane in `website-pack`** as **`site.dashboard-ui-core`** — it reuses the established `pack.site` validation/checker support and the proven website-pack structure.
- **Do not create an `app-pack` yet** — a read-only dashboard surface is a website/app-surface lane, not a full app.
- **Revisit `app-pack`** when admin / CRUD / app-shell lanes (`app.*`) begin — that is the right point to decide on a separate app-surface pack with its own conventions.

See [WEBSITE_PACK_STRUCTURE_PLAN.md](./WEBSITE_PACK_STRUCTURE_PLAN.md) for the `website-pack/` folder and naming conventions to mirror.

---

## 13. Recommended next steps

1. **Create `DASHBOARD_UI_CORE_READINESS_REVIEW.md`** — ambiguity classes, routing boundaries, region checklist, module themes, deferrals before any schema work.
2. **Author `site.dashboard-ui-core` schema-only** — after readiness approval; no routing.
3. **Validate website-pack / reference-check** — load / compose / render budget; orphan and reference checks.
4. **Route only after explicit approval** — separate PR, intent tests, conservative negatives; flag stays off by default.
5. **Run generated gate review** — `/tmp/` scaffold under the canonical dashboard prompt; outcome report.
6. **Add quality guard / readiness improvements only if the gate exposes gaps** — do not pre-build detectors.

Do **not** combine schema and routing in one PR.

---

## 14. Non-goals

This direction document does **not** authorize or imply:

- A recipe from this doc alone
- Routing from this doc alone
- Backend, auth, or CRUD work
- An analytics workbench
- An admin panel
- Templates or starter source files
- CI workflow changes
- Runtime, API, or frontend changes
- Builder Studio or scaffold-behavior changes
- v1 JSON, recipe YAML, website-pack, or game-pack YAML edits from this doc
- Default v2 enablement

---

## 15. References

- [DASHBOARD_KIT_RESEARCH.md](./DASHBOARD_KIT_RESEARCH.md)
- [LANDING_PAGE_CORE_COMPLETION_CHECKPOINT.md](./LANDING_PAGE_CORE_COMPLETION_CHECKPOINT.md)
- [WEBSITE_DESIGN_SYSTEM_DIRECTION.md](./WEBSITE_DESIGN_SYSTEM_DIRECTION.md)
- [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](./WEBSITE_DESIGN_QUALITY_PRINCIPLES.md)
- [WEBSITE_PACK_STRUCTURE_PLAN.md](./WEBSITE_PACK_STRUCTURE_PLAN.md)
- [STATUS.md](./STATUS.md)
