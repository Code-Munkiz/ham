# HAM Builder Platform North Star — Aspirational Product Direction

**Status:** Product vision and phased roadmap intent. **Not** shipped architecture.

- **Shipped pillars and Hermes/Droid/context roles** remain authoritative in **[`VISION.md`](../VISION.md)** (maintained per `.cursor/rules/vision-sync.mdc`).
- **`PRODUCT_DIRECTION.md`** captures near-term workspace direction; this doc holds the longer-horizon **Builder Platform** phased story without turning `PRODUCT_DIRECTION` into a roadmap.
- **Naming:** repository titles often use **Ham** (codebase identity); **HAM** denotes the **product** control plane in prose below.

**Separation:**

```txt
North Star = everything HAM should eventually become
Roadmap    = phased path to get there
MVP        = first practical slice (Builder Blueprint Mode — Phase 1)
```

**Orthogonality:** Phases **1–5** in this doc are the **Builder Platform** track. They do **not** replace or rename workspace/export/media phases in [`HAM_ROADMAP.md`](HAM_ROADMAP.md) (Phase 2B–2G, etc.).

**Cursor / doc prompts:** When extending this north star, include **Builder Space UX Direction** (below) as the preferred interface model for the **prototype / app-builder** portion. Make clear it is **HAM-native** and does **not** replace the whole Workspace. **Lock-in:** HAM Builder should feel like a **persistent app/product Space**, not just a chat thread.

---

## Core north star

HAM should become a **Last Mile Builder / Enterprise Product Orchestrator**:

A 100% vibe-coding experience where an end user describes the app or product they want, and HAM turns that into a production-grade, shippable application.

Product promise:

```txt
The user vibes the product.
HAM handles the engineering rigor.
```

HAM should feel like Manus / AI Studio / Cursor-style vibe building, but more powerful because HAM owns orchestration, architecture, QA, security, approval gates, deployment, rollback, and evidence.

---

## Terminology (product vs implementation vs execution)

**Product-level**

```txt
HAM orchestrates end-to-end.
```

**Implementation-level** (unchanged from `VISION.md`)

```txt
Hermes remains the supervisory core.
```

**Execution-level**

```txt
Cursor, Factory/Droid, OpenRouter, Comfy/media workers, GitHub, Vercel, Cloud Run, databases, and future providers are workers/adapters.
```

Do not rewrite Hermes as a generic chat model. Do not collapse the existing shipped architecture in `VISION.md` into aspirational backlog language.

---

## Full engineering rigor HAM should eventually own

### Discovery and architecture

HAM should eventually support:

- requirements discovery
- missing decision prompts
- product brief generation
- architecture blueprinting
- ADRs for material decisions
- monorepo vs multirepo evaluation
- repository strategy
- API lifecycle planning
- technical debt strategy
- data model planning
- auth/RBAC planning
- tenancy model planning
- integration planning
- documentation strategy

### Implementation core

HAM should coordinate or produce:

- frontend implementation
- backend services
- database/schema/migrations
- auth/RBAC implementation
- multi-tenancy implementation
- API contracts
- background jobs/workers
- file/storage flows
- seed/demo data
- documentation pipeline
- generated previews
- production-ready code organization

### Quality and security

HAM should enforce or orchestrate:

- unit tests
- integration tests
- e2e tests
- security review
- RBAC/tenant isolation review
- dependency hygiene
- secret hygiene
- accessibility compliance / WCAG-oriented checks
- performance benchmarking
- production readiness checks
- future enterprise modules for penetration testing and chaos engineering

### Operations and infrastructure

HAM should support:

- Infrastructure as Code planning/provisioning
- deployment orchestration
- environment readiness checks
- secret readiness checks
- database migration planning
- rollback mechanisms
- observability setup:
  - metrics
  - logging
  - tracing
  - alerts
- cost optimization / cost visibility
- feature flag strategy
- release engineering
- CI/CD provider integration

### Governance and compliance

HAM should support:

- compliance-oriented checklists
- audit trail generation
- evidence bundle compilation
- acceptance checklist validation
- approval gates before destructive actions
- approval gates before commit/deploy
- deploy and rollback evidence
- future enterprise integrations for:
  - legal review
  - regulatory compliance automation
  - security/compliance scanners

### Lifecycle management

HAM should eventually support:

- release lifecycle management
- feature flag lifecycle
- technical debt tracking
- repository strategy recommendations
- API lifecycle management
- data lifecycle planning
- knowledge retention
- architecture history
- end-of-life planning

---

## How HAM should work

HAM acts as the product orchestration/control plane:

```txt
HAM Builder
  → requirements / decision discovery
  → blueprint creation
  → ADRs
  → repository strategy
  → choose worker/backend
  → choose local vs cloud execution path
  → stream progress
  → show diffs/files/logs/preview
  → run tests/security/accessibility/compliance checks
  → validate acceptance criteria
  → ask for approval with evidence
  → deploy/ship with governance
  → produce evidence bundle
  → monitor post-deployment signals
  → preserve knowledge and decisions
```

HAM stays the boss at the product/control-plane level. Hermes remains the implementation supervisory core where existing architecture says so. Providers are workers/adapters.

---

## Interchangeable worker backends

HAM should eventually orchestrate:

- Cursor Cloud Agents
- Cursor SDK local/sidecar
- Factory AI / Droid
- OpenRouter models
- local tools
- GitHub
- Vercel
- Cloud Run
- Supabase / Neon / Postgres
- BigQuery
- Comfy/media workers
- CI/CD providers
- observability platforms
- compliance automation tools
- future providers

The user should experience one consistent HAM workflow regardless of which backend performs the work.

---

## Additional ecosystem capability layers

These layers are **long-term ecosystem capabilities**. They do **not** all belong in Phase 1. **Phase 1 remains Builder Blueprint Mode.**

Each subsection is aspirational intent—**not** shipped architecture—and must be read together with **`VISION.md`** (shipped pillars) and the **Guardrails** section of this doc.

---

### Orchestration and supervision layer

```txt
HAM orchestrates at the product/control-plane level.
Hermes supervises within the implementation architecture per VISION.md.
Providers are workers/adapters.
```

HAM coordinates (at the product level) user intent, requirements discovery, architecture and ADRs, worker selection, task planning, execution monitoring, QA/security review, approval gates, evidence generation, deploy/rollback workflows, and knowledge retention—with Hermes fulfilling the supervisory role described in shipped architecture where applicable. This parallels **How HAM should work** above; ecosystem framing here emphasizes durable **Mission Control–style coordination** across workers (operations, telemetry, approvals, evidence surfaces) without replacing pillar ownership in `VISION.md`.

---

### Local Autopilot and full machine control layer

HAM Desktop should eventually support a **Local Autopilot** posture for operators who choose deeper automation **on their own machine**. Frame as **user-controlled autonomy**, not universal defaults—security stance is **profile-based**.

#### Worker orchestration vs local autopilot

HAM should not try to perform all **heavy development** work directly on behalf of the user. HAM should **orchestrate** the best available **worker** for the job.

**Heavy development** (large code changes, multi-file refactors, repo-wide implementation missions, long-running agentic coding) should be routed to execution backends such as **Cursor Cloud Agents**, **Factory/Droid**, **Cursor SDK / local sidecar**, **Claude Code**, or **future coding workers**—each behind policy, approvals, and telemetry as the product matures.

**HAM Local Autopilot Runner** (this layer) should focus on **local machine and local workflow** work: environment setup, CLI execution, service startup, browser/UI smoke checks, local file operations, test/build commands, log collection, artifact cleanup, and evidence gathering—bounded by the active **trust profile**.

**Product principle:**

```txt
HAM routes heavy development to specialized workers.
HAM handles local friction directly when the user grants the appropriate trust profile.
```

Suggested **trust profiles** (conceptual—not a shipped schema):

```txt
Locked Down
Balanced
Local Autopilot
Unattended Local Runner
Developer Lab / Unsafe Local
```

HAM Desktop may eventually evolve toward richer **local-only** leverage: controlled browser workflows; guarded native automation; bounded file/script operations where policy allows; form assistance; readable page state; repeatable workflows (including scheduled repeats); connectors where safer than raw UI automation; optional **user-approved** credential surfaces (vault / OS keychain class integrations, later and policy-gated); and workflows that honor **hosted web UI cannot touch the bare machine**—intents cross a **user-approved paired local desktop bridge** only.

**Autonomy and visibility principle:**

```txt
The user owns the machine.
The user chooses how much autonomy HAM has.
HAM makes the trust level visible, revocable, and auditable.
```

Guardrails that should remain visible even under permissive local profiles:

- local execution remains **paired** unless an explicit unattended mode is deliberately enabled and surfaced
- **kill switch**, active-control indicators, revocation, bounded audit of sensitive actions
- **no provider secrets** exposed to browsers or unmanaged cloud workers without policy
- **hosted web UI** forwards **intent** through an approved desktop bridge—not direct machine control from the SPA alone

Detailed roadmap labels for this layer (track-level; evaluate before promoting to repo-wide anchors):

```txt
HAM_LOCAL_AUTOPILOT_MODE
HAM_USER_CONTROLLED_SECURITY_PROFILES
HAM_DESKTOP_FULL_MACHINE_CONTROL
HAM_BROWSER_WORKFLOW_AUTOMATION
HAM_LOCAL_WORKFLOW_RUNNER
```

Aligns conceptually with a **local-control lane** orthogonal to Phase 1 Builder Blueprint; merges with broader Builder timelines only when deliberately scoped.

---

### Perception and visual audit layer

HAM should eventually add a perception layer capable of inspecting UI state, previews, screenshots, artifacts, layout/contrast/accessibility cues, supporting both **private/local review** (default for sensitive workflows) and **optional cloud-backed review** governed by organizational policy where enabled.

Possible capabilities:

- screenshot / page-state review, UI regression compares, WCAG-oriented layout/contrast helpers, accessibility review, preview validation before ship, structured **visual evidence** capture, artifact inspection tied to approvals, page-state narration during sanctioned local workflows

**Local/private default:** keep sensitive visual captures and embeddings **local by default**. Do **not** send sensitive screenshots or visual memory payloads to hosted vision providers unless the operator **explicitly** enables outbound review and understands retention/export rules. Separate **HAM_LOCAL_VISUAL_AUDIT**-class tooling from optional **HAM_CLOUD_VISUAL_GROUNDING**. Treat snapshots as evidence with retention/delete controls front and center.

**Agentic Vision reference:** [Agentic Vision](https://github.com/agentralabs/agentic-vision) (`agentralabs/agentic-vision`) is a **named reference/integration candidate**, not shipped HAM software. Evaluate for local/private screenshot memory, visual embeddings, similarity/compare, recalled UI contexts, MCP-oriented visual tooling, and internal audit reproducibility—but **HAM_LOCAL_VISUAL_MEMORY_REFERENCE** posture remains exploratory until hardened.

Suggested track labels:

```txt
HAM_PERCEPTION_LAYER
HAM_LOCAL_VISUAL_AUDIT
HAM_CLOUD_VISUAL_GROUNDING
HAM_WCAG_VISUAL_GUARDRAILS
HAM_AGENTIC_VISION_REFERENCE
HAM_LOCAL_VISUAL_MEMORY_REFERENCE
```

---

### Worker adapter layer (provider-agnostic)

Concrete examples already appear under **[Interchangeable worker backends](#interchangeable-worker-backends)**. HAM stays **worker-adapter–centric**: interchangeable **worker adapters**, **execution backends**, and **provider adapters** routed through HAM—not “teams” nomenclature. Extend the eventual matrix with scanners, compliance tooling, observability backends, automation hosts, optional **social/comms/research adapters**, and niche providers as integrations mature—all behind policy + approval gates consistent with Hermes-forward supervision (`VISION.md`). **Spaces-style UX** inspirations map to **[Builder Space UX direction](#builder-space-ux-direction)**—build natively inside HAM, isolate generated apps to **iframes/worktrees**, and keep agents executing as **workers/adapters** per existing guardrails.

---

### Infrastructure and artifact layer

Plan for durable **artifact and evidence storage**, **project/build outputs**, bounded **mission/workflow logs**, **rollback metadata**, and auditable fingerprints—eventually backed by combinations of GCP/GCS-class object storage (when deployed), Postgres-style tenant stores, CI artifacts, filesystem sandboxes for dev/local runs, Git/GitHub providers, CDN or Vercel-class hosts, telemetry metadata, and BigQuery/analytics tiers when policy allows—with **HAM-native retention and export** surfaced to operators.

**Naming:** Prefer **artifact and evidence storage**, **mission logs**, **durable artifact layer** language—avoid informal “industrial storage” shorthand.

---

### Auth, tenant, and access layer

Production-grade journeys require disciplined auth/RBAC/multi-tenant design: providers such as Clerk or comparable stacks, isolation between orgs/projects, designed roles & invites, per-worker/per-provider scopes, secret readiness dashboards, audited admin tooling. Cross-reference: **database, auth, RBAC, tenant isolation, deployment assumptions must be explicitly confirmed or intentionally deferred** ([Guardrails](#guardrails)).

---

### Billing, ledger, and usage metering layer

Introduce eventual **HAM_USAGE_LEDGER** concepts: aggregated **HAM_PROVIDER_COST_VISIBILITY**, **HAM_MISSION_COST_TRACKING**, per-project/per-org metering, prepaid **credit / fuel–style gauges**, surfaced spend estimates ahead of pricey runs with optional budget caps—not “token arbitrage.” UI may eventually emphasize **HAM_CREDIT_FUEL_GAUGE** dashboards (running tally, runway warnings, receipts). Monetization sequencing depends on metering maturity.

#### Priority sequencing: usage ledger near-term, autopilot layered on telemetry

Treat the **Usage Ledger** as a **near-term infrastructure track**, not solely a distant billing feature. As HAM routes work across **OpenRouter**, **Cursor**, **Factory/Droid**, **Comfy/media**, and other execution backends, HAM needs **cost visibility before broad multi-agent execution scales.**

**Suggested execution order:**

1. **Usage Ledger MVP first**
   - track provider, model, worker, mission stage, tokens, estimated or actual cost **per invocation** where attribution is available
   - aggregate by mission, project, org, and operator/user as policy allows
   - surface mission cost and configured budget/status in Builder and Operations (even before full monetization UX)

2. **LLM Cost Autopilot second** (consumes ledger data)
   - recommend lower-cost tiers when profiles allow
   - route low-risk or draft-class tasks toward policy-acceptable economy models where quality gates pass
   - reserve premium tiers for architecture, adversarial-sensitive review, final acceptance gates, etc.
   - enforce budget guardrails, escalation, and audited overrides using live ledger totals—never “drive blind.”

Product principle:

> Before HAM automates expensive multi-agent work, HAM should make cost **visible, measurable, and governable**.

#### LLM Cost Autopilot and intelligent model routing

**LLM Cost Autopilot** describes a future layer that monitors, predicts, and helps steer LLM/provider spend across Builder, dashboard chat, Operations, agents, media, and allied workflows **without** implying lossless shortcuts or unmanaged “free” hopping between models. Spend becomes a visible input to orchestration alongside quality and reliability.

**HAM** should eventually include capabilities such as:

- token or usage-unit tracking aggregated across providers
- per-invocation attribution: model/workflow/stage/agent (where applicable), input/output sizing, estimated cost where pricing metadata exists and **reported spend** when billed data is wired
- **mission-level**, **project-level**, and **org-level** aggregates in the **usage ledger**
- real-time cost / fuel readouts surfaced in Builder and Operations
- breakdowns by stage, worker/agent, model, provider, and artifact/content class
- pre-run estimates (with **confidence ranges** where pricing or token counts are fuzzy)
- **warnings** ahead of unusually expensive models, workers, or media pipelines
- **budget guardrails**: per-run, project, org, user/credit envelopes; tiers such as advisory warnings (e.g. **50 %**, **80 %**, **95 %**) of configured allowances; escalation or approval before overspend paths; graceful shift to cheaper **policy-allowed** models when thresholds fire; configurable **hard stop** behaviors; audited trails on overrides/floor exceptions

##### Intelligent model router

HAM should eventually support **cost-aware** **intelligent model routing** atop today’s routing primitives—not a brittle “always cheapest,” not “magic routing,” no promise of effortless quality neutrality.

Conceptual routing flow:

```txt
User or worker task
  → task classifier
  → model capability matrix
  → cost / quality / risk policy
  → chosen model/provider
  → usage ledger entry
  → feedback signals (latency, escalation, evaluator notes)
```

The router aims to select the **most cost-conscious model/provider pairing that satisfies the configured reliability, correctness, safety, and policy threshold** for each task—not unbounded penny-pinching—and to:

- classify task modality and nominal complexity tiers
- separate low-risk drafts or summarization sketches from hardened security, architecture gates, extraction with compliance sensitivity, polish/creative extremes, acceptance reviews
- prefer modest-cost models where policy allows simpler work; reserve capable models where failure cost is dominant
- keep context windows disciplined (summarize/compact thoughtfully; recommend safe prompt/context compression—not blind truncation)
- **escalate** to stronger tiers when telemetry or verifier confidence flags regressions or repeated poor outcomes (with safeguards against runaway escalation spend)
- support provider/model **fallbacks**
- honor **explicit human overrides**
- ingest historical spend and outcome summaries for iterative tuning—including controlled evaluation cohorts (**A/B** or offline evaluation harnesses)—without claiming instantaneous optimality

**Budget guardrails (summary):**

- surfaced caps at run/project/org/user granularity; escalating warnings vs approval gates vs hard stops-as-configured
- optional **graceful degradation** pathways that still obey policy—not silent quality collapse
- **audit record** tying overrides/adjustments back to approvals and ledger entries for Builder/Operations reviewers

##### UI implications

Builder and Operations UX may evolve to include:

- live mission/run cost indicators
- projected totals with ranges for uncertain legs
- per-provider/per-model/per-worker decomposition
- remaining credits vs configured budgets (**fuel gauge** affordances already described above)
- expensive-step confirmations
- short natural-language rationales—for example noting that policy routes a sketch pass to an economy tier while reserving a reviewer tier later
- summarized cost excerpts packaged into mission evidence bundles

##### Relationship to explicit model picking today

HAM already ships curated **catalog** data (for example **`GET /api/models`**, OpenRouter-aligned rows plus display-only cousins) so users can manually pick composer models—for example **`WorkspaceOpenRouterModelPicker`** drives explicit selection. Those flows remain authoritative for **today’s** dashboards: user-chosen upstream model ids.

The future LLM Cost Autopilot would extend that stack with policy-aware estimation, surfaced recommendations, telemetry-rich routing, automated guardrails aligned to budgets—all **optional overlays** respecting operator defaults and approvals.

Track labels tying this subsection to metering work:

```txt
HAM_LLM_COST_AUTOPILOT
HAM_INTELLIGENT_MODEL_ROUTER
HAM_COST_QUALITY_ROUTING
HAM_USAGE_LEDGER
HAM_MISSION_COST_TRACKING
HAM_PROVIDER_COST_VISIBILITY
```

---

### Builder / Workspace / Operations UX layer

Maintain the distinctions already embodied in **[Builder Space UX direction](#builder-space-ux-direction)** plus an **operations / Mission Control plane** emphasis:

```txt
HAM Workspace = operator console
HAM Builder Space = vibe-building / prototype-to-product surface
Operations = execution monitoring, approvals, telemetry, evidence
```

Future affordances might include surfaced mode switchers (**Chat**, **Builder**, **Operations**, **Files**, **Terminal**, **Memory**, **Settings**, etc.), guarded voice prompts for builders, sanctioned local-control gestures for trusted workflows only, live HUDs for missions, selectors for models/upstreams/providers, visibility into trust profiles plus cost/fuel readouts plus worker statuses, surfaced approval/decision/evidence cues—still **HAM-native**.

---

### Social / external communications layer

Maintain any social/comms direction as **future social/comms/research adapter tracks**, gated behind approvals. HAM does **not** require **ElizaOS** (or similar frameworks) as a mandatory near-term platform core unless an execution slice explicitly adopts them through adapters.

Use **adapter** language—not compulsory merges with external persona stacks.

---

### Ecosystem layering vs Builder phases

| Layer emphasis | Typical alignment |
|----------------|-------------------|
| Local Autopilot + machine autonomy | Dedicated **local-desktop** roadmap track; overlaps Builder phases only after intentional bridge |
| Perception/visual audit | Phases emphasizing preview, QA, WCAG/evidence (**3+**, plus governance) |
| Usage ledger / billing realism | Needed before credible multi-org monetization and multi-provider metering |
| Intelligent cost routing + LLM autopilot | Layer atop ledger readiness; overlays explicit catalog pickers (see **[Billing, ledger](#billing-ledger-and-usage-metering-layer)**) |
| Worker adapters breadth | Starts **Phase 2+** adapters & beyond |
| Builder Spaces UX | Phases **1–3**, per existing Builder roadmap |
| Lifecycle / governance | Late phases & enterprise posture |

Primary roadmap anchor bundles (builder + ecosystem + usage/cost)—see **[Roadmap anchors](#roadmap-anchors)**.

---

## Critical UX behavior

HAM should detect missing architectural/product decisions and ask targeted questions only when needed.

Examples:

```txt
I noticed this app needs a database. Are you targeting small business/simple tenancy, or enterprise/org-based tenancy?
```

```txt
You asked for an admin dashboard. Should this support Owner/Admin/Member roles, or just Admin/User?
```

```txt
Since you mentioned enterprise clients, I recommend org-based RBAC, audit logs, invite flows, and row-level tenant isolation. Proceed with that baseline?
```

```txt
For production, should we use simple deploys first, or do you need feature-flag-driven rollouts?
```

```txt
Based on expected user scale, should we add caching now or defer until performance testing shows a need?
```

```txt
This repo is growing. Should HAM keep a monorepo strategy, or evaluate splitting into services later?
```

The user should not need to know the stack. HAM recommends sane defaults and explains why each decision matters.

---

## Builder flow

A safe HAM Builder flow should be:

```txt
1. User describes desired app
2. HAM detects missing decisions
3. HAM asks targeted questions
4. HAM creates product brief
5. HAM creates architecture blueprint
6. HAM creates ADRs for major decisions
7. HAM creates data/auth/RBAC plan
8. HAM creates implementation plan
9. User approves blueprint
10. HAM routes work to selected workers
11. HAM streams progress
12. HAM shows files/diffs/logs/preview
13. HAM runs tests/security/accessibility checks
14. HAM asks for acceptance
15. HAM prepares deploy plan
16. User approves deploy
17. HAM deploys or prepares deployment artifacts
18. HAM produces evidence bundle
19. HAM tracks post-deploy signals and knowledge
```

---

## Builder Space UX direction

For the Builder / prototype-to-product portion of HAM, the preferred UX is a **Spaces-style Builder surface**.

This does **not** replace the whole HAM Workspace.

```txt
HAM Workspace     = operator console
HAM Builder Space = vibe-building / prototype-to-product surface
```

Each **Builder Space** should represent one app/product/build effort.

**Example (one space):** Builder Space: **“Client Portal App”**

- Chat / vibe prompt
- Decision Queue
- Product Brief
- Architecture Blueprint
- ADRs
- Data Model / RBAC
- Live Build Stream
- Preview
- Files / Diffs
- Tests
- Evidence / Deploy

### Why Builder Spaces

A normal chat page is too cramped for end-to-end product building. HAM needs room to show:

- user intent and conversation
- missing product/architecture decisions
- blueprint cards
- selected worker/backend
- live agent stream
- generated files
- diffs
- logs
- tests
- preview iframe/browser panel
- deploy checklist
- evidence bundle

### Desired user feeling

- **Yes:** “I’m in **the app’s** workspace, and HAM is building it around me.”
- **No:** “I’m just chatting with a bot.”

### Builder Space layout direction

Initial Builder Space layout should be HAM-native and may include:

| Region | Contents |
|--------|----------|
| **Left rail** | Builder Spaces, New App, Recent builds |
| **Main left** | HAM chat / vibe prompt, Missing decisions, Build status |
| **Main center** | Blueprint cards, Files changed, Test results, Diffs |
| **Right** | Live preview iframe, Inspector, Deploy/evidence checklist |

For **smaller/mobile/simple** mode, collapse into:

```txt
Chat → Decisions → Preview → Evidence
```

### Persistence model

Each Builder Space should remember:

- what the user asked for
- requirements and decisions
- architecture chosen
- ADRs
- repo/project connection
- selected workers/backends
- build runs
- generated artifacts
- files changed
- diffs
- tests passed/failed
- human approvals and rejected recommendations
- deploy/evidence status
- open risks and next steps

### Builder Space UX guardrails

- **Do not** directly import a Space Agent-style frontend runtime into HAM as the **first** implementation.
- **Preferred:** borrow the **Spaces UX pattern**, build it **HAM-native**, keep generated apps isolated in **iframe/worktree**, keep agents as **backend workers/adapters**.
- **Safe direction:** HAM Builder Space with cards, preview, decision queue, files, diffs, event stream.
- **Avoid:** a frontend agent freely mutating the real HAM interface.

### Roadmap label — Builder Spaces UX

```txt
HAM_BUILDER_SPACES_UX
```

**Spans (conceptually):** after blueprint artifacts exist **and** as live build/preview mature — align with **`HAM_BUILDER_BLUEPRINT_MODE`** → **`HAM_LIVE_PREVIEW_AND_ACCEPTANCE_LOOP`** (not a substitute for execution adapters between them; UX carries across Phases **1–3** as surfaces deepen).

**Acceptance language:**

```txt
SPACES_STYLE_UI_APPROVED_FOR_BUILDER_PROTOTYPE_SURFACE
HAM_NATIVE_SPACES_UI
NOT_DIRECT_SPACE_AGENT_RUNTIME_INTEGRATION
```

---

## Roadmap anchors

Top-level roadmap anchors:

```txt
HAM_BUILDER_PLATFORM_DIRECTION_APPROVED
HAM_LAST_MILE_APP_BUILDER
HAM_ENTERPRISE_PRODUCT_ORCHESTRATOR
HAM_MULTI_AGENT_BUILD_ORCHESTRATOR
HAM_BUILDER_BLUEPRINT_MODE
HAM_BUILDER_SPACES_UX
HAM_CURSOR_FACTORY_EXECUTION_ADAPTERS
HAM_LIVE_PREVIEW_AND_ACCEPTANCE_LOOP
HAM_PRODUCTION_DEPLOY_AND_EVIDENCE_LOOP
HAM_LIFECYCLE_INTELLIGENCE_AND_GOVERNANCE
HAM_LOCAL_AUTOPILOT_MODE
HAM_USER_CONTROLLED_SECURITY_PROFILES
HAM_PERCEPTION_LAYER
HAM_AGENTIC_VISION_REFERENCE
HAM_USAGE_LEDGER
HAM_MISSION_COST_TRACKING
HAM_LLM_COST_AUTOPILOT
HAM_INTELLIGENT_MODEL_ROUTER
```

Detailed layer/track labels beyond these appear in **[Additional ecosystem capability layers](#additional-ecosystem-capability-layers)** to keep this list readable.

---

## Suggested phased roadmap

### Phase 1 — Builder Blueprint Mode

User describes app → HAM asks missing decisions → HAM produces:

- product brief
- architecture blueprint
- ADRs for key decisions
- role/RBAC plan
- tenancy plan
- data model
- API plan
- frontend page map
- backend service map
- repository strategy recommendation
- deployment target recommendation
- implementation phases
- acceptance checklist

No coding required in this phase unless explicitly approved.

**UX:** Phase 1 should move toward presenting these artifacts inside a **HAM Builder Space** (decision queue, blueprint cards)—not only a cramped single-thread chat. See **[Builder Space UX direction](#builder-space-ux-direction)**.

### Phase 2 — Execution adapters

HAM routes approved build slices to:

- Cursor Cloud Agents
- Cursor SDK local/sidecar
- Factory AI/Droid
- future workers

Shared adapter contract should include:

```txt
create_run()
stream_events()
cancel_run()
get_status()
list_artifacts()
get_diff()
normalize_error()
```

### Phase 3 — Live preview + acceptance loop

HAM shows:

- live agent stream
- files changed
- diffs
- terminal/test logs
- generated preview iframe/browser panel
- acceptance checklist
- approve/reject/iterate controls

**UX:** This phase is where the **Spaces-style** layout pays off—live stream, preview, diffs, and evidence in-region. See **`HAM_BUILDER_SPACES_UX`** and **[Builder Space UX direction](#builder-space-ux-direction)**.

### Phase 4 — Production deploy + evidence loop

HAM prepares or executes deployment with approval:

- env audit
- secret checks
- migration plan
- deployment plan
- rollback plan
- smoke tests
- observability checks
- evidence bundle

### Phase 5 — Lifecycle intelligence + governance

HAM expands into:

- technical debt tracking
- repository strategy optimization
- release strategy
- feature flag lifecycle
- performance/cost guidance
- compliance-oriented modules
- legal/security review integrations
- knowledge retention
- architecture history
- data lifecycle
- end-of-life planning

---

## Guardrails

- Do not let agents freely mutate production.
- Read-only plan first.
- User approval before scoped edits.
- User approval before commit/deploy.
- Provider keys stay server-side/local-side.
- Browser never sees provider secrets.
- Preserve auditability and rollback.
- HAM should summarize raw tool logs before showing them to users.
- Production-grade auth/RBAC/database decisions must not be skipped.
- For production app builds, database, auth, RBAC, tenant isolation, and deployment assumptions must be **explicitly confirmed** or **intentionally deferred** (deferral documented, not silently assumed).
- Enterprise compliance/legal/pen-test/chaos capabilities are part of the long-term vision, not Phase 1 requirements unless explicitly scoped.

---

## Relationship to shipped docs

| Doc | Role |
|-----|------|
| [`VISION.md`](../VISION.md) | Shipped pillars; Hermes/Droid/context; implementation status |
| [`PRODUCT_DIRECTION.md`](../PRODUCT_DIRECTION.md) | Principles and near-term direction (not phased roadmap wording) |
| [`HAM_ROADMAP.md`](HAM_ROADMAP.md) | Workspace, attachments, export, media, RAG — **different** phase labels |
| [`ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) | Cursor Cloud Agent + managed missions shipped vs gap |
| [`HAM_CHAT_CONTROL_PLANE.md`](HAM_CHAT_CONTROL_PLANE.md) | Chat + skills intent |

This file does **not** change those contracts; it provides a **single** place for the Builder Platform north star and phased intent.
