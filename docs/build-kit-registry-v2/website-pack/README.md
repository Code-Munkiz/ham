# Website Pack — Build Registry v2

**Status:** Schema pilot · **Pack id:** `pack.site` · **Recipes:** `site.landing-page-core` (routed when flagged) · `site.dashboard-ui-core` (routed when flagged) · `app.saas-dashboard-core` (routed when flagged) · `app.admin-dashboard-core` (schema-only, **not routed**)

Generative playbooks for DOM-native marketing/landing pages and read-only dashboard/app-surface overviews. This pack is **separate from** [game-pack/](../game-pack/) — no game mechanics, no templates, no starter source trees.

## Purpose

- Guide HAM to compose **custom** one-page marketing/landing pages from user prompts plus structured YAML modules.
- Enforce section rhythm (hero → value → features → proof → CTA → FAQ/close), accessibility basics, and anti-slop quality intent.
- Stay **schema/docs/registry only** until explicit routing approval.

## Non-template posture

- No checked-in React/Vite landing starters.
- No clone baselines of named sites.
- `non_template_statement` on every module.
- Generated output targets `/tmp/` or preview bootstrap only — never repo-native template trees.

## First recipe: `site.landing-page-core`

One-page static marketing/landing playbook:

| In scope | Out of scope |
|----------|--------------|
| Hero, value prop, feature sections, social proof, CTA, FAQ | Backend, auth, live forms, payments, CMS |
| Responsive layout + semantic headings | Dashboard, ecommerce, multi-page app routing |
| Meaningful placeholder copy (no lorem ipsum) | Template cloning, pixel-perfect brand copies |

**Routing:** see [LANDING_PAGE_CORE_READINESS_REVIEW.md](../LANDING_PAGE_CORE_READINESS_REVIEW.md) and [ROUTING_STRATEGY.md](../ROUTING_STRATEGY.md).

## Second recipe: `site.dashboard-ui-core`

Read-only / mostly static dashboard overview playbook:

| In scope | Out of scope |
|----------|--------------|
| Dashboard shell, bounded KPI row (3–5), 1–2 basic charts, simple table | Backend, auth, accounts, CRUD, payments, admin permissions |
| Optional local/static filters, empty/loading/error states | Analytics workbench, ad-hoc querying, real-time streams |
| Responsive 12-col layout + accessibility semantics | Maps/geospatial, fintech/trading order books, game HUD |
| Meaningful local sample data | Template cloning, marketing fake-dashboard screenshots |

**Routing:** narrowly routed behind `HAM_BUILD_REGISTRY_V2_ENABLED` for strict read-only dashboard intent.

## Third recipe: `app.saas-dashboard-core`

Static, app-shell-light SaaS product-home playbook (**schema-only, not routed**):

| In scope | Out of scope |
|----------|--------------|
| Bounded app shell (sidebar/topbar), workspace selector placeholder, usage cards, plan/status card | Real auth/accounts/sessions, backend/API/database |
| Recent activity feed, simple resource list/table, one upgrade CTA, settings/help shortcuts | Billing/payment processing, invoices/subscriptions implementation |
| Empty/loading/error states, responsive and semantic structure, local sample data only | Admin user management, RBAC, CRUD-heavy workflows, analytics workbench, realtime, fintech/trading, ecommerce admin, maps |

**Routing:** narrowly routed behind `HAM_BUILD_REGISTRY_V2_ENABLED` for bounded SaaS app-home intent.

## Fourth recipe: `app.admin-dashboard-core`

Static, app-shell-light admin control-surface prototype (**schema-only, not routed**):

| In scope | Out of scope |
|----------|--------------|
| Static admin shell (sidebar/topbar), overview/status cards, user/team summary, role/permission summary | Real auth/login/session/JWT/OAuth, backend/API/database |
| Static review queue, resource table, audit/activity list, system status panel | Real user CRUD, permission mutation, RBAC implementation |
| Demo-mode/read-only action controls, optional non-mutating danger modal mockup | Destructive mutation workflows, real moderation workflows |
| Empty/loading/error states, responsive semantics, local sample data only | Live monitoring/log streaming, billing/payments, security/compliance implementation, exact clone |

**Routing:** deferred by design. `app.admin-dashboard-core` is intentionally **not wired in `intent.py`** yet.

## Layout

```text
website-pack/
├── registry-pack.yaml
├── app-types/site.landing-page-core.yaml
├── app-types/site.dashboard-ui-core.yaml
├── app-types/app.saas-dashboard-core.yaml
├── app-types/app.admin-dashboard-core.yaml
├── stack-kits/dom-marketing-minimal.yaml
├── stack-kits/dom-dashboard-minimal.yaml
├── stack-kits/dom-saas-dashboard-minimal.yaml
├── stack-kits/dom-admin-dashboard-minimal.yaml
├── sections/          # indexed as mechanics for loader compatibility
├── components/
├── validators/
├── recovery/
├── progress-labels/
└── learning-hooks/
```

Section modules live under `sections/` but appear in `module_index.mechanics` until loader gains a dedicated `sections` key (see [WEBSITE_PACK_STRUCTURE_PLAN.md](../WEBSITE_PACK_STRUCTURE_PLAN.md)).

## Validation (local)

```bash
python3 -m pytest tests/test_website_pack_registry.py -q
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/website-pack \
  --app-type site.landing-page-core \
  --check
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/website-pack \
  --app-type site.dashboard-ui-core \
  --check
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/website-pack \
  --app-type app.saas-dashboard-core \
  --check
python3 scripts/validate_game_pack_registry.py \
  --pack-root docs/build-kit-registry-v2/website-pack \
  --app-type app.admin-dashboard-core \
  --check
python3 scripts/check_build_registry_references.py \
  --pack docs/build-kit-registry-v2/website-pack/registry-pack.yaml \
  --check-orphans \
  --check-render-budget
```

`validate_registry_pack()` and the reference checker both support `pack.site` with website-pack directory conventions (`sections/`, `components/`, `recovery/`).

## Related docs

- [WEBSITE_PACK_STRUCTURE_PLAN.md](../WEBSITE_PACK_STRUCTURE_PLAN.md)
- [WEBSITE_DESIGN_QUALITY_PRINCIPLES.md](../WEBSITE_DESIGN_QUALITY_PRINCIPLES.md)
- [AUTHORING_GUIDE.md](../AUTHORING_GUIDE.md) — game-pack patterns apply to module shape
