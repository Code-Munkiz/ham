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
```

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
