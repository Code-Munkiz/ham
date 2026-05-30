# Sales Ops Dashboard Core Readiness Review

> **Readiness / ambiguity gate only · Not recipe approval · Not routing approval · Not schema · Not implementation authorization · Not runtime enablement**

Readiness and ambiguity review for the next domain-specific dashboard lane: **`app.sales-ops-dashboard-core`**. This review defines candidate lane intent, ambiguity classes, routing signals/exclusions, scope recommendation, candidate module themes, generated gate expectations, pack-placement posture, and a readiness decision — **before** any YAML lands. It builds on [SALES_OPS_DASHBOARD_CORE_RESEARCH.md](./SALES_OPS_DASHBOARD_CORE_RESEARCH.md), the completed dashboard/app-surface lanes ([DASHBOARD_PACK_STAGE_CHECKPOINT.md](./DASHBOARD_PACK_STAGE_CHECKPOINT.md), [SAAS_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md](./SAAS_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md), [ADMIN_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md](./ADMIN_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md)), and mirrors how [SAAS_DASHBOARD_CORE_READINESS_REVIEW.md](./SAAS_DASHBOARD_CORE_READINESS_REVIEW.md) and [ADMIN_DASHBOARD_CORE_READINESS_REVIEW.md](./ADMIN_DASHBOARD_CORE_READINESS_REVIEW.md) preceded their lanes.

**Review date:** 2026-05-29 (UTC)
**Latest pushed commit:** `0d51665a` — `docs(builder): add sales ops dashboard core research`
**Baseline:** DOM-native game-kit phase complete; website-pack foundation complete; `site.dashboard-ui-core`, `app.saas-dashboard-core`, and `app.admin-dashboard-core` complete with final gate **Pass**; Sales Ops Dashboard Core research on `origin/main`; v1 default preserved; v2 opt-in behind `HAM_BUILD_REGISTRY_V2_ENABLED`.

For research see [SALES_OPS_DASHBOARD_CORE_RESEARCH.md](./SALES_OPS_DASHBOARD_CORE_RESEARCH.md). For live registry status see [STATUS.md](./STATUS.md).

**This review adds no recipe, routing, templates, schema, runtime changes, or default v2 enablement.** It is a readiness / ambiguity gate only.

---

## 1. Executive summary

- **`app.sales-ops-dashboard-core` is ready for schema-only authoring only if scope stays static, local, and demo-bounded.** Local mock data only, illustrative calculations, explicit sample/demo framing on financial results, no backing system.
- **It is the first domain-specific dashboard lane.** Unlike the completed surface archetypes, it carries a financial/sales/recovery domain model (commissions, clawbacks, aging, recovery funnels, pipeline).
- **It should cover commission sales operations, revenue recovery, agent performance, and process analytics in one broad lane** — a unified RevOps control surface, not several narrow lanes at once.
- **It must not become payroll, payments, accounting, CRM, legal collections, or regulated financial software.** Any financial or operational affordance must be illustrative, not authoritative.
- **This review does not add a recipe, routing, schema, template, or implementation.** It is a readiness/ambiguity gate that defines boundaries before any schema work begins.

---

## 2. Current baseline

| Dimension | State |
|-----------|-------|
| **`site.dashboard-ui-core`** | **Complete** — read-only/static dashboard overview; final gate **Pass** |
| **`app.saas-dashboard-core`** | **Complete** — app-shell-light static SaaS product home; final gate **Pass** |
| **`app.admin-dashboard-core`** | **Complete** — static admin control-surface preview; final gate **Pass** |
| **Sales Ops Dashboard Core research** | **Complete** — [SALES_OPS_DASHBOARD_CORE_RESEARCH.md](./SALES_OPS_DASHBOARD_CORE_RESEARCH.md) on `origin/main` (`0d51665a`) |
| **Default lane** | **v1** Builder Kit JSON preserved when flag is off or unset |
| **Build Registry v2** | **Opt-in** — `HAM_BUILD_REGISTRY_V2_ENABLED` off by default |
| **Build-kit internals** | **Invisible** to normal users (recipe/pack IDs, routing metadata, gate language, YAML paths, render budgets, playbook headers all hidden) |
| **Generated output** | **Not committed** — gate artifacts under `/tmp/` only |

---

## 3. Candidate lane intent

`app.sales-ops-dashboard-core` would produce a single, coherent, **static sales/revenue-operations control-surface prototype**:

- **Static sales/revenue operations dashboard** — one bounded operational surface, not a multi-screen app.
- **Sales ops shell** — persistent operations layout frame (sidebar/topbar), illustrative chrome only.
- **Executive summary row** — bounded headline operational metrics (gross/net sales, close rate, commission, recovery).
- **Agent / team performance** — static leaderboard / performance summary.
- **Sales activity metrics** — calls/contacts/appointments and activity volume over local sample data.
- **Pipeline / stage movement** — illustrative funnel or stage-progression chart.
- **Commission summary** — earned / pending / clawback / chargeback views as display only.
- **Pending / earned / chargeback / clawback views** — bounded commission-state breakdowns.
- **Recovery summary** — recoverable balance and recovered dollars over sample data.
- **Recoverable balance and recovered dollars** — illustrative recovery totals.
- **Aging buckets** — static aging distribution (e.g., 0–30 / 31–60 / 61–90 / 90+).
- **Exception / review queue** — static, scannable list of items needing attention; no real workflow actions.
- **Process bottleneck panel** — illustrative cycle-time / bottleneck display.
- **Activity / audit feed** — bounded static event list; not a real audit trail.
- **Filters by date / team / agent / status / stage** — illustrative filter controls.
- **Visible empty / loading / error states** — static examples for async-looking regions.
- **Semantic tables / lists / charts** — real `<table>` structure and accessible chart/list markup.
- **Local / static sample data only** — no fetched data, no live updates.

---

## 4. Why this lane is useful

- **Repeated client demand in commission-based sales, revenue recovery, and process analytics.** These operational surfaces recur across sales organizations, agencies, and recovery-adjacent teams, and currently have no bounded home.
- **Generic dashboard kits provide structure but not domain intelligence.** `site.dashboard-ui-core` produces a plausible overview, but it cannot express commission states, aging buckets, clawbacks, or recovery funnels with coherent domain semantics.
- **Creates reusable RevOps domain primitives.** Agent leaderboards, commission summaries, aging buckets, exception queues, and pipeline charts become composable playbook vocabulary.
- **Avoids rebuilding the same agent/commission/recovery dashboard patterns repeatedly.** One lane captures the shared UI primitives across sales ops, commission ops, and revenue recovery.
- **One broad lane avoids premature fragmentation.** Splitting into commission / recovery / process-analytics lanes before any single lane exists would multiply routing ambiguity and maintenance cost.

---

## 5. Why this lane is risky

- **Payroll drift** — commission/payout language creeping into real payroll computation or disbursement.
- **Payment-processing drift** — "process payout" / "pay agent" affordances that look live.
- **Accounting / ASC 606 drift** — revenue recognition, ledger, or accounting-engine claims.
- **Legal collections automation drift** — dunning steps, "send to collections" actions, or coercive collections language.
- **CRM / API / backend drift** — "connected to Salesforce" / live pipeline sync / database claims.
- **Real PII exposure** — real-looking customer names, contacts, or financial identifiers in mock data.
- **Fake compliance claims** — "ASC 606 compliant", "SOC2", "audit-ready" copy.
- **Overprecise commission math without source rules** — exact commission figures with no stated rule basis.
- **Aggressive collections language** — threatening, coercive, or dunning-style copy.
- **Gamified employee surveillance** — invasive activity tracking / leaderboards as monitoring.
- **Misleading recovery forecasts** — confident recovery predictions presented as fact.
- **Dense financial table accessibility risks** — div-only pseudo-tables, missing headers/captions, unreadable data walls.

---

## 6. Hard scope recommendation

- **One static / local / demo-bounded RevOps dashboard page.**
- **Sales-ops-shell-light layout**, responsive.
- **Local mock data only** — no fetched data, no live updates.
- **Illustrative calculations only** — no authoritative financial computation.
- **No real payroll.**
- **No payment processing.**
- **No accounting ledger / ASC 606 engine.**
- **No legal collections automation.**
- **No CRM sync.**
- **No backend / API / database.**
- **No real bank / account / payment identifiers.**
- **No real customer PII.**
- **No tax / accounting / compliance certification claims.**
- **No live dunning / telephony / SMS automation.**
- **No regulated financial advice.**
- **No real payout approval or disbursement.**

---

## 7. Ambiguity classes

| Class | Examples | Routing posture |
|-------|----------|-----------------|
| **Generic sales dashboard** | "build a sales dashboard" | **Weak alone** — do not route without strong combined sales-ops domain signals |
| **Sales ops dashboard** | "sales operations dashboard with agent performance and pipeline" | **Candidate lane** — route only if static/local/demo-bounded (post-schema, post-routing-approval) |
| **Commission dashboard** | "commission tracking dashboard with earned/pending/clawbacks" | **Candidate lane** — within the broad sales-ops lane initially |
| **Revenue recovery dashboard** | "revenue recovery dashboard with aging and recovered dollars" | **Candidate lane** — within the broad sales-ops lane initially |
| **Collections dashboard** | "collections dashboard with cases and aging" | **Candidate (display only)** — static recovery summary; **exclude** live dunning/legal automation |
| **CRM dashboard** | "CRM dashboard synced to my pipeline" | **Defer / exclude** — live CRM sync / backend |
| **Finance dashboard** | "finance dashboard with revenue and expenses" | **Defer** — generic finance; not sales-ops domain unless clearly sales/commission/recovery framed |
| **Accounting / payroll system** | "payroll system", "accounting ledger app" | **Exclude** — real payroll/accounting computation |
| **Payment processing app** | "process payments", "payout disbursement" | **Exclude** — real payment processing |
| **Admin dashboard** | "internal admin/control-panel with users, roles, audit" | **Route to `app.admin-dashboard-core`** (existing lane) |
| **SaaS dashboard** | "SaaS product home with usage, plan, activity" | **Route to `app.saas-dashboard-core`** (existing lane) |
| **Trading / fintech dashboard** | "trading terminal", "live market/portfolio dashboard" | **Defer / exclude** — real-time fintech/trading |
| **Legal collections automation** | "automated dunning / send-to-collections workflow" | **Exclude** — live legal/collections automation |
| **Executive revenue dashboard** | "executive revenue dashboard with KPIs and forecasts" | **Weak alone** — may overlap dashboard-ui unless sales-ops/commission/recovery signals present |
| **Sales process analytics** | "sales process analytics with bottlenecks and cycle time" | **Candidate lane** — within the broad sales-ops lane initially |

---

## 8. Strong positive signals for future routing

Routing should require **combined** static-sales-ops signals, for example:

- "sales ops dashboard"
- "commission dashboard"
- "revenue recovery dashboard"
- "agent performance"
- "sales activity tracking"
- "commission earned / pending"
- "clawbacks / chargebacks"
- "payout status display"
- "recoverable balance"
- "recovered dollars"
- "aging buckets"
- "recovery queue"
- "process bottlenecks"
- "pipeline stage movement"
- "local / static / sample / demo data"
- "no payments / no payroll / no accounting / no backend / no CRM / no legal collections"

A strong route combines a sales-ops/revenue-operations intent **plus** domain regions (agent/commission/recovery/pipeline) **plus** a static/local/demo/no-backend constraint — not a single term.

---

## 9. Weak signals that should not route alone

These terms are insufficient on their own and must not route:

- "sales"
- "dashboard"
- "finance"
- "revenue"
- "agents"
- "pipeline"
- "commissions"
- "recovery"
- "collections"
- "analytics"
- "process"
- "activity"
- "leaderboard"
- "payout"

---

## 10. Explicit exclusions

The following must **not** route to `app.sales-ops-dashboard-core` (fall back to v1, clarify, or route to the correct lane):

- Real payroll
- Payment processing
- Accounting ledger / ASC 606 calculation
- Legal collections automation
- Live CRM / database / API
- Real bank / account / payment identifiers
- Real customer PII
- Tax / accounting claims
- Compliance certification claims
- Live dunning execution
- Telephony / SMS automation
- Regulated financial advice
- Real payout approval or disbursement
- Backend / API / database integrations
- Trading / order-book / financial market dashboards

---

## 11. Candidate module themes

Possible future modules (themes only — no YAML authored here):

**App type:**

- `app-types/app.sales-ops-dashboard-core.yaml`

**Stack kit:**

- `stack-kits/dom-sales-ops-dashboard-minimal.yaml`

**Sections:**

- `sales-ops-shell`
- `sales-executive-summary`
- `sales-agent-performance`
- `sales-activity-metrics`
- `sales-pipeline-stage-movement`
- `commission-summary`
- `commission-payout-status`
- `revenue-recovery-summary`
- `recovery-aging-buckets`
- `recovery-exception-queue`
- `process-bottleneck-panel`
- `sales-activity-feed`
- `sales-ops-filters`
- `sales-ops-empty-loading-error-states`
- `sales-ops-responsive-structure`

**Components:**

- `sales-ops-shell`
- `kpi-summary-card`
- `agent-leaderboard`
- `pipeline-stage-chart`
- `recovery-aging-table`
- `commission-summary-card`
- `payout-status-table`
- `case-recovery-queue`
- `activity-feed`
- `process-bottleneck-card`
- `date-range-filter`
- `exception-queue`
- `semantic-financial-table`

**Validators (conceptual first):**

- `sales-ops-domain-coverage`
- `no-payroll-payment-claims`
- `no-accounting-compliance-engine`
- `no-legal-collections-automation`
- `no-crm-api-backend-claims`
- `no-sensitive-pii`
- `financial-table-semantics`
- `coherent-sample-financial-data`
- `no-gamified-surveillance`
- `responsive-a11y-basics`

**Recovery playbooks:**

- `payroll-payment-drift`
- `accounting-compliance-drift`
- `collections-automation-drift`
- `crm-api-drift`
- `pii-drift`
- `meaningless-sales-metrics`
- `inaccessible-financial-table`
- `dead-filter-drift`

**Meta:**

- a `progress` label (`progress.app-sales-ops-dashboard-core`)
- a `learning` hook (`learning.app-sales-ops-dashboard-core`)

---

## 12. Generated quality expectations

A future `app.sales-ops-dashboard-core` generated gate should require:

- Sales / recovery / commission domain regions present (per the prompt's actual need)
- Meaningful local sample data (coherent, internally reconciling values)
- Agent / team / activity / pipeline / recovery / commission regions present as appropriate
- Commission / recovery / agent metrics are **internally coherent**
- Semantic `header` / `nav` / `main` / table / list / chart structure
- Visible empty / loading / error states
- **No backend / API / live CRM / payment / payroll / accounting integrations**
- **No sensitive PII**
- **No fake payment processing**
- **No fake compliance claims**
- **No real collections automation**
- **No aggressive collections language**
- **No gamified surveillance**
- **No build-kit internals exposed** in generated output or copy
- Generated output stays **under `/tmp/` only** — never committed

---

## 13. Validation / testing posture

**Adopt now:**

- **Research / readiness before schema** — research complete; this review, then schema-only authoring.
- **Schema-only before routing** — never combine schema and routing in one step.
- **Reference checker** — `scripts/check_build_registry_references.py` (pack references, duplicates, orphans).
- **Render budget** — keep under 12k, preferably under 11.4k chars (mirrors the existing dashboard lanes).
- **Generated gate before completion** — representative sales-ops prompts, `/tmp/` output, outcome report.
- **Likely domain-specific scaffold-quality guard if routing later** — sales-ops-specific anti-drift checks calibrated before any route lands.
- **No-exposure tests** if UI surfaces change.

**Defer:**

- Real CRM / payment / payroll / accounting tests
- Legal collections workflow tests
- Backend / API tests
- CI-blocking generated gates
- Pixel regression
- Real compliance validation

---

## 14. Relationship to existing dashboard kits

- **`site.dashboard-ui-core`** = generic read-only dashboard overview (surface shape; KPI/chart/table).
- **`app.saas-dashboard-core`** = customer / product-home SaaS surface ("this is my product workspace").
- **`app.admin-dashboard-core`** = internal admin / control-plane surface ("this is where operators manage users and the system").
- **`app.sales-ops-dashboard-core`** = internal RevOps / sales / recovery / commission **operational** surface ("this is where the sales/revenue operation is run and measured").

It **overlaps visually with admin** (internal operator surface, dense tables, queues, activity feeds) but **differs by financial/sales/recovery domain model** — commissions, clawbacks, aging, recovery funnels, pipeline. Prompts must not route interchangeably between admin and sales-ops on shape alone, or between sales-ops and dashboard-ui on generic "revenue dashboard" terms alone.

---

## 15. Pack placement posture

- **Under current constraints, sales ops should remain a static client-side prototype** — consistent with the existing dashboard lanes.
- **It may fit `website-pack` / `pack.site`** if kept static, local, demo-bounded, and non-transactional — mirroring the `app.saas-dashboard-core` and `app.admin-dashboard-core` placement decisions, where the validator and reference checker are recipe-prefix-agnostic and `resolve_pack_root` already maps `app.*` → website-pack.
- **A future `app-pack` or domain pack may be justified** if real CRM sync, payroll, payment, accounting, backend, or multi-screen workflow support becomes required — but those are explicitly out of scope for a static sales-ops-preview lane.
- **Do not create a new pack from this review.** Placement is a later, separately decided step, not a readiness-time action.

---

## 16. Readiness decision

- **Ready to author `app.sales-ops-dashboard-core` schema-only next — conditionally** — only if scope stays **static, local, and demo-bounded** (no real payroll/payments/accounting/collections/CRM/backend, no real PII, illustrative calculations only).
- **Not ready for routing** — routing must **not** be added in the same step as schema.
- **Not ready for real payroll / payment / accounting / CRM / legal collections / backend** — those remain deferred to separately gated lanes or real app infrastructure.
- **Generated gate required after any future routing** — the lane is not "complete" until a `/tmp/` generated gate review passes under a canonical static-sales-ops prompt.

---

## 17. Recommended next step

1. **Author `app.sales-ops-dashboard-core` schema-only** — only if scope stays bounded (static / local / demo-bounded).
2. **Keep render under 12k**, preferably **under 11.4k** chars.
3. **Use `website-pack` only if** static / domain-dashboard fit remains clean.
4. **Do not route** until explicit approval.
5. **Add conservative routing only after tests** — separate step, intent tests, conservative negatives; flag stays off by default.
6. **Run a generated gate review** before declaring the lane complete.

Do **not** combine schema and routing in one step. Do **not** split into commission / recovery / process-analytics lanes yet.

---

## 18. Non-goals

This readiness review does **not** authorize or imply:

- A recipe from this review
- Routing from this review
- Runtime / API / frontend changes
- Backend / CRM / payment / payroll / accounting work
- Legal collections automation
- Templates or starter source files
- Committing generated output (artifacts stay under `/tmp/` only)

---

## 19. References

- [SALES_OPS_DASHBOARD_CORE_RESEARCH.md](./SALES_OPS_DASHBOARD_CORE_RESEARCH.md)
- [DASHBOARD_PACK_STAGE_CHECKPOINT.md](./DASHBOARD_PACK_STAGE_CHECKPOINT.md)
- [SAAS_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md](./SAAS_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md)
- [ADMIN_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md](./ADMIN_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md)
- [SAAS_DASHBOARD_CORE_RESEARCH.md](./SAAS_DASHBOARD_CORE_RESEARCH.md)
- [ADMIN_DASHBOARD_CORE_RESEARCH.md](./ADMIN_DASHBOARD_CORE_RESEARCH.md)
- [STATUS.md](./STATUS.md)
