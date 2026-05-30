# Admin Dashboard Core Research

> **Research / distillation only · Not readiness · Not recipe approval · Not routing approval · Not schema · Not implementation · Not runtime enablement**

Research artifact for a possible future dashboard sibling lane: **`app.admin-dashboard-core`**. This document surveys what a bounded admin dashboard core build kit could and could not cover, **before** any readiness, schema, or implementation work. It builds on [DASHBOARD_KIT_RESEARCH.md](./DASHBOARD_KIT_RESEARCH.md), [DASHBOARD_BUILD_KIT_DIRECTION.md](./DASHBOARD_BUILD_KIT_DIRECTION.md), the completed [SAAS_DASHBOARD_CORE_RESEARCH.md](./SAAS_DASHBOARD_CORE_RESEARCH.md), and the [DASHBOARD_PACK_STAGE_CHECKPOINT.md](./DASHBOARD_PACK_STAGE_CHECKPOINT.md). It mirrors how [SAAS_DASHBOARD_CORE_RESEARCH.md](./SAAS_DASHBOARD_CORE_RESEARCH.md) preceded `app.saas-dashboard-core`.

**Research date:** 2026-05-29 (UTC)
**Latest pushed commit:** `91b31cf1` — `docs(builder): add dashboard pack stage checkpoint`
**Baseline:** DOM-native game-kit phase complete; website-pack foundation complete; `site.landing-page-core`, `site.dashboard-ui-core`, and `app.saas-dashboard-core` complete with final gate **Pass**; Dashboard Pack stage closed; v1 default preserved; v2 opt-in behind `HAM_BUILD_REGISTRY_V2_ENABLED`.

For live registry status see [STATUS.md](./STATUS.md).

**This document adds no recipe, routing, schema, templates, or implementation.** It is research and distillation only.

---

## 1. Executive summary

- **`app.admin-dashboard-core` is a possible future dashboard sibling, but it is higher risk than the SaaS dashboard lane.** An admin surface implies cross-user/system control, not a single workspace home.
- **External research indicates a bounded static admin dashboard is viable** — but only as a high-fidelity static prototype, never a real admin system.
- **The lane must be static, illustrative, non-mutating, and mock-data-driven** — local sample data only, with explicit demo-mode/disabled controls.
- **The central challenge is representing an admin control surface without falsely implying real backend/auth/RBAC/CRUD/destructive actions.** Admin chrome is exactly where users expect real power; the lane must make its non-functional, demo nature unmistakable.
- **This doc adds no recipe, routing, schema, template, or implementation.** It defines posture so the lane (if pursued) starts from doctrine rather than ambiguity.

---

## 2. Current baseline

| Dimension | State |
|-----------|-------|
| **Game-kit phase** | **Complete** — DOM-native game recipes/modules shipped |
| **Website-pack foundation** | **Complete** — `pack.site` with `site.landing-page-core`, `site.dashboard-ui-core`, `app.saas-dashboard-core` (97 modules) |
| **`site.dashboard-ui-core`** | **Complete** — read-only/static dashboard overview; final gate **Pass** |
| **`app.saas-dashboard-core`** | **Complete** — app-shell-light static SaaS product home; final gate **Pass** |
| **Dashboard Pack stage** | **Complete** — see [DASHBOARD_PACK_STAGE_CHECKPOINT.md](./DASHBOARD_PACK_STAGE_CHECKPOINT.md) |
| **Default lane** | **v1** Builder Kit JSON preserved when flag is off or unset |
| **Build Registry v2** | **Opt-in** — `HAM_BUILD_REGISTRY_V2_ENABLED` off by default |
| **Build-kit internals** | **Invisible** to normal users (recipe/pack IDs, routing metadata, gate language, YAML paths, render budgets, playbook headers all hidden) |
| **Admin dashboard** | **Intentionally deferred** until this research pass — listed as a deferred lane in the Dashboard Pack stage checkpoint |

---

## 3. Why admin dashboard is different

| Aspect | `site.dashboard-ui-core` | `app.saas-dashboard-core` | `app.admin-dashboard-core` (candidate) |
|--------|--------------------------|---------------------------|-----------------------------------------|
| **Nature** | Read-only / static overview UI | App-shell-light product home | Operational control surface |
| **Framing** | "Look at the state" | "This is my product's logged-in home" | "This is where operators manage users and the system" |
| **Audience** | Anyone viewing metrics | A single customer/workspace | Internal operators/admins across users |
| **Content** | KPI cards, charts, table | Usage/plan/activity/resources | Users, roles, permissions, review queues, audit logs, system status |
| **Primary risk** | Component soup, fake charts | Auth/billing/CRUD drift | **Implying real user management, RBAC, destructive actions, audit logging, and backend/auth** |

The core difference: admin surfaces imply **cross-user and system-level management** — roles, permissions, audit logs, moderation queues, destructive actions, and backend assumptions. That is precisely where a generative static kit can produce dangerous, deceptive slop (delete buttons that look live, permission editors that pretend to work, audit logs that look authoritative). The lane must be deliberately static, demo-bounded, and explicit about its non-functional nature.

---

## 4. Viability finding

- **A bounded admin dashboard core is viable** — distilled from the external research brief.
- **It should be treated as a high-fidelity static prototype, not a real admin system.** The deliverable is an illustrative admin IA, not a working control plane.
- **It can simulate admin IA with local mock data** — semantic tables, static audit logs, illustrative roles/permissions, and demo-mode action friction that visibly does not mutate anything.
- **It must not generate live backend/API/auth/RBAC/CRUD behavior.** Any control that appears to act on data must be disabled, clearly demo-mode, or explicitly non-mutating.

---

## 5. Candidate bounded scope

A possible static/admin-preview lane would produce a single, coherent, **static admin control-surface prototype**:

- **Admin shell** — persistent layout with sidebar/topbar.
- **Overview / status cards** — bounded headline operational metrics (users, sessions, queue depth) over local sample data.
- **User / team summary** — a static count/summary of users or teams.
- **Static role / permission summary** — illustrative roles and permission groupings (display only, never editable).
- **Moderation / review queue** — a static display of pending items; no real workflow actions.
- **System health / status panel** — static status indicators; no live monitoring.
- **Audit / activity log** — a static, bounded log display; not a real audit trail.
- **Simple resource / user table** — one readable semantic table of users/resources.
- **Disabled / illustrative action controls** — buttons clearly marked disabled or demo-mode.
- **Demo-mode confirmation / danger modal examples** — only if clearly non-mutating and labeled as illustrative.
- **Empty / loading / error states** — static examples for async-looking regions.
- **Responsive layout and accessible semantics** — landmarks, semantic tables, labeled controls, non-color-only status.
- **Local / static sample data only** — no fetched data, no live updates.

---

## 6. Hard exclusions

These must be **explicitly out of scope** for `app.admin-dashboard-core`:

- Real auth / login / accounts / sessions / JWT / OAuth
- Real backend / API / database
- Real user creation / editing / deleting
- Permission mutation
- RBAC implementation
- Destructive actions that mutate data
- Real moderation workflows
- Billing / payment / invoices
- Live monitoring / log streaming
- Real audit logging
- Real admin automation
- CRUD forms
- Production security / compliance claims
- Cryptographic / security implementation
- Inaccessible disabled-button / tooltip patterns

The lane is a **static, illustrative admin control-surface prototype**, not a functioning admin system.

---

## 7. Admin dashboard IA patterns

- **Admin shell / sidebar** — a persistent frame signaling an operator control surface without deep routing.
- **Topbar / global search / profile placeholder** — static chrome; search and profile are illustrative, not functional.
- **Overview / status row** — a bounded top band of operational status/metrics.
- **User / team summary** — a static summary of who/what is managed.
- **Static roles / permissions summary** — illustrative role groupings, display only.
- **Pending review / moderation queue** — a scannable, bounded static list of items awaiting action.
- **Dense resource table** — one readable semantic table for "what is under management".
- **Audit / activity log** — recent events as a bounded, static display.
- **System health / status** — static indicators, not live telemetry.
- **Settings / security shortcuts** — quiet secondary entry points, illustrative only.
- **Disabled / illustrative actions** — action affordances that visibly do nothing or are demo-mode.
- **Progressive disclosure** — summarize first; defer detail to illustrative deeper views rather than cramming everything onto the home surface.

---

## 8. Component taxonomy

**Core (first lane):**

- Admin app shell
- Sidebar / topbar
- Status / KPI cards
- User / team summary card
- Static role / permission pills
- Review queue table
- Audit log list / table
- System status panel
- Resource index table
- Demo-mode action controls
- Empty / loading / error panels
- Danger modal mockup (only if clearly static / demo)

**Deferred (later siblings / out of scope):**

- Forms that mutate data
- Permission editors
- Real user management
- Real auth
- Backend / API / database
- Destructive workflows
- Live logs / monitoring
- Billing / admin finance
- Real security / compliance tools

The first lane should compose from **core components only** and avoid overpacking — emit the regions the prompt's actual admin-preview need calls for, not every component above.

---

## 9. Anti-pattern taxonomy

| Anti-pattern | Symptom | Why it fails |
|--------------|---------|--------------|
| **Fake working admin controls** | Buttons that look live but do nothing | Deceptive; implies real power |
| **Live-looking delete/suspend buttons** | "Delete user" / "Suspend" with no demo marking | Dangerous expectation of real destructive action |
| **Permission editor pretending to work** | Editable RBAC controls with no backing | Security-shaped slop |
| **Backend / auth claims** | Copy implying real login/sessions/API | Misleading functionality |
| **CRUD sprawl** | Create/edit/delete forms everywhere | Stateful admin semantics out of scope |
| **User-management drift** | Real user creation/editing flows | Wrong lane — belongs to a future, separately gated admin system |
| **Security theater** | "Encrypted", "compliant", "secured" claims | False security/compliance assurance |
| **Audit-log fakery** | Logs presented as authoritative records | Implies real audit trail |
| **Dense table soup** | Unreadable data walls, div-only pseudo-tables | Non-scannable; inaccessible |
| **Inaccessible disabled controls / tooltips** | Disabled buttons with no explanation or unreachable tooltips | Excludes assistive-tech users |
| **Mobile ignored** | Fixed-width admin shell, horizontal scroll traps | Unusable on small screens |
| **Admin dashboard becoming a full app** | Multi-route stateful admin application | Out of static-prototype scope |

---

## 10. Routing ambiguity classes

| Class | Examples | Routing posture |
|-------|----------|-----------------|
| **Generic dashboard** | "build a dashboard", "dashboard UI" | **Weak alone** — do not route without clear signals |
| **SaaS dashboard** | "SaaS product dashboard home with usage, plan, activity" | **Route to `app.saas-dashboard-core`** (existing lane) |
| **Admin dashboard** | "static admin dashboard preview with users, roles, audit log" | **Candidate lane** — route only if static/illustrative/demo-bounded (post-readiness, post-routing-approval) |
| **User management dashboard** | "user management console with create/edit/delete" | **Defer / exclude** — real CRUD/user management |
| **Permissions / RBAC dashboard** | "role and permission editor", "RBAC management" | **Defer / exclude** — permission mutation |
| **Moderation dashboard** | "content moderation workflow with approve/reject actions" | **Defer / exclude** — real workflow mutation |
| **System operations dashboard** | "live ops console", "real-time system monitoring" | **Defer** — live monitoring / streaming |
| **Analytics dashboard** | "analytics workbench", "drill-down explorer" | **Defer** — density + interactivity |
| **Billing admin** | "billing management", "invoices and subscriptions admin" | **Defer / exclude** — payment/billing implementation |
| **CRM / project management** | "CRM pipeline", "kanban board", "deal tracker" | **Defer** — stateful app semantics |
| **Backend / auth app request** | "admin dashboard wired to my API with login and roles" | **Fallback / clarify** — out of static lane scope |
| **Exact clone** | "clone an existing admin panel pixel-perfect" | **Defer / exclude** — clone request |

---

## 11. Generated gate expectations

A future `app.admin-dashboard-core` generated gate should check:

- Admin shell present **but bounded** (no deep multi-route app)
- Static overview / status / user / review / audit / resource regions present per checklist
- Action controls **disabled / illustrative or demo-mode only**
- **Destructive actions do not mutate data**
- **No real auth / backend / database / API claims**
- **No real CRUD mutation flows**
- **No real permissions / RBAC implementation**
- **No live monitoring / log streaming**
- Semantic `header` / `nav` / `main` / table / list structure
- Visible empty / loading / error states
- Meaningful local sample data (coherent admin-domain values)
- **No disabled-button tooltip trap** (disabled controls remain accessible/explained)
- **No build-kit internals exposed** in generated output or copy
- Generated output stays **under `/tmp/` only** — never committed

---

## 12. Accessibility and safety posture

- **Semantic tables for dense admin data** — real `<table>`/`<thead>`/`<tbody>`/`<th>`/`<td>` with caption/heading context.
- **Accessible labels / captions / headings** for every region.
- **Avoid div-soup tables** — never fake tabular data with non-semantic divs.
- **Avoid inaccessible disabled controls** — disabled affordances must be reachable and explained, not dead/unlabeled.
- **Use readable explanatory text for demo-mode limitations** — say plainly that controls are illustrative.
- **Danger / destructive actions require visible friction if included** — confirmation/danger modals must be clearly non-mutating demos.
- **Do not imply actual security enforcement** — no "secured", "compliant", or "enforced" claims.

---

## 13. Admin dashboard vs SaaS dashboard boundary

- **SaaS dashboard is customer/product-home oriented** — it answers "this is my product workspace".
- **Admin dashboard is internal/system-control oriented** — it answers "this is where operators manage users and the system".
- **SaaS shows** usage, plan, activity, and resources for a single workspace.
- **Admin shows** users, roles, review queues, audit trails, and system status across users/systems.
- **Prompts must not route interchangeably** — a workspace product home routes to `app.saas-dashboard-core`; an internal operator control surface is the (future, separately gated) admin lane. A single ambiguous "dashboard" term must not route to either.

---

## 14. App-pack vs website-pack implications

- **Under current constraints, admin dashboard should remain a static client-side prototype.** That keeps it consistent with the existing dashboard lanes.
- **It may fit `website-pack` / `pack.site`** if kept static and app-shell-light — mirroring the `app.saas-dashboard-core` placement decision (Option A), where the validator and reference checker are recipe-prefix-agnostic and `resolve_pack_root` already maps `app.*` → website-pack.
- **A future `app-pack` may be justified** if real workflows, auth, backend, permissions, or multi-screen app state become required — but those are explicitly out of scope for a static admin-preview lane.
- **Do not create an `app-pack` from this research doc.** Placement is a later, separately decided step (a pack-placement decision), not a research-time action.

---

## 15. Recommended first lane decision

**Proceed to `ADMIN_DASHBOARD_CORE_READINESS_REVIEW.md`** — **only if** the lane can stay **static, illustrative, non-mutating, and explicitly demo-bounded** (no real auth, no backend, no RBAC/CRUD, no destructive mutation, no real audit logging).

**Otherwise, pause** if a bounded static admin scope is too risky — an admin framing that demands real user management, permissions, destructive actions, or backend/auth is not a fit for a static build kit and should not be forced into one.

**Preferred recommendation:** Proceed to a readiness review **only if** the lane stays static, illustrative, non-mutating, and explicitly demo-bounded; if early readiness work shows the lane cannot stay bounded, stop rather than expand scope.

---

## 16. Non-goals

This research document does **not** authorize or imply:

- A recipe from this doc
- Routing from this doc
- A schema from this doc
- Backend / auth / RBAC work
- CRUD implementation
- Destructive workflows
- Templates or starter source files
- Runtime / frontend changes

---

## 17. References

- [DASHBOARD_PACK_STAGE_CHECKPOINT.md](./DASHBOARD_PACK_STAGE_CHECKPOINT.md)
- [SAAS_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md](./SAAS_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md)
- [SAAS_DASHBOARD_CORE_RESEARCH.md](./SAAS_DASHBOARD_CORE_RESEARCH.md)
- [SAAS_DASHBOARD_CORE_READINESS_REVIEW.md](./SAAS_DASHBOARD_CORE_READINESS_REVIEW.md)
- [DASHBOARD_KIT_RESEARCH.md](./DASHBOARD_KIT_RESEARCH.md)
- [DASHBOARD_BUILD_KIT_DIRECTION.md](./DASHBOARD_BUILD_KIT_DIRECTION.md)
- [STATUS.md](./STATUS.md)
