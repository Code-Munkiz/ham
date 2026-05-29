# SaaS Dashboard Core Readiness Review

> **Readiness / ambiguity gate only · Not recipe approval · Not routing approval · Not schema · Not implementation authorization · Not runtime enablement**

Readiness and ambiguity review for the next dashboard sibling lane: **`app.saas-dashboard-core`**. This review defines candidate lane intent, ambiguity classes, routing signals/exclusions, scope recommendation, candidate module themes, generated gate expectations, pack-placement posture, and a readiness decision — **before** any YAML lands. It builds on [SAAS_DASHBOARD_CORE_RESEARCH.md](./SAAS_DASHBOARD_CORE_RESEARCH.md), [DASHBOARD_KIT_RESEARCH.md](./DASHBOARD_KIT_RESEARCH.md), [DASHBOARD_BUILD_KIT_DIRECTION.md](./DASHBOARD_BUILD_KIT_DIRECTION.md), and the completed [DASHBOARD_UI_CORE_COMPLETION_CHECKPOINT.md](./DASHBOARD_UI_CORE_COMPLETION_CHECKPOINT.md).

**Review date:** 2026-05-29 (UTC)
**Latest pushed commit:** `13c4dfc5` — `docs(builder): add saas dashboard core research`
**Baseline:** DOM-native game-kit phase complete; website-pack foundation complete; `site.landing-page-core` and `site.dashboard-ui-core` complete with final gate **Pass**; SaaS dashboard research on `origin/main`; invisible orchestration provider seams complete; v1 default preserved; v2 opt-in behind `HAM_BUILD_REGISTRY_V2_ENABLED`.

For research see [SAAS_DASHBOARD_CORE_RESEARCH.md](./SAAS_DASHBOARD_CORE_RESEARCH.md). For live registry status see [STATUS.md](./STATUS.md).

**This review adds no recipe, routing, templates, schema, runtime changes, or default v2 enablement.** It is a readiness / ambiguity gate only.

---

## 1. Executive summary

**`app.saas-dashboard-core` is recommended as the next dashboard sibling — only if scope stays bounded.**

- It should be a **local/static, app-shell-light SaaS product home** — an app-shaped overview surface, not a functioning SaaS product.
- It is **more app-like than `site.dashboard-ui-core`** (app shell, account/project context, usage/plan affordances) but **must not become admin, billing, auth, or CRUD**.
- It should be **authored schema-only next** if scope stays tight (static, no backend/auth/billing/CRUD) and routing remains deferred.
- **This review does not add a recipe, routing, schema, template, or implementation.** It is a readiness/ambiguity gate that defines boundaries before schema work begins.

---

## 2. Current baseline

| Dimension | State |
|-----------|-------|
| **Game-kit phase** | **Complete** — DOM-native game recipes/modules shipped |
| **Website-pack foundation** | **Complete** — `pack.site` active |
| **`site.landing-page-core`** | **Complete** — final gate **Pass** |
| **`site.dashboard-ui-core`** | **Complete** — read-only/static dashboard; final gate **Pass** (render 11,358 chars) |
| **SaaS dashboard research** | **Complete** — [SAAS_DASHBOARD_CORE_RESEARCH.md](./SAAS_DASHBOARD_CORE_RESEARCH.md) on `origin/main` (`13c4dfc5`) |
| **Invisible orchestration** | **Complete** — OpenCode, Droid/Factory, Claude, Cursor launch seams |
| **CodingPlanCard UX** | **Simplified** — provider-plan/candidate presentation removed; approval mechanics preserved |
| **Default lane** | **v1** Builder Kit JSON preserved when flag is off or unset |
| **Build Registry v2** | **Opt-in** — `HAM_BUILD_REGISTRY_V2_ENABLED` off by default |
| **Generated output** | **Not committed** — gate artifacts under `/tmp/` only |
| **Build-kit internals** | **Invisible** to normal users |

---

## 3. Candidate lane intent

`app.saas-dashboard-core` would produce a single, coherent, **app-like-but-static SaaS product home**:

- **App shell** — persistent layout frame.
- **Sidebar / topbar** — product-workspace navigation chrome (shallow).
- **Workspace / account / project selector placeholder** — static switcher affordance; no real account model.
- **Usage / KPI cards** — bounded headline metrics (usage, seats, quota) with label, value, unit.
- **Plan / status card** — current plan tier and status, presented statically.
- **Recent activity feed** — a bounded recent-events list with meaningful sample entries.
- **Simple project / team / resource list** — one readable list/table.
- **Single upgrade / CTA area** — one non-spammy upgrade/plan prompt (no payment processing).
- **Settings / help shortcuts** — static, illustrative entry points (no real settings backend).
- **Empty / loading / error state examples** — for any async-looking region.
- **Responsive layout** — predictable stacking; no fixed-width or horizontal-scroll traps.
- **Accessible semantics** — landmarks, nav, main, table/list structure, labeled controls, non-color-only status.
- **Local / static sample data only** — no fetched data, no live updates.

---

## 4. Why this lane is useful

- **Bridges static dashboard UI and richer app surfaces** — a natural step up from `site.dashboard-ui-core` without jumping to full apps.
- **Proves app-shell composition without backend complexity** — exercises shell + sidebar/topbar + context in isolation.
- **Teaches SaaS-specific IA** — usage, plan/status, activity, resources — the vocabulary later app lanes reuse.
- **Safer than admin dashboard** — no CRUD, user management, permissions, or destructive actions.
- **Establishes anti-drift gates before CRUD/auth/billing** — calibrates auth/billing/admin/CRUD drift detectors against a bounded surface first.

---

## 5. Why this lane is risky

- **Auth / account drift** — login/signup/session implications creeping into the shell.
- **Billing / payment drift** — upgrade CTA sliding into payment processing or card capture.
- **CRUD sprawl** — create/edit/delete forms appearing across the surface.
- **Admin dashboard drift** — user management, permissions, destructive actions.
- **Fake dead nav / app shell** — sidebar/topbar links that go nowhere and imply a real product.
- **Meaningless SaaS metrics** — usage/quota cards over arbitrary numbers.
- **Upgrade CTA spam** — repeated aggressive prompts (paywall-mock feel).
- **Inaccessible sidebar / table / list structure** — missing landmarks, headers, labels.
- **Mobile ignored** — fixed-width shell, horizontal scroll traps.
- **Too much app state** — drifting toward a stateful application rather than a static overview.

---

## 6. Hard scope recommendation

| Element | Recommendation |
|---------|----------------|
| **Page count** | One static SaaS dashboard page |
| **Layout** | App-shell-light, responsive |
| **Real auth** | **None** |
| **Backend / API / database** | **None** |
| **Billing / payment processing** | **None** |
| **Invoices / subscriptions implementation** | **None** |
| **User management** | **None** |
| **Permissions / RBAC** | **None** |
| **CRUD forms** | **None** |
| **Analytics workbench** | **None** |
| **Real-time systems** | **None** |
| **Maps / geospatial** | **None** |
| **Trading / fintech** | **None** |
| **Ecommerce admin** | **None** |

---

## 7. Ambiguity classes

| Class | Examples | Routing posture |
|-------|----------|-----------------|
| **Generic dashboard** | "build a dashboard", "dashboard UI" | **Weak alone** — do not route without strong combined signals |
| **Read-only dashboard overview** | "read-only KPI overview", "static metrics dashboard" | **Route to `site.dashboard-ui-core`** (existing lane) |
| **SaaS dashboard / product home** | "SaaS product dashboard home with usage, plan, activity" | **Candidate lane** — route only if static/app-shell-light (post-readiness, post-routing-approval) |
| **Admin dashboard** | "admin panel", "user management console" | **Defer / do not route** — separate admin readiness |
| **Billing dashboard** | "billing management", "invoices and subscriptions" | **Defer / exclude** — payment/billing implementation |
| **User portal** | "logged-in user portal", "account home" | **Future sibling** — auth/session/personal data |
| **Analytics dashboard** | "analytics workbench", "drill-down explorer" | **Defer** — density + interactivity |
| **CRM / project management** | "CRM pipeline", "kanban board", "deal tracker" | **Defer** — stateful app semantics |
| **Landing page with app screenshot** | "marketing page showing a product dashboard image" | **Route to landing lane** (`site.landing-page-core`) |
| **Backend / auth app request** | "SaaS dashboard wired to my API with login" | **Fallback / clarify** — out of static lane scope |
| **Ecommerce admin** | "store admin", "order/product management" | **Defer / exclude** — admin CRUD |
| **Fintech / trading dashboard** | "trading dashboard", "order book", "live prices" | **Defer** — density + liveness |
| **Settings / account page** | "account settings page", "profile/preferences form" | **Defer / clarify** — settings backend / form semantics out of static lane scope |

---

## 8. Strong positive signals for future routing

Routing should require **combined** SaaS-product-home signals, for example:

- "SaaS dashboard"
- "product dashboard"
- "app home"
- "workspace dashboard"
- "usage cards"
- "plan / status card"
- "recent activity"
- "project / resource list"
- "upgrade CTA"
- "settings / help shortcuts"
- "static / local sample data"
- "no backend / no auth / no billing"

A strong route combines an app-home/product-workspace intent **plus** usage/plan **and** activity/resource signals **plus** a static/no-backend constraint — not a single term.

---

## 9. Weak signals that should not route alone

These terms are insufficient on their own and must not route:

- "dashboard"
- "app"
- "SaaS"
- "portal"
- "account"
- "billing"
- "analytics"
- "users"
- "settings"
- "metrics"
- "usage"
- "project"
- "workspace"
- "admin"

---

## 10. Explicit exclusions

The following must **not** route to `app.saas-dashboard-core` (fall back to v1, clarify, or route to the correct lane):

- Real auth / accounts
- Backend / API / database
- Billing / payment management
- Invoices / subscriptions
- Admin user management
- Permissions / RBAC
- CRUD-heavy workflows
- Analytics workbench / ad-hoc queries
- CRM / kanban / project management
- Real-time monitoring
- Fintech / trading / order books
- Ecommerce admin
- Maps / geospatial operations
- Exact clone / pixel-perfect app clone

---

## 11. Candidate module themes

Possible future modules (themes only — no YAML authored here):

**App type:**

- `app-types/app.saas-dashboard-core.yaml`

**Stack kit:**

- `stack-kits/dom-saas-dashboard-minimal.yaml`

**Sections:**

- `saas-app-shell`
- `saas-workspace-context`
- `saas-usage-summary`
- `saas-plan-status`
- `saas-activity-feed`
- `saas-resource-list`
- `saas-upgrade-cta`
- `saas-empty-loading-error-states`
- `saas-responsive-structure`

**Components:**

- `components/app-shell`
- `components/sidebar-nav`
- `components/topbar`
- `components/workspace-switcher`
- `components/usage-card`
- `components/plan-status-card`
- `components/activity-item`
- `components/resource-list`
- `components/upgrade-card`
- `components/settings-shortcut`

**Validators (conceptual first):**

- `app-shell-bounds`
- `no-auth-backend-claims`
- `no-billing-implementation`
- `usage-data-meaningful`
- `activity-feed-bounded`
- `resource-list-readable`
- `no-admin-crud-drift`
- `responsive-a11y-basics`
- `no-dead-nav-deception`

**Recovery playbooks:**

- `auth-drift`
- `billing-drift`
- `admin-drift`
- `crud-sprawl`
- `dead-nav-shell`
- `meaningless-saas-metrics`
- `upgrade-cta-spam`

**Meta:**

- a `progress` label (`progress.app-saas-dashboard-core`)
- a `learning` hook (`learning.app-saas-dashboard-core`)

---

## 12. Generated quality expectations

A future `app.saas-dashboard-core` generated gate should require:

- App shell present **but bounded** (no deep multi-route app)
- Usage / status / activity / resource regions present per checklist
- Meaningful sample data (coherent SaaS-domain values)
- One clear upgrade / CTA area (not repeated/spammy)
- Settings / help shortcuts illustrative and **not deceptive**
- Empty / loading / error states represented
- Responsive layout (predictable stacking; no horizontal-scroll traps)
- Semantic `header` / `nav` / `main` / list / table structure
- **No real auth / backend / payment claims**
- **No CRUD / admin / billing drift**
- **No dead nav pretending to work**
- **No build-kit internals exposed** in generated output or copy
- Generated output stays **under `/tmp/` only** — never committed

---

## 13. Validation / testing posture

**Adopt now:**

- **Research / readiness before schema** — this review, then schema-only authoring.
- **Schema-only before routing** — never combine schema and routing in one step.
- **Reference checker** — `scripts/check_build_registry_references.py` (pack references, duplicates, orphans).
- **Render budget** — keep under 12k, preferably under 11.4k chars (mirrors `site.dashboard-ui-core` at 11,358).
- **Manual generated gate** — representative SaaS-home prompts, `/tmp/` output, outcome report.
- **No-exposure guardrails** if UI surfaces change.

**Defer:**

- Playwright app-flow tests
- Real auth / billing / API tests
- CI-blocking generated gates
- Pixel regression
- Complex accessibility automation

---

## 14. Relationship to future admin dashboard

- **SaaS dashboard should not absorb admin dashboard.** The static SaaS product-home surface is a smaller, safer step.
- **Admin dashboard requires separate research / readiness** — it is not a sub-feature of this lane.
- **Admin needs CRUD, users, roles, permissions, destructive actions, and audit trails** — none of which belong in the SaaS core.
- **Do not route admin prompts to SaaS core** — admin intent falls back or routes to a future, separately gated admin lane.

---

## 15. Readiness decision

- **Ready to author `app.saas-dashboard-core` schema-only next — conditionally** — only if scope stays **local/static and app-shell-light** (no real auth, no backend, no billing/payment, no CRUD/admin drift).
- **Not ready for routing** — routing must **not** be added in the same step as schema.
- **Not ready for admin / billing / auth / CRUD** — those remain deferred to separately gated lanes.
- **Generated gate required after any future routing** — the lane is not "complete" until a `/tmp/` generated gate review passes under the canonical SaaS-home prompt.

---

## 16. Recommended next step

1. **Author `app.saas-dashboard-core` schema-only** (no routing).
2. **Keep render under 12k**, preferably **under 11.4k** chars.
3. **Validate website/app pack placement decision before authoring** (see pack-placement note below).
4. **Do not route** until explicit approval.
5. **Add conservative routing only after tests** — separate PR, intent tests, conservative negatives; flag stays off by default.
6. **Run a generated gate review** before declaring the lane complete.

Do **not** combine schema and routing in one PR.

**Pack-placement note:**

- Decide whether this belongs in the existing `website-pack/` as an app-like site lane, or in a future `app-pack/`.
- **Recommended for now:** keep in `website-pack/` **only if** loader/checker conventions (`--pack` / `--pack-root`, app-type/stack-kit/section/component layout) support an `app.*` recipe cleanly **and** scope remains static/app-shell-light. **Otherwise pause and plan an `app-pack`** rather than forcing an app-surface lane into the site pack. Resolve this placement before authoring schema.

---

## 17. Non-goals

This readiness review does **not** authorize or imply:

- A recipe from this review
- Routing from this review
- Runtime / API / frontend changes
- Backend / auth / billing work
- Admin CRUD
- Templates or starter source files
- Committing generated output (artifacts stay under `/tmp/` only)
- Default Build Registry v2 enablement

---

## 18. References

- [SAAS_DASHBOARD_CORE_RESEARCH.md](./SAAS_DASHBOARD_CORE_RESEARCH.md)
- [DASHBOARD_KIT_RESEARCH.md](./DASHBOARD_KIT_RESEARCH.md)
- [DASHBOARD_BUILD_KIT_DIRECTION.md](./DASHBOARD_BUILD_KIT_DIRECTION.md)
- [DASHBOARD_UI_CORE_READINESS_REVIEW.md](./DASHBOARD_UI_CORE_READINESS_REVIEW.md)
- [DASHBOARD_UI_CORE_COMPLETION_CHECKPOINT.md](./DASHBOARD_UI_CORE_COMPLETION_CHECKPOINT.md)
- [WEBSITE_PACK_STAGE_CHECKPOINT.md](./WEBSITE_PACK_STAGE_CHECKPOINT.md)
- [NEXT_WAVE_DECISION.md](./NEXT_WAVE_DECISION.md)
- [INVISIBLE_ORCHESTRATION_CHAT_UX_CHECKPOINT.md](./INVISIBLE_ORCHESTRATION_CHAT_UX_CHECKPOINT.md)
- [STATUS.md](./STATUS.md)
