# SaaS Dashboard Core Research

> **Research / distillation only · Not readiness · Not recipe approval · Not routing approval · Not schema · Not implementation · Not runtime enablement**

Research artifact for the next dashboard sibling lane: **`app.saas-dashboard-core`**. This document surveys what a bounded SaaS dashboard core build kit should and should not cover, **before** any readiness, schema, or implementation work. It builds on [DASHBOARD_KIT_RESEARCH.md](./DASHBOARD_KIT_RESEARCH.md), [DASHBOARD_BUILD_KIT_DIRECTION.md](./DASHBOARD_BUILD_KIT_DIRECTION.md), and the completed [DASHBOARD_UI_CORE_COMPLETION_CHECKPOINT.md](./DASHBOARD_UI_CORE_COMPLETION_CHECKPOINT.md). It mirrors how [DASHBOARD_KIT_RESEARCH.md](./DASHBOARD_KIT_RESEARCH.md) preceded `site.dashboard-ui-core`.

**Research date:** 2026-05-29 (UTC)
**Latest pushed commit:** `9e3d4c74` — `docs(builder): add invisible orchestration chat ux checkpoint`
**Baseline:** DOM-native game-kit phase complete; website-pack foundation complete; `site.landing-page-core` and `site.dashboard-ui-core` complete with final gate **Pass**; invisible orchestration provider seams complete; v1 default preserved; v2 opt-in behind `HAM_BUILD_REGISTRY_V2_ENABLED`.

For live registry status see [STATUS.md](./STATUS.md).

**This document adds no recipe, routing, schema, templates, or implementation.** It is research and distillation only.

---

## 1. Executive summary

- **`app.saas-dashboard-core` is the likely next dashboard sibling** after `site.dashboard-ui-core` — the natural step up from a read-only overview surface toward an app-like product workspace.
- It should be **researched before any readiness or schema work** — the SaaS framing carries higher drift risk (auth, billing, CRUD) than the read-only dashboard lane.
- It is **more app-like than `site.dashboard-ui-core`** (app shell, account/project context, usage/plan affordances) but **should remain bounded** — static/local data, no backend, no real auth/billing.
- **This doc adds no recipe, routing, schema, template, or implementation.** It defines posture so the lane starts from doctrine rather than ambiguity.

---

## 2. Current baseline

| Dimension | State |
|-----------|-------|
| **Game-kit phase** | **Complete** — DOM-native game recipes/modules shipped |
| **Website-pack foundation** | **Complete** — `pack.site` exists with two recipes |
| **`site.landing-page-core`** | **Complete** — final generated gate **Pass** |
| **`site.dashboard-ui-core`** | **Complete** — read-only/static dashboard surface; final gate **Pass** |
| **Invisible orchestration** | **Complete** — OpenCode, Droid/Factory, Claude, Cursor launch seams enrich runner prompts internally |
| **CodingPlanCard UX** | **Simplified** — provider-plan/candidate presentation removed; approval mechanics preserved |
| **Default lane** | **v1** Builder Kit JSON preserved when flag is off or unset |
| **Build Registry v2** | **Opt-in** — `HAM_BUILD_REGISTRY_V2_ENABLED` off by default |
| **Build-kit internals** | **Invisible** to normal users (recipe/pack IDs, routing metadata, gate language, YAML paths, render budgets, playbook headers all hidden) |

---

## 3. Why SaaS dashboard is different from dashboard-ui-core

| Aspect | `site.dashboard-ui-core` | `app.saas-dashboard-core` (candidate) |
|--------|--------------------------|----------------------------------------|
| **Nature** | Read-only / static overview UI | App-like product workspace surface |
| **Framing** | "Look at the state" | "This is my product's logged-in home" |
| **Context** | Single page, no account model | Account / workspace / project context (placeholder) |
| **Content** | KPI cards, charts, simple table | Usage/status, activity, resource/project list, plan/upgrade affordances |
| **Navigation** | Topnav or none | App shell with sidebar/topbar |
| **Primary risk** | Component soup, fake charts | **Auth / billing / CRUD drift** — implying a real product backend |

The core difference: `site.dashboard-ui-core` answers *"can I understand the state?"*; a SaaS dashboard implies *"this is a product I log into and operate"*. That implication is exactly where scope can balloon into auth, billing, and CRUD — so the lane must be deliberately app-shell-light and static.

---

## 4. Candidate intent

A bounded `app.saas-dashboard-core` would produce a single, coherent, **app-like-but-static SaaS product home**:

- **App shell** — persistent layout with header/topbar and optional sidebar.
- **Workspace / account / project selector placeholder** — a static switcher affordance; no real account model.
- **Usage / KPI cards** — bounded headline metrics (usage, seats, quota, activity counts) with label, value, unit.
- **Plan / status card** — current plan tier and status, presented statically.
- **Activity / recent events** — a bounded recent-events list with meaningful sample entries.
- **Simple project / team / resource list** — one readable list/table of projects, members, or resources.
- **Upgrade or CTA area** — a single, non-spammy upgrade/plan prompt (no payment processing).
- **Settings / help shortcuts** — static entry points to settings/help (no real settings backend).
- **Empty / loading / error states** — for any async-looking region.
- **Responsive layout** — predictable stacking; no fixed-width or horizontal-scroll traps.
- **Accessible semantics** — landmarks, nav, main, table/list structure, labeled controls, non-color-only status.
- **Local / static sample data only** — no fetched data, no live updates.

---

## 5. Hard exclusions

These must be **explicitly out of scope** for `app.saas-dashboard-core`:

- Real auth / accounts (login, signup, sessions)
- Backend / API / database wiring
- Billing / payment management / payment processing
- Invoices / subscriptions implementation
- Admin user management
- Permissions / RBAC screens
- CRUD-heavy workflows (create/update/delete records)
- Analytics workbench / ad-hoc query / drill-down
- CRM / project management / kanban boards
- Real-time monitoring / streaming / websockets
- Fintech / trading dashboards
- Ecommerce admin
- Maps / geospatial operations

The lane is a **static, app-shaped overview**, not a functioning SaaS product.

---

## 6. SaaS dashboard IA patterns

- **App shell + sidebar/topbar** — a persistent frame that signals "product workspace" without deep routing.
- **Workspace / project context** — a static context indicator (current workspace/account/project) near the top of the shell.
- **Overview-first layout** — the landing surface summarizes account state; detail is deferred, not interleaved.
- **Usage / status cards** — a bounded top band of usage/quota/plan-status metrics.
- **Activity feed** — recent events as a scannable, bounded list.
- **Resource list** — one project/team/resource list or table for the "what do I have" question.
- **Upgrade / plan prompt** — a single, contextual upgrade affordance, not repeated CTAs.
- **Settings / help shortcuts** — quiet secondary entry points, not primary content.
- **Progressive disclosure** — summarize first; defer detail to (illustrative) deeper views rather than cramming everything onto the home surface.

---

## 7. Component taxonomy

**Core (first lane):**

- App shell
- Sidebar / topbar
- Workspace switcher placeholder
- Usage cards
- Plan / status card
- Activity feed / list
- Resource / project table or list
- Upgrade CTA
- Empty / loading / error state panels

**Deferred (later siblings):**

- Auth forms
- Billing tables
- Invoices
- User management
- RBAC screens
- CRUD forms
- Complex charts
- Real-time streams
- Workflow boards

The first lane should compose from **core components only** and avoid overpacking — emit the regions the prompt's actual SaaS-home need calls for, not every component above.

---

## 8. Anti-pattern taxonomy

| Anti-pattern | Symptom | Why it fails |
|--------------|---------|--------------|
| **Fake SaaS app with dead nav** | Sidebar/topbar links that go nowhere | Implies a product that does not exist |
| **Billing UI implying payment processing** | "Pay now" / card forms with no backend | Misleading; dangerous expectation of real payments |
| **Auth/account forms with no backend** | Login/signup forms that do nothing | Fake functionality; security-shaped slop |
| **Admin panel drift** | User management, permissions, destructive actions | Wrong lane — belongs to a future admin core |
| **CRUD sprawl** | Create/edit/delete forms everywhere | Stateful app semantics out of scope |
| **Dashboard component soup** | Every widget on the home with no IA | No coherent product-home story |
| **Meaningless metrics** | Usage/quota cards over arbitrary numbers | Non-reviewable; no domain meaning |
| **Dead filters / nav** | Controls that change nothing visible | Broken affordances |
| **Inaccessible sidebar / table structure** | No landmarks, no table headers, unlabeled nav | Excludes assistive-tech users |
| **Mobile ignored** | Fixed-width shell, horizontal scroll traps | Unusable on small screens |
| **Upgrade CTA spam** | Repeated aggressive upgrade prompts | Feels like a paywall mock, not a product home |

---

## 9. Routing ambiguity classes

| Class | Examples | Routing posture |
|-------|----------|-----------------|
| **Generic dashboard** | "build a dashboard", "dashboard UI" | **Weak alone** — do not route without clear signals |
| **Read-only dashboard overview** | "read-only KPI overview", "static metrics dashboard" | **Route to `site.dashboard-ui-core`** (existing lane) |
| **SaaS dashboard** | "SaaS product dashboard home with usage, plan, activity" | **Candidate lane** — route only if it stays static/app-shell-light (post-readiness) |
| **Admin dashboard** | "admin panel", "user management console" | **Defer** — separate admin readiness (CRUD/permissions/destructive) |
| **Analytics dashboard** | "analytics workbench", "drill-down explorer" | **Defer** — density + interactivity |
| **Billing dashboard** | "billing management", "invoices and subscriptions" | **Defer / exclude** — payment/billing implementation |
| **User portal** | "logged-in user portal", "account home" | **Future sibling** — auth/session/personal data |
| **CRM / project management** | "CRM pipeline", "kanban board", "deal tracker" | **Defer** — stateful app semantics |
| **Landing page with app screenshot** | "marketing page showing a product dashboard image" | **Route to landing lane** (`site.landing-page-core`) |
| **Backend / auth app request** | "SaaS dashboard wired to my API with login" | **Fallback / clarify** — out of static lane scope |
| **Ecommerce admin** | "store admin", "order/product management" | **Defer / exclude** — admin CRUD |

---

## 10. Generated gate expectations

A future `app.saas-dashboard-core` generated gate should check:

- App shell present **but bounded** (no deep multi-route app)
- **No real auth/backend/payment claims** — static affordances only
- Usage / status / activity / resource regions present per checklist
- **No dead nav** unless clearly illustrative (and labeled as such)
- Meaningful sample data (coherent SaaS-domain values)
- Empty / loading / error states for async-looking regions
- Responsive layout (predictable stacking; no horizontal-scroll traps)
- Semantic landmarks (`nav`, `main`), table/list structure, labeled controls
- **No CRUD / admin / billing drift**
- **No build-kit internals exposed** in generated output or copy
- Generated output stays **under `/tmp/` only** — never committed

---

## 11. Validation / testing posture

**Adopt now:**

- **Docs / research / readiness first** — this research artifact, then a readiness review.
- **Schema / reference checks later** — validate YAML, compose, render budget once schema is authored.
- **Manual generated gate** — representative SaaS-home prompts, `/tmp/` output, outcome report.
- **No-exposure tests** if/when UI work happens — keep build-kit internals invisible.

**Defer:**

- Playwright app-flow tests
- Real auth / billing / API flows
- CI-blocking generated gates
- Pixel-perfect / visual regression
- Complex accessibility automation

This mirrors the proven landing/dashboard rhythm: cheap structural checks first, automation later, nothing CI-blocking initially.

---

## 12. Relationship to admin dashboard

- **SaaS dashboard should come before admin dashboard.** A static SaaS product-home surface is a smaller, safer step than an admin backoffice.
- **Admin dashboard requires separate readiness** for CRUD, user management, permissions/RBAC, and destructive actions — none of which belong in the SaaS core.
- **Do not let SaaS core become admin core.** The moment a prompt needs real user management, permissions, or destructive CRUD, it routes to a (future, separately gated) admin lane or falls back — not to `app.saas-dashboard-core`.

---

## 13. Recommended first lane decision

**Proceed to `SAAS_DASHBOARD_CORE_READINESS_REVIEW.md`** — **only if** the lane can stay **local/static and app-shell-light** (no real auth, no backend, no billing/payment processing, no CRUD/admin drift).

**Otherwise, pause** if scope cannot stay bounded — a SaaS framing that demands auth/billing/CRUD is not a fit for a static build kit and should not be forced into one.

**Preferred recommendation:** Proceed to a readiness review, conditional on the static/app-shell-light boundary holding; if early readiness work shows the lane cannot stay bounded, stop rather than expand scope.

---

## 14. Non-goals

This research document does **not** authorize or imply:

- A recipe from this doc
- Routing from this doc
- A schema from this doc
- Backend / auth / billing work
- Admin CRUD
- Templates or starter source files
- Runtime / frontend changes
- Default Build Registry v2 enablement

---

## 15. References

- [DASHBOARD_KIT_RESEARCH.md](./DASHBOARD_KIT_RESEARCH.md)
- [DASHBOARD_BUILD_KIT_DIRECTION.md](./DASHBOARD_BUILD_KIT_DIRECTION.md)
- [DASHBOARD_UI_CORE_READINESS_REVIEW.md](./DASHBOARD_UI_CORE_READINESS_REVIEW.md)
- [DASHBOARD_UI_CORE_COMPLETION_CHECKPOINT.md](./DASHBOARD_UI_CORE_COMPLETION_CHECKPOINT.md)
- [WEBSITE_PACK_STAGE_CHECKPOINT.md](./WEBSITE_PACK_STAGE_CHECKPOINT.md)
- [NEXT_WAVE_DECISION.md](./NEXT_WAVE_DECISION.md)
- [INVISIBLE_ORCHESTRATION_CHAT_UX_CHECKPOINT.md](./INVISIBLE_ORCHESTRATION_CHAT_UX_CHECKPOINT.md)
- [STATUS.md](./STATUS.md)
