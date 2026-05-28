# Dashboard Kit Research

> **Research / distillation only · Not recipe approval · Not routing approval · Not directory implementation · Not runtime enablement**

Research distillation for the next **Build Registry v2 website/app-surface workstream: dashboards**. This document surveys dashboard/app-surface patterns, anti-patterns, information architecture, and the boundary vs landing-page and game lanes. It distills external dashboard research into a practical HAM build-kit planning artifact so the dashboard lane starts from doctrine rather than ambiguity — mirroring how [WEBSITE_DESIGN_SYSTEM_DIRECTION.md](./WEBSITE_DESIGN_SYSTEM_DIRECTION.md) and [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](./WEBSITE_DESIGN_QUALITY_PRINCIPLES.md) preceded `site.landing-page-core`.

**Research date:** 2026-05-28 (UTC)
**Latest pushed commit:** `f7e9e961` — `docs(builder): add landing page core completion checkpoint`
**Baseline:** DOM-native game-kit phase complete (16 recipes / 376 modules); **Landing Page Core website stage complete** — website pack exists with **`site.landing-page-core`** (29 modules, routed behind `HAM_BUILD_REGISTRY_V2_ENABLED`); v1 Builder Kit JSON remains default when the flag is off.

For landing-page closeout see [LANDING_PAGE_CORE_COMPLETION_CHECKPOINT.md](./LANDING_PAGE_CORE_COMPLETION_CHECKPOINT.md). For live registry status see [STATUS.md](./STATUS.md).

**This document adds no recipe, routing, templates, schema, or implementation.** It is research and distillation only.

---

## 1. Executive summary

**The dashboard lane is the next website/app-surface workstream** after the landing/site foundations completed.

- Dashboards are **component-heavy, data-dense, and higher risk** than landing pages — they overlap excluded landing-page families (admin/analytics/data UI) and demand stricter component taxonomy and gate criteria.
- Research recommends **starting with a bounded read-only dashboard lane** before any admin, analytics, or CRUD-heavy lane.
- **Recommended first candidate: `site.dashboard-ui-core`** — a mostly static, read-only dashboard surface (KPI cards, basic charts, a simple table, optional static filters) with no backend, auth, CRUD, or payments.
- **This document adds no recipe, routing, templates, or implementation.** It defines posture and a recommended sequence so the dashboard lane follows the same proven rhythm: direction → principles → readiness → structure plan → schema → validate → route approval → generated gate → quality guidance → checkpoint.

---

## 2. Why dashboards are different

Dashboards do not optimize for the same outcomes as the lanes already shipped.

| Lane | Optimizes for | Core question |
|------|---------------|---------------|
| **Dashboards** | Information architecture, data hierarchy, visual density, decision support | "Can I understand the state and decide?" |
| **Landing pages** | Narrative arc and conversion | "Does it communicate and convert clearly?" |
| **Games** | Playable loops, state mutation, win/loss/restart | "Does it play?" |

Implications for the dashboard lane:

- Dashboards present **dense, structured data for comprehension and action** — not a persuasive story and not a playable loop.
- Quality is judged on **whether the layout supports scanning, comparison, and decisions**, not on conversion CTAs or reducer wiring.
- Dashboard kits need a **stricter component taxonomy** (KPI cards, charts, tables, filters) and **stricter gate criteria** (required regions, bounded KPI rows, meaningful data, state coverage) than marketing landing pages.
- Landing-page detectors (hero, social proof, CTA clarity) and game detectors (win/loss, reducer dispatch) **do not apply** — dashboards need their own quality family.

---

## 3. Information architecture principles

Dashboard IA is the dominant quality lever. A coherent dashboard reads top-down by priority.

- **Inverted pyramid layout** — most important, most summarized information first; detail deepens as the eye moves down.
- **Top row: primary KPIs** — the few headline metrics that answer "how are things right now?"
- **Middle band: charts / trends** — time series, comparisons, and distributions that explain the KPIs.
- **Lower area: tables / detail** — row-level records and drill-down data for investigation.
- **F-pattern / upper-left priority** — place the highest-priority metric in the upper-left where scanning begins.
- **Progressive disclosure** — summarize first; reveal detail on demand (tabs, expand, drill-down) rather than showing everything at once.
- **Overview vs detail separation** — keep the at-a-glance overview distinct from deep detail views; do not interleave them.
- **Avoid putting every data point on one screen** — density is a tool, not a goal; an overloaded dashboard defeats comprehension.

---

## 4. Layout / grid posture

Dashboards need a disciplined grid so generated output reads as intentional, not as a random component dump.

- **12-column or 16-column dashboard grid** — align all regions to a shared column system.
- **8px spacing baseline** — consistent gutters, padding, and gaps from an 8px rhythm.
- **Clear gutters and grouping** — related metrics and controls are visually grouped; unrelated regions are separated.
- **Responsive stacking rules** — multi-column regions collapse predictably to single-column on small screens; KPI rows wrap, charts and tables stack.
- **Avoid arbitrary component placement** — every region sits in the grid for an IA reason (priority, grouping, flow).
- **Prevent random component gallery output** — the dashboard is a composed surface with a purpose, not a showcase of every available widget.

---

## 5. Navigation posture

Navigation depth should match dashboard scope; the first lane stays deliberately shallow.

- **Topnav for small / focused dashboards** — a single-purpose dashboard needs only a top bar with title, a few links, and account controls.
- **Sidebar for deeper dashboards** — multi-section admin/analytics surfaces with many views justify a left sidebar.
- **First lane should stay simple and avoid deep navigation** — `site.dashboard-ui-core` is a single read-only surface; topnav (or no nav) is sufficient.
- **Future admin/app dashboards may need sidebar** — sidebar navigation, nested routes, and view switching are deferred to later admin/app lanes, not the first core lane.

---

## 6. Component taxonomy

The first lane should compose from **core components only** and avoid overpacking every generated dashboard.

| Component | Role | Core / Optional | Constraints |
|-----------|------|-----------------|-------------|
| **KPI / metric cards** | Headline at-a-glance numbers in the top row | **Core** | Bounded count (≈3–6); each has a label, value, and unit; no KPI card spam |
| **Line / bar charts** | Trends and comparisons in the middle band | **Core** | Axis labels, units, legend where needed; meaningful sample data; not decorative |
| **Simple data table / datagrid** | Row-level detail in the lower area | **Core** | Readable column count; headers; sane row count; sortable affordance optional |
| **Filters / search** | Narrow the visible data set | **Optional** | Must map to visible data regions; no dead controls |
| **User / account controls** | Identity / settings entry point in nav | **Optional** | Static; no real auth/session in first lane |
| **Tabs / subnav** | Switch between views or facets | **Optional** | Keep shallow in first lane; prefer progressive disclosure over deep nesting |
| **Activity feed** | Recent events / changes list | **Optional** | Meaningful entries; not lorem; bounded length |
| **Notifications / alerts** | Status messages and warnings | **Optional** | Not color-only meaning; include text/icon |
| **Pie / donut charts** | Part-to-whole composition | **Optional** | Use sparingly; only when composition is the point; avoid over-segmentation |

**Emphasis:**

- The **first lane should use core components only** — KPI cards, one or two basic charts, and a simple table (plus optional static filters).
- **Avoid overpacking** — do not emit every component above in a single generated dashboard; compose for the prompt's actual information need.

---

## 7. Data / state expectations

Generated dashboards must look like real surfaces over real data — not chart chrome filled with noise.

- **Meaningful sample data** — values that tell a coherent story for the dashboard's stated domain.
- **No arbitrary chart arrays** — no `[12, 7, 19, 3]` filler with no domain meaning.
- **Axis labels and units** — every chart axis is labeled; numbers carry units (%, $, count, ms).
- **Filters must map to visible data regions if included** — a filter or search control must visibly affect a region; no decorative controls.
- **Empty / loading / error states required for async-looking components** — any component that implies fetched data must define empty, loading, and error presentation.
- **No fake interactivity** — controls either do something visible or are not present; no inert buttons, dead dropdowns, or non-functional search.

---

## 8. Dashboard anti-pattern taxonomy

Unacceptable patterns for future generated gates and doctrine. These differ from landing-page slop and game no-op reducers.

| Anti-pattern | Symptom | Why it fails |
|--------------|---------|--------------|
| **Random component gallery** | Every widget on one screen with no IA | No decision support; not a real dashboard |
| **KPI card spam** | 8+ undifferentiated metric cards | Buries the few numbers that matter |
| **Fake charts with meaningless data** | Charts over arbitrary arrays, no labels/units | Non-reviewable; misleads |
| **Dead filters / search** | Controls that do not change any region | Broken affordances |
| **Unreadable dense tables** | Too many columns, tiny text, no headers | Defeats the detail purpose |
| **Generic admin panel sludge** | Indistinguishable boilerplate admin shell | No domain fit; AI-default output |
| **Mobile ignored** | Fixed-width grid, horizontal scroll traps | Unusable on small screens |
| **Inaccessible charts / tables** | No table headers, no chart text alternative | Excludes assistive-tech users |
| **Color-only status meaning** | Red/green with no label or icon | Fails for color-blind users; ambiguous |
| **Dashboard-as-marketing-fake-screenshot** | A decorative dashboard mock when the user actually asked for a landing page | Wrong lane; misroute |

---

## 9. Routing ambiguity classes

Dashboard prompts span a wide risk range. Each class needs an explicit posture before any routing is approved.

| Class | Description | Posture |
|-------|-------------|---------|
| **Static / service dashboard** | Read-only status or summary surface, no backend | **First lane target** — `site.dashboard-ui-core` |
| **Analytics workbench** | Exploratory analytics, drill-down, dynamic queries | **Defer** — high density and interactivity |
| **Admin panel / backoffice** | CRUD, user management, settings, permissions | **Defer** — backend/auth/CRUD heavy |
| **CRM / project management** | Pipelines, boards, records, assignment | **Defer** — stateful app semantics |
| **Fintech / trading dashboard** | Real-time prices, dense tables, live charts | **Defer** — highest density and liveness risk |
| **Game HUD** | In-game status overlay | **Out of lane** — belongs to game pack, not dashboards |
| **Landing page with fake dashboard screenshot** | Marketing page that shows a decorative dashboard | **Route to landing lane** — `site.landing-page-core`, not a dashboard recipe |
| **Generic dashboard prompt** | "build a dashboard" with no domain or data signals | **Do not route** — too ambiguous; v1 fallback until signals are clear |

---

## 10. Candidate dashboard lanes

| Lane | Purpose | Risk | Recommended order |
|------|---------|------|-------------------|
| **`site.dashboard-ui-core`** | Read-only/static dashboard surface: KPI cards, basic charts, simple table | Low–medium — bounded, no backend | **1 (first)** |
| **`app.admin-dashboard-core`** | Admin/backoffice with CRUD, user management | High — backend/auth/CRUD | Defer |
| **`app.analytics-dashboard-core`** | Analytics workbench, drill-down, dynamic queries | High — density + interactivity | Defer |
| **`app.saas-dashboard-core`** | SaaS product dashboard with accounts, billing surfaces | High — auth/billing/app semantics | Defer |
| **`app.operations-dashboard-core`** | Ops/monitoring with live status, alerts | High — liveness, alerting, density | Defer |
| **`app.user-portal-dashboard`** | Authenticated user portal / account home | High — auth/session/personal data | Defer |

**Recommendation:**

- **Start with `site.dashboard-ui-core`** — the smallest coherent dashboard archetype with a clear region checklist and no backend.
- **Defer admin / analytics / SaaS / operations / user portal** until core dashboard IA and gates are proven on the first lane.

---

## 11. Recommended first lane: `site.dashboard-ui-core`

**Scope (in):**

| Area | Expectation |
|------|-------------|
| **Surface** | Read-only or mostly static dashboard page |
| **KPI cards** | Bounded top-row metric cards with label, value, unit |
| **Basic charts** | One or two line/bar charts with axis labels and units |
| **Simple table** | A readable detail table with headers and bounded columns |
| **Filters** | Optional static / local filters that map to a visible region |
| **States** | Empty / loading / error state guidance for async-looking components |
| **Responsive layout** | Predictable stacking; no fixed-width or horizontal-scroll traps |
| **Accessibility** | Semantic landmarks/headings, table headers, labeled controls, non-color-only status |

**Out of scope (first lane):**

- No backend, auth, CRUD, or payments
- No admin user management
- No complex analytics workbench (drill-down, dynamic queries, pivot)
- No real-time / live data, websockets, or trading-grade density
- No multi-route app shell or deep sidebar navigation

---

## 12. Generated gate criteria

A future `site.dashboard-ui-core` generated gate should check:

| Criterion | Pass expectation |
|-----------|------------------|
| **Correct routing / context** | Prompt maps to the dashboard app type; v2 context used; not landing/game/v1 fallback on a clear match |
| **Required dashboard regions present** | KPI row + at least one chart + a detail table per recipe checklist |
| **KPI row bounded** | Roughly 3–6 differentiated KPI cards; no card spam |
| **Chart / table semantics** | Charts have axis labels and units; tables have headers and readable column counts |
| **Meaningful sample data** | Domain-coherent values; no arbitrary filler arrays |
| **Filter–control mapping if filters exist** | Each filter/search visibly affects a data region; no dead controls |
| **Empty / loading / error states** | Async-looking components define all three states |
| **Responsive behavior** | Regions stack predictably; no horizontal scroll traps |
| **Accessibility** | Landmarks, heading structure, labeled buttons, table headers, chart text alternatives |
| **No anti-pattern drift** | §8 patterns absent or documented as false positives |
| **Artifact hygiene** | Generated output stays **under `/tmp/` only** — never committed |

---

## 13. Validation / testing posture

Mirror the landing-page rhythm: cheap structural checks first, automation later, nothing CI-blocking initially.

| Phase | Recommendation |
|-------|----------------|
| **Start** | Static / schema / reference checks first — validate YAML, compose, render budget |
| **Generated review** | **Manual generated gate first** — representative prompts, `/tmp/` output, outcome report |
| **DOM / a11y automation** | **Later** — Playwright / ARIA snapshots for landmarks, table headers, control labels |
| **Chart accessibility** | **Later** — SVG / chart ARIA expectations as guidance before enforcement |
| **Visual regression** | **No** pixel-perfect screenshot gates |
| **CI** | **No CI-blocking** dashboard generated gates initially — mirror game/landing warning-only posture |

---

## 14. What to adopt now

- A **dashboard direction doc** (`DASHBOARD_BUILD_KIT_DIRECTION.md`) — posture, lanes, first candidate.
- A **dashboard readiness review** (`DASHBOARD_UI_CORE_READINESS_REVIEW.md`) — ambiguity classes, routing boundaries, region checklist, deferrals.
- A **conservative first lane** — read-only `site.dashboard-ui-core` only.
- A **strict anti-pattern taxonomy** (§8) as persistent doctrine.
- A **generated gate checklist** (§12) defined before schema lands.
- A **bounded component set** (§6 core-only) for the first lane.

---

## 15. What to defer

- Admin CRUD (create/update/delete, user management).
- Analytics workbench (drill-down, dynamic queries, pivots).
- Fintech / trading density and real-time data.
- Backend / auth / permissions / sessions.
- Complex Playwright interaction flows.
- ARIA snapshot CI gates (blocking).
- SVG chart accessibility enforcement as blocking.
- Pixel-perfect visual regression.

---

## 16. Recommended next steps

1. **Create `DASHBOARD_BUILD_KIT_DIRECTION.md`** — dashboard workstream direction (posture, lanes, first candidate, validation/routing posture).
2. **Create `DASHBOARD_UI_CORE_READINESS_REVIEW.md`** — ambiguity gate, routing boundaries, region checklist, deferrals before any schema work.
3. **Decide website-pack vs app-pack placement** for the dashboard lane (`site.*` under `website-pack/` vs a new `app-pack/` for app-surface lanes).
4. **Author `site.dashboard-ui-core` schema-only** — after readiness approval; no routing.
5. **Add validation / checker tests** — load / compose / render budget; orphan and reference checks where supported.
6. **Route only after approval** — separate PR, intent tests, conservative negatives; `HAM_BUILD_REGISTRY_V2_ENABLED` stays off by default.
7. **Run generated gate review** — `/tmp/` scaffold under the canonical dashboard prompt; outcome report; optional future scaffold quality family.

Do **not** skip steps 1–3 to land schema faster, and do **not** combine schema and routing in one PR.

---

## 17. References

- [LANDING_PAGE_CORE_COMPLETION_CHECKPOINT.md](./LANDING_PAGE_CORE_COMPLETION_CHECKPOINT.md)
- [WEBSITE_DESIGN_SYSTEM_DIRECTION.md](./WEBSITE_DESIGN_SYSTEM_DIRECTION.md)
- [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](./WEBSITE_DESIGN_QUALITY_PRINCIPLES.md)
- [WEBSITE_PACK_STRUCTURE_PLAN.md](./WEBSITE_PACK_STRUCTURE_PLAN.md)
- [STATUS.md](./STATUS.md)
