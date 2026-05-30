# Admin Dashboard Core Readiness Review

> **Readiness / ambiguity gate only · Not recipe approval · Not routing approval · Not schema · Not implementation authorization · Not runtime enablement**

Readiness and ambiguity review for the next possible dashboard sibling lane: **`app.admin-dashboard-core`**. This review defines candidate lane intent, ambiguity classes, routing signals/exclusions, scope recommendation, candidate module themes, generated gate expectations, pack-placement posture, and a readiness decision — **before** any YAML lands. It builds on [ADMIN_DASHBOARD_CORE_RESEARCH.md](./ADMIN_DASHBOARD_CORE_RESEARCH.md), the completed [SAAS_DASHBOARD_CORE_READINESS_REVIEW.md](./SAAS_DASHBOARD_CORE_READINESS_REVIEW.md), and the [DASHBOARD_PACK_STAGE_CHECKPOINT.md](./DASHBOARD_PACK_STAGE_CHECKPOINT.md). It mirrors how [SAAS_DASHBOARD_CORE_READINESS_REVIEW.md](./SAAS_DASHBOARD_CORE_READINESS_REVIEW.md) preceded `app.saas-dashboard-core` schema work.

**Review date:** 2026-05-29 (UTC)
**Latest pushed commit:** `955a8b50` — `docs(builder): add admin dashboard core research`
**Baseline:** DOM-native game-kit phase complete; website-pack foundation complete; `site.landing-page-core`, `site.dashboard-ui-core`, and `app.saas-dashboard-core` complete with final gate **Pass**; Dashboard Pack stage closed; Admin Dashboard Core research on `origin/main`; v1 default preserved; v2 opt-in behind `HAM_BUILD_REGISTRY_V2_ENABLED`.

For research see [ADMIN_DASHBOARD_CORE_RESEARCH.md](./ADMIN_DASHBOARD_CORE_RESEARCH.md). For live registry status see [STATUS.md](./STATUS.md).

**This review adds no recipe, routing, templates, schema, runtime changes, or default v2 enablement.** It is a readiness / ambiguity gate only.

---

## 1. Executive summary

- **`app.admin-dashboard-core` is ready for schema-only authoring only if scope stays static, illustrative, non-mutating, and demo-bounded.** Local mock data only, explicit demo-mode/read-only boundaries, no backing system.
- **It is higher-risk than the SaaS dashboard lane.** Admin chrome is exactly where users expect real power (user management, roles, destructive actions), so the lane must make its non-functional, demo nature unmistakable.
- **It must not imply real backend/auth/RBAC/CRUD/destructive actions.** Any control that appears to act on data must be disabled, clearly demo-mode, or explicitly non-mutating.
- **This review does not add a recipe, routing, schema, template, or implementation.** It is a readiness/ambiguity gate that defines boundaries before any schema work begins.

---

## 2. Current baseline

| Dimension | State |
|-----------|-------|
| **`site.dashboard-ui-core`** | **Complete** — read-only/static dashboard overview; final gate **Pass** |
| **`app.saas-dashboard-core`** | **Complete** — app-shell-light static SaaS product home; final gate **Pass** |
| **Dashboard Pack stage** | **Complete** — see [DASHBOARD_PACK_STAGE_CHECKPOINT.md](./DASHBOARD_PACK_STAGE_CHECKPOINT.md) |
| **Admin Dashboard Core research** | **Complete** — [ADMIN_DASHBOARD_CORE_RESEARCH.md](./ADMIN_DASHBOARD_CORE_RESEARCH.md) on `origin/main` (`955a8b50`) |
| **Default lane** | **v1** Builder Kit JSON preserved when flag is off or unset |
| **Build Registry v2** | **Opt-in** — `HAM_BUILD_REGISTRY_V2_ENABLED` off by default |
| **Build-kit internals** | **Invisible** to normal users (recipe/pack IDs, routing metadata, gate language, YAML paths, render budgets, playbook headers all hidden) |
| **Generated output** | **Not committed** — gate artifacts under `/tmp/` only |

---

## 3. Candidate lane intent

`app.admin-dashboard-core` would produce a single, coherent, **static admin control-surface prototype**:

- **Static admin shell** — persistent operator-control layout frame.
- **Sidebar / topbar** — admin navigation chrome (shallow, illustrative).
- **Overview / status cards** — bounded headline operational metrics (users, sessions, queue depth) over local sample data.
- **User / team summary** — a static count/summary of users or teams.
- **Static role / permission summary** — illustrative roles and permission groupings (display only, never editable).
- **Review / moderation queue as static display only** — a scannable list of pending items; no real workflow actions.
- **System health / status panel as static display only** — static indicators; no live monitoring.
- **Audit / activity log as static display only** — a bounded log display; not a real audit trail.
- **Resource / user table** — one readable semantic table of users/resources.
- **Demo-mode action controls** — affordances clearly marked disabled or demo-mode.
- **Danger modal mockup** — only if clearly static / non-mutating and labeled as illustrative.
- **Empty / loading / error states** — static examples for async-looking regions.
- **Responsive / accessibility semantics** — landmarks, semantic tables, labeled controls, non-color-only status.
- **Local / static mock data only** — no fetched data, no live updates.

---

## 4. Why this lane is useful

- **Completes the dashboard family progression** after `site.dashboard-ui-core` and `app.saas-dashboard-core`.
- **Supports common admin / control-plane visual requests** — a frequent ask that currently has no bounded home.
- **Teaches admin IA without real backend complexity** — users, roles, review queues, audit trails, system status as visual vocabulary.
- **Creates boundaries before admin prompts route incorrectly** — defines doctrine so admin intent does not silently drift into SaaS core or a full app.
- **Provides static prototype value without pretending to implement infrastructure** — a high-fidelity illustrative admin surface, not a working control plane.

---

## 5. Why this lane is risky

- **Auth / backend drift** — login/session/API implications creeping into the shell.
- **RBAC / permissions drift** — editable role/permission controls that imply real enforcement.
- **CRUD sprawl** — create/edit/delete forms appearing across the surface.
- **Destructive action fakery** — delete/suspend buttons that look live with no demo marking.
- **User-management drift** — real user creation/editing flows.
- **Audit-log / security theater** — logs presented as authoritative; "encrypted"/"compliant" claims.
- **Fake live monitoring** — status panels that imply real-time telemetry/log streaming.
- **Dense table soup** — unreadable data walls, div-only pseudo-tables.
- **Inaccessible disabled controls / tooltips** — dead/unlabeled disabled buttons, unreachable tooltips.
- **Admin lane becoming a full app** — multi-route stateful admin application out of static-prototype scope.

---

## 6. Hard scope recommendation

- **One static admin dashboard page.**
- **`app-shell-light` / admin-shell-light layout**, responsive.
- **Local mock data only** — no fetched data, no live updates.
- **Action controls must be demo-mode / read-only / illustrative.**
- **Destructive actions, if present, must show visible friction and never mutate real data.**
- **No real auth / login / session / JWT / OAuth.**
- **No backend / API / database.**
- **No real user create / edit / delete.**
- **No permission mutation.**
- **No RBAC implementation.**
- **No CRUD forms.**
- **No live monitoring / log streaming.**
- **No billing / payment.**
- **No production security / compliance claims.**

---

## 7. Ambiguity classes

| Class | Examples | Routing posture |
|-------|----------|-----------------|
| **Generic dashboard** | "build a dashboard", "dashboard UI" | **Weak alone** — do not route without strong combined signals |
| **SaaS dashboard / product home** | "SaaS product dashboard home with usage, plan, activity" | **Route to `app.saas-dashboard-core`** (existing lane) |
| **Admin dashboard** | "static admin dashboard preview with users, roles, audit log" | **Candidate lane** — route only if static/illustrative/demo-bounded (post-schema, post-routing-approval) |
| **User management dashboard** | "user management console with create/edit/delete" | **Defer / exclude** — real CRUD / user management |
| **Permissions / RBAC dashboard** | "role and permission editor", "RBAC management" | **Defer / exclude** — permission mutation |
| **Moderation / review dashboard** | "content moderation workflow with approve/reject actions" | **Defer / exclude** — real workflow mutation |
| **System operations dashboard** | "live ops console", "real-time system monitoring" | **Defer** — live monitoring / streaming |
| **Analytics dashboard / workbench** | "analytics workbench", "drill-down explorer" | **Defer** — density + interactivity |
| **Billing admin** | "billing management", "invoices and subscriptions admin" | **Defer / exclude** — payment/billing implementation |
| **CRM / project management** | "CRM pipeline", "kanban board", "deal tracker" | **Defer** — stateful app semantics |
| **Backend / auth app request** | "admin dashboard wired to my API with login and roles" | **Fallback / clarify** — out of static lane scope |
| **Exact clone / pixel-perfect dashboard** | "clone an existing admin panel pixel-perfect" | **Defer / exclude** — clone request |
| **Security / compliance console** | "security center", "compliance dashboard", "SOC console" | **Defer / exclude** — security/compliance theater |

---

## 8. Strong positive signals for future routing

Routing should require **combined** static-admin-preview signals, for example:

- "admin dashboard"
- "admin control panel"
- "internal operations dashboard"
- "staff / user management overview"
- "role / permission summary"
- "review queue"
- "moderation queue"
- "audit log"
- "system status"
- "resource table"
- "static / demo / read-only / local mock data"
- "no backend / no auth / no RBAC / no CRUD"

A strong route combines an admin/control-surface intent **plus** admin-domain regions (users/roles/review/audit/system) **plus** a static/demo/no-backend constraint — not a single term.

---

## 9. Weak signals that should not route alone

These terms are insufficient on their own and must not route:

- "dashboard"
- "admin"
- "users"
- "roles"
- "permissions"
- "settings"
- "security"
- "audit"
- "table"
- "operations"
- "system"
- "management"
- "control panel"

---

## 10. Explicit exclusions

The following must **not** route to `app.admin-dashboard-core` (fall back to v1, clarify, or route to the correct lane):

- Real auth / login / accounts / session / JWT / OAuth
- Real backend / API / database
- Real user creation / editing / deletion
- Permission mutation
- RBAC implementation
- CRUD-heavy workflows
- Destructive actions that mutate data
- Real moderation workflows
- Billing / payments / invoices
- Live monitoring / log streaming
- Real audit logging
- Security / compliance implementation
- Cryptographic / security tooling
- Exact clone / pixel-perfect app clone

---

## 11. Candidate module themes

Possible future modules (themes only — no YAML authored here):

**App type:**

- `app-types/app.admin-dashboard-core.yaml`

**Stack kit:**

- `stack-kits/dom-admin-dashboard-minimal.yaml`

**Sections:**

- `admin-app-shell`
- `admin-overview-status`
- `admin-user-team-summary`
- `admin-role-permission-summary`
- `admin-review-queue`
- `admin-resource-table`
- `admin-audit-log`
- `admin-system-status`
- `admin-demo-action-boundaries`
- `admin-empty-loading-error-states`
- `admin-responsive-structure`

**Components:**

- `admin-shell`
- `admin-sidebar-nav`
- `admin-topbar`
- `status-card`
- `user-summary-card`
- `role-permission-pill`
- `review-queue-table`
- `audit-log-list`
- `system-status-panel`
- `resource-index-table`
- `demo-action-control`
- `danger-modal-mockup`

**Validators (conceptual first):**

- `admin-shell-bounds`
- `no-auth-backend-claims`
- `no-rbac-implementation`
- `no-crud-mutation`
- `no-destructive-live-actions`
- `audit-log-static-bounds`
- `admin-table-semantics`
- `disabled-action-accessibility`
- `responsive-a11y-basics`
- `no-security-theater`

**Recovery playbooks:**

- `auth-backend-drift`
- `rbac-drift`
- `crud-sprawl`
- `destructive-action-drift`
- `audit-log-fakery`
- `security-theater`
- `dense-table-soup`
- `inaccessible-disabled-controls`

**Meta:**

- a `progress` label (`progress.app-admin-dashboard-core`)
- a `learning` hook (`learning.app-admin-dashboard-core`)

---

## 12. Generated quality expectations

A future `app.admin-dashboard-core` generated gate should require:

- Admin shell / sidebar / topbar present **but bounded** (no deep multi-route app)
- Overview / status / user / role / review / audit / resource / system regions present per checklist
- Semantic `header` / `nav` / `main` / table / list structure
- Meaningful local mock data (coherent admin-domain values)
- Visible empty / loading / error states
- Action controls are **demo-mode / read-only / illustrative**
- Destructive action examples **do not mutate real data**
- **No real auth / backend / API / database claims**
- **No real CRUD mutation flows**
- **No real RBAC / permission mutation**
- **No live monitoring / log streaming**
- **No security / compliance theater**
- **No disabled-button tooltip trap** (disabled controls remain accessible/explained)
- **No build-kit internals exposed** in generated output or copy
- Generated output stays **under `/tmp/` only** — never committed

---

## 13. Validation / testing posture

**Adopt now:**

- **Research / readiness before schema** — research complete; this review, then schema-only authoring.
- **Schema-only before routing** — never combine schema and routing in one step.
- **Reference checker** — `scripts/check_build_registry_references.py` (pack references, duplicates, orphans).
- **Render budget** — keep under 12k, preferably under 11.4k chars (mirrors the existing dashboard lanes).
- **Manual generated gate** — representative admin-preview prompts, `/tmp/` output, outcome report.
- **SaaS-style scaffold-quality guard likely needed if routing later** — admin-specific anti-drift checks calibrated before any route lands.
- **No-exposure tests** if UI surfaces change.

**Defer:**

- Playwright admin-flow tests
- Auth / RBAC / backend / API tests
- Destructive-action workflow tests
- CI-blocking generated gates
- Pixel regression
- Real security / compliance testing

---

## 14. Relationship to SaaS dashboard

- **SaaS dashboard is customer / product-home oriented** — it answers "this is my product workspace".
- **Admin dashboard is internal / system-control oriented** — it answers "this is where operators manage users and the system".
- **SaaS shows** usage, plan, activity, and resources for a single workspace.
- **Admin shows** users, roles, review queues, audit trails, and system status across users/systems.
- **Admin prompts must not route to SaaS core, and SaaS prompts must not route to admin core** — a single ambiguous "dashboard" term must not route to either.

---

## 15. Pack placement posture

- **Under current constraints, admin dashboard should remain a static client-side prototype** — consistent with the existing dashboard lanes.
- **It may fit `website-pack` / `pack.site`** if kept static, admin-shell-light, and non-mutating — mirroring the `app.saas-dashboard-core` placement decision, where the validator and reference checker are recipe-prefix-agnostic and `resolve_pack_root` already maps `app.*` → website-pack.
- **A future `app-pack` may be justified** if real workflows, auth, backend, permissions, multi-screen state, or destructive flows become required — but those are explicitly out of scope for a static admin-preview lane.
- **Do not create `app-pack` from this review.** Placement is a later, separately decided step, not a readiness-time action.

---

## 16. Readiness decision

- **Ready to author `app.admin-dashboard-core` schema-only next — conditionally** — only if scope stays **static, illustrative, non-mutating, and demo-bounded** (no real auth, no backend, no RBAC/CRUD, no destructive mutation, no real audit logging).
- **Not ready for routing** — routing must **not** be added in the same step as schema.
- **Not ready for real admin / RBAC / auth / backend / CRUD** — those remain deferred to separately gated lanes.
- **Generated gate required after any future routing** — the lane is not "complete" until a `/tmp/` generated gate review passes under a canonical static-admin-preview prompt.

---

## 17. Recommended next step

1. **Author `app.admin-dashboard-core` schema-only** — only if scope stays bounded (static / illustrative / non-mutating / demo-bounded).
2. **Keep render under 12k**, preferably **under 11.4k** chars.
3. **Use `website-pack` only if** static / admin-shell-light fit remains clean.
4. **Do not route** until explicit approval.
5. **Add conservative routing only after tests** — separate step, intent tests, conservative negatives; flag stays off by default.
6. **Run a generated gate review** before declaring the lane complete.

Do **not** combine schema and routing in one step.

---

## 18. Non-goals

This readiness review does **not** authorize or imply:

- A recipe from this review
- Routing from this review
- Runtime / API / frontend changes
- Backend / auth / RBAC / CRUD work
- Destructive workflows
- Templates or starter source files
- Committing generated output (artifacts stay under `/tmp/` only)

---

## 19. References

- [ADMIN_DASHBOARD_CORE_RESEARCH.md](./ADMIN_DASHBOARD_CORE_RESEARCH.md)
- [DASHBOARD_PACK_STAGE_CHECKPOINT.md](./DASHBOARD_PACK_STAGE_CHECKPOINT.md)
- [SAAS_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md](./SAAS_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md)
- [SAAS_DASHBOARD_CORE_RESEARCH.md](./SAAS_DASHBOARD_CORE_RESEARCH.md)
- [SAAS_DASHBOARD_CORE_READINESS_REVIEW.md](./SAAS_DASHBOARD_CORE_READINESS_REVIEW.md)
- [DASHBOARD_KIT_RESEARCH.md](./DASHBOARD_KIT_RESEARCH.md)
- [DASHBOARD_BUILD_KIT_DIRECTION.md](./DASHBOARD_BUILD_KIT_DIRECTION.md)
- [STATUS.md](./STATUS.md)
