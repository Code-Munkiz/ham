# Sales Ops Dashboard Core Research

> **Research / distillation only · Not readiness · Not recipe approval · Not routing approval · Not schema · Not implementation · Not runtime enablement**

Research artifact for a new domain-specific dashboard lane: **`app.sales-ops-dashboard-core`**. This document distills an external research brief into repo-appropriate doctrine for a bounded, static sales/revenue-operations dashboard build kit — **before** any readiness, schema, or implementation work. It builds on the completed dashboard/app-surface lanes ([DASHBOARD_PACK_STAGE_CHECKPOINT.md](./DASHBOARD_PACK_STAGE_CHECKPOINT.md), [SAAS_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md](./SAAS_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md), [ADMIN_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md](./ADMIN_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md)) and mirrors how [SAAS_DASHBOARD_CORE_RESEARCH.md](./SAAS_DASHBOARD_CORE_RESEARCH.md) and [ADMIN_DASHBOARD_CORE_RESEARCH.md](./ADMIN_DASHBOARD_CORE_RESEARCH.md) preceded their lanes.

**Research date:** 2026-05-29 (UTC)
**Latest pushed commit:** `5f73e162` — `fix(builder): close admin dashboard generated quality gate`
**Baseline:** DOM-native game-kit phase complete; website-pack foundation complete; `site.dashboard-ui-core`, `app.saas-dashboard-core`, and `app.admin-dashboard-core` complete with final gate **Pass**; Dashboard Pack stage closed; v1 default preserved; v2 opt-in behind `HAM_BUILD_REGISTRY_V2_ENABLED`.

For live registry status see [STATUS.md](./STATUS.md).

**This document adds no recipe, routing, schema, templates, or implementation.** It is research and distillation only.

---

## 1. Executive summary

- **`app.sales-ops-dashboard-core` is recommended as a new domain-specific dashboard lane.** It is the first lane scoped to a concrete operational business domain rather than a generic surface shape.
- **It should cover commission sales operations, revenue recovery, agent performance, and process analytics in one broad first lane** — a unified sales/revenue-operations control surface, not several narrow lanes at once.
- **It is more domain-specific than `site.dashboard-ui-core`, `app.saas-dashboard-core`, and `app.admin-dashboard-core`.** Those are surface archetypes; this lane carries a financial/sales domain model (commissions, recovery, pipeline, exceptions).
- **It must remain static, local, and demo-bounded** — illustrative calculations over local sample data, never real payroll/payments/accounting/collections/CRM/backend behavior.
- **This doc adds no recipe, routing, schema, template, or implementation.** It defines posture so the lane (if pursued) starts from doctrine rather than ambiguity.

---

## 2. Current baseline

| Dimension | State |
|-----------|-------|
| **`site.dashboard-ui-core`** | **Complete** — read-only/static dashboard overview; final gate **Pass** |
| **`app.saas-dashboard-core`** | **Complete** — app-shell-light static SaaS product home; final gate **Pass** |
| **`app.admin-dashboard-core`** | **Complete** — static admin control-surface preview; final gate **Pass** |
| **Dashboard / app-surface stage** | **Mature** — three completed surface archetypes; mature enough to consider domain-specific lanes |
| **Default lane** | **v1** Builder Kit JSON preserved when flag is off or unset |
| **Build Registry v2** | **Opt-in** — `HAM_BUILD_REGISTRY_V2_ENABLED` off by default |
| **Build-kit internals** | **Invisible** to normal users (recipe/pack IDs, routing metadata, gate language, YAML paths, render budgets, playbook headers all hidden) |
| **Generated output** | **Not committed** — gate artifacts under `/tmp/` only |

---

## 3. Why this lane is warranted

- **Repeated client demand in commission-based sales, revenue recovery, and process analytics.** These operational surfaces recur across sales organizations, agencies, and recovery/collections-adjacent teams, and currently have no bounded home.
- **Generic dashboard kits can provide shape but not domain intelligence.** `site.dashboard-ui-core` produces a plausible overview, but it cannot express commission states, aging buckets, clawbacks, or recovery funnels with coherent domain semantics.
- **Sales ops, commission ops, and revenue recovery share UI primitives.** KPI summary rows, agent leaderboards, stage/funnel charts, aging buckets, exception queues, and dense financial tables are common across all three — one lane can serve them coherently.
- **One broad first lane avoids premature fragmentation.** Splitting into commission / recovery / process-analytics lanes before any single lane exists would multiply routing ambiguity and maintenance cost without proven demand for the splits.

---

## 4. Recommended lane decision

- **Proceed with one broad `app.sales-ops-dashboard-core` lane first.** A single unified sales/revenue-operations surface that can emit commission, recovery, agent-performance, and process-analytics regions as the prompt calls for them.
- **Do not split immediately into commission / recovery / process-analytics lanes.** Keep one lane until real usage shows the splits are warranted.
- **Future siblings may be justified later, each via its own research/readiness:**
  - `app.commission-dashboard-core`
  - `app.revenue-recovery-dashboard-core`
  - `app.sales-process-analytics-core`

These siblings are **candidates only**; this research does not approve them.

---

## 5. Candidate bounded scope

A possible static sales-ops lane would produce a single, coherent, **static sales/revenue-operations control-surface prototype**:

- **Sales ops shell** — persistent operations layout (sidebar/topbar), illustrative chrome only.
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

## 6. Core metrics and data model

Illustrative metric vocabulary the lane may express over **local sample data only**:

**Sales performance:**

- gross sales
- net sales
- qualified leads
- calls / contacts / appointments
- close rate
- conversion rate
- average deal size
- pipeline stage movement
- agent activity

**Commission operations:**

- commission earned
- commission pending
- clawbacks / chargebacks
- payout status

**Revenue recovery:**

- recovered dollars
- recoverable balance
- recovery rate
- aging buckets
- case status

**Process analytics:**

- forecast vs actual
- cycle time
- exception count

**Data model notes:**

- Sample data should be **internally coherent** — totals, rates, and breakdowns must reconcile so the surface reads as plausible.
- **No real PII** — no real names, contacts, or customer identities.
- **No real financial identifiers** — no real account, card, routing, or payout identifiers.
- **Illustrative calculations only** — commission/recovery math is demonstrative, not authoritative.
- Mock relationships **may** link **closed deals → commission payout → recovery status** to show domain coherence, but only as illustrative, non-authoritative sample relationships.

---

## 7. Information architecture patterns

- **Top KPI / summary row** — bounded headline metrics first.
- **Agent leaderboard** — ranked static performance summary.
- **Pipeline / recovery funnel or stage chart** — illustrative progression visualization.
- **Aging / recovery buckets** — static distribution display.
- **Commission / payout status region** — earned/pending/clawback/chargeback and payout state, display only.
- **Exception queue** — bounded list of items requiring attention.
- **Process bottleneck panel** — cycle-time / bottleneck indicators.
- **Dense account / case / resource table** — one readable semantic table for "what is under management".
- **Activity / audit timeline** — recent events as a bounded, static display.
- **Filters and date range controls** — illustrative scoping by date/team/agent/status/stage.

Apply **progressive disclosure** — summarize first, defer detail to illustrative deeper views rather than cramming every region onto the home surface.

---

## 8. Component taxonomy

**Core (first lane):**

- Sales ops shell
- KPI summary cards
- Agent leaderboard
- Pipeline stage chart
- Recovery aging table
- Commission summary card
- Payout status table
- Case / recovery queue
- Activity feed
- Process bottleneck panel
- Filter / date range controls
- Exception queue
- Semantic financial table
- Empty / loading / error panels

**Deferred (later siblings / out of scope):**

- Payroll engine
- Payment processing
- Accounting ledger
- ASC 606 engine
- Legal collections workflow
- CRM sync
- Live telephony / auto-dialer
- Bank / payment integrations
- Commission contract engine
- Tax reporting
- Regulated financial advice

The first lane should compose from **core components only** and avoid overpacking — emit the regions the prompt's actual sales-ops need calls for, not every component above.

---

## 9. Hard exclusions

These must be **explicitly out of scope** for `app.sales-ops-dashboard-core`:

- Real payroll
- Payment processing
- Accounting ledger / ASC 606 calculation
- Legal collections automation
- Live CRM / database / API
- Real bank / account / payment identifiers
- Real customer PII
- Tax / accounting claims
- Real compliance certification claims
- Live dunning execution
- Telephony / SMS automation
- Regulated financial advice
- Real payout approval or disbursement
- Backend / API / database integrations

The lane is a **static, illustrative sales/revenue-operations prototype**, not a functioning financial or collections system.

---

## 10. Safety and compliance boundaries

- **Local / static sample data only** — no fetched data, no live updates.
- **Illustrative calculations only** — no authoritative financial computation.
- **No real PII** — no real customer or agent identities.
- **No real account / payment identifiers** — no real card/bank/routing/payout numbers.
- **No real payroll / payment / accounting / legal claims** — nothing that implies real money movement or legal effect.
- **Clear sample / demo framing where financial results appear** — financial figures are visibly illustrative.
- **Avoid aggressive collections language** — no threatening, coercive, or dunning-style copy.
- **Avoid gamified employee surveillance** — no invasive monitoring framing.
- **Use outcome-based sales metrics rather than invasive tracking** — measure results, not keystroke/behavioral surveillance.
- **No claims of legal / compliance correctness** — the surface makes no regulatory assurances.

---

## 11. Anti-pattern taxonomy

| Anti-pattern | Symptom | Why it fails |
|--------------|---------|--------------|
| **Generic revenue dashboard with meaningless KPIs** | Random numbers labeled as revenue/commission | No domain coherence; reads as slop |
| **Fake payment / payout processing** | "Process payout" / "Pay agent" buttons that look live | Deceptive; implies real money movement |
| **Fake compliance claims** | "ASC 606 compliant", "SOC2", "audit-ready" copy | False regulatory assurance |
| **Overprecise commission math without source rules** | Exact commission figures with no stated rule basis | Implies authoritative payroll/accounting |
| **Live collections workflow fakery** | Dunning steps / "send to collections" actions that look real | Implies live legal/collections automation |
| **Sensitive PII in mock data** | Real-looking SSNs, card numbers, customer names | Privacy risk; out of scope |
| **Gamified agent surveillance** | Invasive activity tracking / leaderboards as monitoring | Harmful framing; surveillance, not outcomes |
| **Misleading recovery forecasts** | Confident recovery predictions presented as fact | Overstates illustrative projections |
| **Dashboard component soup** | Every region crammed in with no hierarchy | Non-scannable; unfocused |
| **Dead filters** | Filter controls that do nothing | Implies interactivity that is absent |
| **Inaccessible dense tables** | Div-only pseudo-tables, no headers/captions | Excludes assistive-tech users |
| **Mobile ignored** | Fixed-width ops shell, horizontal scroll traps | Unusable on small screens |
| **Fake CRM / payment / accounting integrations** | "Connected to Salesforce / Stripe / QuickBooks" copy | Implies real backend integration |

---

## 12. Routing ambiguity classes

| Class | Examples | Routing posture |
|-------|----------|-----------------|
| **Generic sales dashboard** | "build a sales dashboard" | **Weak alone** — do not route without sales-ops domain signals |
| **Sales ops dashboard** | "sales operations dashboard with agent performance and pipeline" | **Candidate lane** — route only if static/local/demo-bounded (post-readiness, post-routing-approval) |
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

---

## 13. Relationship to existing dashboard kits

- **`site.dashboard-ui-core`** = generic read-only dashboard overview (surface shape; KPI/chart/table).
- **`app.saas-dashboard-core`** = customer / product-home SaaS surface ("this is my product workspace").
- **`app.admin-dashboard-core`** = internal admin / control-plane surface ("this is where operators manage users and the system").
- **`app.sales-ops-dashboard-core`** = internal RevOps / sales / recovery / commission **operational** surface ("this is where the sales/revenue operation is run and measured").

It **overlaps visually with admin** (internal operator surface, dense tables, queues, activity feeds) but **differs by domain model** — it carries a financial/sales/recovery vocabulary (commissions, clawbacks, aging, recovery funnels, pipeline) that admin does not. Prompts must not route interchangeably between admin and sales-ops on shape alone.

---

## 14. Pack placement recommendation

- **Keep in `website-pack` / `pack.site` initially** if the lane stays static, local, and demo-bounded — mirroring the `app.saas-dashboard-core` and `app.admin-dashboard-core` placement decisions, where the validator and reference checker are recipe-prefix-agnostic and `resolve_pack_root` already maps `app.*` → website-pack.
- **A future `app-pack` or domain pack may be justified only if** real workflows, backend integration, CRM sync, payment/payroll/accounting logic, or multi-screen app state become required — all of which are explicitly out of scope for a static sales-ops-preview lane.
- **Do not create a new pack from this research doc.** Placement is a later, separately decided step (a pack-placement decision), not a research-time action.

---

## 15. Generated gate recommendations

A future `app.sales-ops-dashboard-core` generated gate should require:

- Sales / recovery / commission domain regions present (per the prompt's actual need)
- Meaningful local sample data (coherent, internally reconciling values)
- Agent / team / activity / pipeline / recovery / commission regions present as appropriate
- Semantic `header` / `nav` / `main` / table / list / chart structure
- Visible empty / loading / error states
- **No backend / API / live CRM / payment / payroll / accounting integrations**
- **No sensitive PII**
- **No fake payment processing**
- **No fake compliance claims**
- **No real collections automation**
- **No build-kit internals exposed** in generated output or copy
- Generated output stays **under `/tmp/` only** — never committed

---

## 16. Recommended next step

- **Proceed to `SALES_OPS_DASHBOARD_CORE_READINESS_REVIEW.md`** — **only if** the lane can stay **static, local, and demo-bounded** (no real payroll/payments/accounting/collections/CRM/backend).
- **Do not author schema yet.** Schema work follows a readiness/ambiguity gate.
- **Do not split into multiple lanes yet.** Keep one broad lane until usage justifies siblings.
- **Do not route anything yet.** Routing follows schema and a route-approval step.

If early readiness work shows the lane cannot stay static/local/demo-bounded, **stop** rather than expand scope into real financial/collections systems.

---

## 17. Non-goals

This research document does **not** authorize or imply:

- A recipe from this doc
- Routing from this doc
- A schema from this doc
- Backend / API / CRM / payment / payroll / accounting work
- Legal collections automation
- Templates or starter source files
- Runtime / frontend changes

---

## 18. References

- [DASHBOARD_PACK_STAGE_CHECKPOINT.md](./DASHBOARD_PACK_STAGE_CHECKPOINT.md)
- [SAAS_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md](./SAAS_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md)
- [ADMIN_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md](./ADMIN_DASHBOARD_CORE_COMPLETION_CHECKPOINT.md)
- [SAAS_DASHBOARD_CORE_RESEARCH.md](./SAAS_DASHBOARD_CORE_RESEARCH.md)
- [ADMIN_DASHBOARD_CORE_RESEARCH.md](./ADMIN_DASHBOARD_CORE_RESEARCH.md)
- [STATUS.md](./STATUS.md)
