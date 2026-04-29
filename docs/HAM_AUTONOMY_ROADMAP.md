# HAM Autonomy Roadmap

## Purpose

This document names three autonomy lanes for HAM and maps them to the
implementation reality in this repository. It is a planning document only. It
does not add code, broaden machine control, or change the architecture contract
in `VISION.md`.

The three lanes are:

1. **AI Coding Orchestrator** - code work coordinated through Hermes, Bridge,
   Droid, Cursor Cloud Agents, and factual run records.
2. **TEDS / Business Process Copilot** - a future operator assistant for
   business-process guidance, evidence collection, and checklist-style work.
3. **FMO / Agent Workflow Automation** - future workflow automation over
   allowlisted connectors and runners, not unrestricted machine control.

Terms such as **TEDS** and **FMO** are product-lane labels in this document.
They are not first-class module names in the current codebase.

## Ground rules from the current repo

- Hermes remains the sole supervisory orchestrator. It supervises, critiques,
  and learns; execution-heavy work stays with Droid or other explicit
  harnesses.
- `memory_heist` is the context engine. It provides repo truth, not execution
  policy.
- `ControlPlaneRun` is a factual record for committed provider launches and
  status observations. It is not a mission graph, queue, retry engine, or
  learning store.
- Capability Directory and My Library entries are metadata. They do not execute
  code or mutate configuration by themselves.
- Browser automation, desktop-local control, Droid, Cursor Cloud Agent, and
  future connectors are separate lanes with different trust boundaries.
- Machine control must remain narrow, local-first where applicable, opt-in,
  audited, and default-deny. No broad remote control of an operator machine is
  part of this roadmap.

## Existing repo assets

| Asset | Current role | Relevant lane(s) |
|-------|--------------|------------------|
| `VISION.md` | Canonical architecture, pillar roles, current implementation state. | All |
| `src/hermes_feedback.py` | `HermesReviewer` critique surface for bridge-style runs. | AI Coding Orchestrator |
| `src/swarm_agency.py` | Hermes-supervised context assembly, not a second orchestrator. | AI Coding Orchestrator |
| `src/memory_heist.py` | Repo scan, git state, instruction/config/session context. | All |
| `src/tools/droid_executor.py` | Bounded local execution engine used through Bridge/Droid paths. | AI Coding Orchestrator, FMO |
| `src/bridge/` and `main.py` | Bridge runtime, policy, persistence, and one-shot CLI path. | AI Coding Orchestrator |
| `src/ham/chat_operator.py`, `src/api/chat.py` | Dashboard chat operator phases, preview/apply/launch/status flows. | All |
| `.cursor/skills/` and `src/ham/cursor_skills_catalog.py` | Operator skills catalog for chat prompt grounding. | AI Coding Orchestrator, TEDS |
| `src/ham/droid_workflows/` | Allowlisted Factory Droid workflows such as `readonly_repo_audit` and `safe_edit_low`. | AI Coding Orchestrator, FMO |
| `docs/FACTORY_DROID_CONTRACT.md` | Preview, digest, launch, token, argv, and audit contract for Droid execution. | AI Coding Orchestrator, FMO |
| `docs/HAM_DROID_RUNNER_SERVICE.md` | Optional remote runner with bearer auth, cwd allowlists, no arbitrary shell. | FMO |
| `src/integrations/cursor_cloud_client.py`, `src/ham/cursor_agent_workflow.py` | Cursor Cloud Agent preview, launch, status, and summary path. | AI Coding Orchestrator |
| `src/persistence/control_plane_run.py`, `src/api/control_plane_runs.py` | Durable factual run records for Cursor/Droid launches. | AI Coding Orchestrator, FMO |
| `src/persistence/managed_mission.py`, `src/api/cursor_managed_*.py` | Per-agent managed mission record and deploy/post-deploy observations. | AI Coding Orchestrator |
| `src/ham/operator_audit.py` | Append-only operator audit sink for handled control-plane turns. | All |
| `src/ham/clerk_auth.py`, `src/ham/clerk_policy.py`, `src/ham/clerk_email_access.py` | Optional Clerk identity, permission, and email/domain enforcement. | All |
| `src/ham/settings_write.py`, `src/api/project_settings.py` | Preview/apply/rollback for allowlisted `.ham/settings.json` writes. | TEDS, FMO |
| `src/ham/capability_library/`, `src/api/capability_library.py` | Saved capability refs with token-gated mutations and audit. | TEDS, FMO |
| `src/ham/data/capability_directory_v1.json` | Read-only capability directory data. | TEDS, FMO |
| `docs/capabilities/capability_bundle_directory_v1.md` | Capability directory spec: data records, not behavior. | TEDS, FMO |
| `src/api/browser_runtime.py`, `src/ham/browser_runtime/` | Server-side Playwright session API with domain policy and owner key. | TEDS, FMO |
| `docs/BROWSER_RUNTIME_PLAYWRIGHT.md` | Server-side browser runtime setup and limitations. | TEDS, FMO |
| `desktop/` and `docs/desktop/local_control_v1.md` | Electron local-control policy, audit, kill switch, and managed-browser IPC where shipped. | FMO |
| `docs/capabilities/computer_control_pack_v1.md` | Computer-control direction with strict local-first and default-deny boundaries. | FMO |

## Lane 1: AI Coding Orchestrator

### What exists

HAM already has a credible coding-orchestration spine:

- Repo-grounded context through `memory_heist`.
- Hermes review through `HermesReviewer` on bridge-style runs.
- Bridge/Droid local execution with policy gates and persisted `.ham/runs`
  evidence.
- Cursor Cloud Agent preview/launch/status through the chat operator and
  Cursor client.
- Factory Droid workflow preview/launch through allowlisted workflow IDs.
- `ControlPlaneRun` records for committed Cursor/Droid launches.
- Managed mission records for Cursor Cloud Agent observations and deploy
  approval snapshots.
- Operator skill and subagent indexes that can ground chat responses without
  pretending those indexes execute work.

### Missing capabilities

- A single end-to-end Hermes loop over every Cursor Cloud Agent turn. Current
  managed mission heuristics and `HermesReviewer` are separate surfaces.
- A first-class UI join between bridge runs, control-plane runs, managed
  missions, audit records, and provider-native links.
- Stronger status correlation and provider outcome mapping where providers are
  ambiguous. `unknown` must remain a valid state.
- Durable learning persistence for Hermes beyond current review artifacts.
- Explicit follow-up policy for when a review can suggest, but not
  automatically launch, the next coding action.

### Autonomy stance

Recommended profile: **supervised autonomy**.

- Preview before mutating provider launches.
- Digest and base-revision verification before commit.
- Human confirmation for mutating launches.
- Provider-specific status mapping with honest `unknown`.
- Advisory Hermes review that does not overwrite factual provider lifecycle.

## Lane 2: TEDS / Business Process Copilot

### What exists

There is no dedicated TEDS module today, but several repo assets can support a
business-process copilot lane:

- Dashboard chat can map operator intent to known skills, docs, settings
  previews, project/run inspection, and controlled launch phases.
- Capability Directory and My Library can describe reusable capabilities and
  operator playbooks as data.
- Project settings preview/apply already models the right pattern for
  human-approved changes: dry run, diff, digest/revision, token-gated apply,
  backup, and audit.
- Clerk policy can distinguish preview/status permissions from launch/admin
  permissions.
- `memory_heist` can provide project context, config, and instruction files to
  the assistant without inventing state.
- Server-side browser runtime can inspect web pages on the API host under
  policy, but it is not desktop-local control.

### Missing capabilities

- A TEDS-specific vocabulary for process templates, evidence requirements,
  approvals, and handoff states.
- A read-only process template registry, separate from execution providers.
- Evidence packets that cite source docs, forms, browser observations, and
  operator decisions without storing secrets.
- Connector-specific read APIs for business systems. None should be implied by
  generic browser or machine control.
- A policy model for process classes such as read-only research, draft-only
  preparation, approval-required submission, and blocked actions.
- UI surfaces that show "recommended next step" without turning every
  recommendation into an executable button.

### Autonomy stance

Recommended profile: **copilot-first autonomy**.

- Default to read-only guidance and draft preparation.
- Let TEDS propose checklist steps, collect evidence, and prepare payloads.
- Require explicit approval before any external submission or settings write.
- Use connectors when available; use browser observation only when a connector
  does not exist and the target is allowed by policy.
- Do not use desktop-local machine control for business processes unless a
  separate local-control policy slice explicitly approves that capability.

## Lane 3: FMO / Agent Workflow Automation

### What exists

FMO maps best to HAM's existing provider and workflow substrate, but only in a
bounded sense:

- Factory Droid workflows are allowlisted and launch through preview, digest,
  confirmation, and audit.
- Droid can run locally from the HAM API host or through the optional runner
  service. The runner validates argv, can enforce cwd allowlists, uses
  `shell=False`, and keeps Factory secrets on the runner host.
- Cursor Cloud Agents are a remote execution harness against GitHub
  repositories, with separate Cursor API auth and HAM launch tokens.
- `ControlPlaneRun` can record committed launches and last observed provider
  status, but it is not a general workflow graph.
- Capability Directory can describe workflow bundles as metadata.
- Desktop Local Control has policy, audit, kill-switch, inert sidecar, and
  managed-browser slices where shipped, but it is not a generic automation
  plane.

### Missing capabilities

- A workflow runner abstraction that coordinates multi-step jobs without
  pretending `ControlPlaneRun` is already a graph.
- Durable workflow definitions with explicit inputs, approvals, evidence, and
  connector scopes.
- Connector inventory and credentials model. Current repo assets document
  future MCP/tool directions but do not ship a generic connector framework.
- Queue, retry, cancel, resume, and compensation semantics.
- Cross-step audit correlation and UI state for workflow instances.
- Policy for which connector actions are read-only, draft, submit, destructive,
  or forbidden.

### Autonomy stance

Recommended profile: **bounded workflow automation**.

- Start with single-step or short linear workflows.
- Use provider-specific preview and launch gates.
- Keep connector actions allowlisted and typed.
- Require approval at commit boundaries.
- Treat broad filesystem, process, shell, or desktop control as out of scope
  unless a separate local-only policy explicitly enables a narrow capability.

## Browser vs machine vs connector split

| Plane | Current repo meaning | Appropriate use | Guardrails |
|-------|----------------------|-----------------|------------|
| **Browser** | Server-side `/api/browser*` Playwright sessions on the API host, plus separate Electron managed-browser slices in Desktop. | Inspect allowed web surfaces, capture screenshots, perform narrow browser actions when policy permits. | Domain policy, owner key/session TTL, rate limits, Clerk/dashboard access, no assumption that it controls the user's desktop. |
| **Machine** | Desktop Local Control policy/audit/kill switch and narrow Electron main-process capabilities; Droid local subprocess for coding workflows. | Local-only, opt-in, audited capabilities with explicit presets. | Default deny, kill switch outside model reasoning, no generic shell from renderer/chat, no broad remote desktop control. |
| **Connector** | Future typed integrations or MCP/tool servers; current repo has catalog/spec placeholders and provider-specific clients for Cursor/Droid. | Preferred path for business systems and workflow automation when a typed API exists. | Read/write scopes, token storage outside browser, typed schemas, preview/diff before mutation, audit references. |

Design rule: prefer **connector** over browser when an API exists; prefer
**browser observation** over machine control for web-only tasks; reserve
**machine control** for local, explicit, narrow capabilities.

## Workflow runner model

The roadmap should evolve from current provider-specific launches toward a
small workflow runner model without introducing a broad orchestration framework.

### Current runner shapes

| Runner | Topology | Current guarantees |
|--------|----------|--------------------|
| Bridge/Droid local | HAM API host executes bounded subprocess work. | Policy gate, timeout, capped output, structured run persistence. |
| Factory Droid runner service | Remote VM/sidecar executes `droid exec` for HAM. | Bearer auth, optional allowed roots, argv validation, no arbitrary shell, runner JSONL audit. |
| Cursor Cloud Agent | Cursor-hosted agent against remote repository. | Cursor API auth, HAM digest/launch token on operator path, status polling, provider-native payloads capped or referenced. |
| Browser runtime | API-host Playwright sessions. | Domain policy, session owner, screenshot/action endpoints, no desktop-local semantics. |
| Desktop Local Control | Electron main process. | Local-only policy, audit, kill switch, narrow IPC/preload bridge, no broad renderer powers. |

### Recommended future workflow instance

A future workflow runner should use a distinct record type, not overload
`ControlPlaneRun`. A minimal instance can contain:

- `workflow_instance_id`
- `workflow_template_id`
- `project_id`
- `actor`
- `approval_profile`
- ordered `steps`
- per-step `runner_kind` (`cursor_cloud_agent`, `factory_droid`,
  `browser_observation`, `connector_action`, `desktop_local`)
- per-step `proposal_digest` and `base_revision` when a step can mutate
- per-step `evidence_refs`
- per-step `audit_refs`
- lifecycle (`draft`, `awaiting_approval`, `running`, `blocked`, `succeeded`,
  `failed`, `unknown`, `cancelled`)

`ControlPlaneRun` remains the child factual record for committed provider
launches. Workflow instances may reference those run IDs later, but should not
make provider facts depend on workflow-level judgment.

## Approval and guardrail profiles

| Profile | Allowed behavior | Example fit | Required controls |
|---------|------------------|-------------|-------------------|
| `observe_only` | Read status, inspect allowed resources, summarize evidence. | TEDS research, run/status views, diagnostics. | Clerk/status permission, redaction, audit for handled operator turns. |
| `draft_only` | Prepare proposed text, settings diffs, forms, or workflow plans without submission. | TEDS process drafts, agent profile proposals. | No external writes; proposal digest where a later apply may occur. |
| `confirm_to_apply` | Mutate HAM settings or library/config only after preview and explicit confirmation. | `.ham/settings.json`, Hermes skill install, capability library mutations. | Token, base revision, backup, audit, conflict handling. |
| `confirm_to_launch_readonly` | Launch a read-only runner after preview/confirmation. | Droid `readonly_repo_audit`, Cursor status/read tasks. | Digest verification, provider audit, `ControlPlaneRun` where applicable. |
| `confirm_to_launch_mutating` | Launch a mutating provider action after preview/confirmation. | Droid `safe_edit_low`, Cursor Cloud Agent launch with PR options. | HAM launch token, provider auth, digest verification, audit, status mapping. |
| `local_desktop_guarded` | Use narrow desktop-local capabilities where explicitly enabled. | Managed browser slice in HAM Desktop. | Default deny, local-only policy, kill switch, redacted audit, no generic shell. |
| `blocked` | Refuse action and explain allowed alternatives. | Broad remote machine control, arbitrary shell, untyped credential use. | Audit denial when routed through operator policy. |

## Audit event taxonomy

HAM should use a consistent event vocabulary across lanes. Existing JSONL
audits can keep their current schemas while future docs and UI map them into
these families.

| Event family | Meaning | Existing anchors |
|--------------|---------|------------------|
| `operator.intent_received` | Chat/operator request was classified into an actionable or informational phase. | `src/ham/chat_operator.py`, `src/ham/operator_audit.py` |
| `operator.access_denied` | Identity, email/domain, or permission gate denied the request. | Clerk policy and email access audit |
| `preview.created` | A dry-run proposal was generated. | Settings preview, Droid preview, Cursor preview, Hermes skills install preview |
| `preview.rejected` | Preview could not be created because inputs, root, repo, credentials, or policy failed. | Chat operator result errors |
| `approval.requested` | UI/client must ask the human to confirm a pending operation. | `pending_apply`, `pending_droid`, `pending_cursor_agent` |
| `approval.granted` | Confirmed request crossed the commit boundary with valid token/digest/revision. | Droid/Cursor launch, settings apply |
| `approval.denied` | Human or policy declined to proceed. | Future workflow UI, existing blocked operator flows |
| `runner.dispatched` | HAM sent work to a provider or runner after approval. | Droid runner, Cursor launch, Bridge runtime |
| `runner.blocked` | Runner refused execution because of auth, cwd, argv, or policy. | Droid runner JSONL |
| `runner.observed` | HAM observed provider status or captured bounded evidence. | Cursor status, managed missions, browser screenshots |
| `runner.completed` | Provider or runner reached terminal mapped status. | Droid outcome, Cursor mapped status |
| `artifact.recorded` | HAM stored a pointer to output, screenshot, provider id, PR, run record, or audit line. | `.ham/runs`, `ControlPlaneRun`, JSONL audit refs |
| `settings.applied` | Allowlisted HAM/Hermes/project setting changed. | Settings apply, Hermes skills apply |
| `capability.saved` | Metadata-only capability/library reference changed. | Capability library audit |
| `guardrail.triggered` | A safety rule blocked or downgraded an action. | Droid forbidden flags, browser policy, local-control kill switch |

The taxonomy should avoid storing secrets, full provider payloads, or unbounded
stdout/stderr in primary records. Use capped summaries and artifact pointers.

## Phased roadmap

### Phase 0: Align language and boundaries

- Adopt the three lane labels in docs and UI copy only where helpful.
- Keep `VISION.md`, `HAM_CHAT_CONTROL_PLANE.md`, `CONTROL_PLANE_RUN.md`, and
  `HARNESS_PROVIDER_CONTRACT.md` as the source of truth for shipped behavior.
- Add a lane map to capability docs and operator help without adding execution.
- Explicitly label TEDS and FMO as future product lanes, not current modules.

Exit criteria:

- Operators can distinguish coding orchestration, business copilot, and
  workflow automation without assuming broad machine control.

### Phase 1: Read-only evidence and templates

- Define process/workflow templates as metadata records.
- Add evidence expectations and approval profiles to docs/specs.
- Surface existing `ControlPlaneRun`, managed mission, run-store, and audit
  links in one read-only view or doc pattern.
- Keep Capability Directory and My Library data-only.

Exit criteria:

- A user can inspect what would run, what evidence is expected, and which
  approval profile applies before any mutation exists.

### Phase 2: Preview-first actions

- Extend existing preview/apply patterns to one narrow TEDS or FMO slice.
- Require proposal digest, base revision, conflict checks, and human approval
  before writes.
- Prefer connector-style typed payloads over browser action where possible.
- Keep browser use observational unless the workflow explicitly requires a
  narrow allowed action.

Exit criteria:

- One workflow can produce a dry-run proposal and evidence packet without
  executing a broad automation loop.

### Phase 3: Committed single-step or short linear workflows

- Introduce a distinct workflow instance record if product needs multi-step
  automation.
- Reference `ControlPlaneRun` for committed Cursor/Droid launches instead of
  replacing it.
- Add per-step audit refs and status.
- Add cancel/block semantics before retry/resume semantics.

Exit criteria:

- A short workflow can run with explicit approvals and factual per-step
  evidence, while provider truth remains provider-native.

### Phase 4: Connector and policy hardening

- Add typed connector inventory only after a concrete connector exists.
- Add read/write scopes, credential placement, and redaction rules per
  connector.
- Add tests around policy gates, audit redaction, and lifecycle mapping.
- Consider Hermes advisory review over capped workflow artifacts, but do not
  let review text drive factual lifecycle fields.

Exit criteria:

- Connector-backed automation can operate under typed scopes with audit and
  approval parity.

### Phase 5: Limited autonomy loops

- Allow bounded follow-up only inside a declared workflow template and approval
  profile.
- Require stop conditions, maximum step count, max spend/time, and kill/cancel
  path.
- Keep broad machine-control loops out of scope.

Exit criteria:

- HAM can run a bounded workflow loop without becoming an unrestricted desktop,
  shell, browser, or provider automation system.

## Risks

| Risk | Mitigation |
|------|------------|
| Role collapse: Hermes becomes a second execution engine. | Keep Hermes advisory/supervisory; execution remains provider-specific. |
| `ControlPlaneRun` becomes a workflow graph by accident. | Add a separate workflow instance record only when needed. |
| Browser automation is mistaken for desktop machine control. | Keep `/api/browser`, Desktop Local Control, and connectors explicitly separate. |
| Capability metadata gains hidden execution semantics. | Preserve registry-records-as-data rule; execution only through reviewed providers. |
| Audit records leak secrets or full payloads. | Store capped summaries and pointers; redact env, tokens, paths, and provider blobs. |
| Provider status is overclaimed. | Keep `unknown` as a valid lifecycle and test mappings before declaring success/failure. |
| Approval fatigue leads to unsafe defaults. | Use profiles: observe/draft can be lightweight; apply/launch requires confirmation. |
| Generic connector framework arrives before a concrete connector. | Build only after a real second or third implementation proves the abstraction. |
| Machine-control scope expands through chat prompts. | Default deny, local-only policy, kill switch, no arbitrary shell, no raw argv from chat. |
| TEDS/FMO language implies shipped modules that do not exist. | Label them as roadmap lanes until repo assets are created. |

## Recommended next implementation slice

Do **not** start with new machine-control features. The safest next slice is a
documentation and read-only product-model slice:

1. Add a small **autonomy lane map** to the dashboard/help surfaces or
   Capability Directory copy that links the three lanes to existing assets.
2. Define a metadata-only `workflow_template` / `process_template` shape in a
   spec doc, with:
   - lane
   - required runner kind
   - approval profile
   - expected evidence
   - audit event families
   - explicit non-goals
3. Create one **read-only example template** for each lane:
   - AI Coding Orchestrator: repo audit or Cursor Cloud Agent handoff.
   - TEDS: business-process checklist and evidence packet, no submission.
   - FMO: allowlisted Droid workflow launch plan, no new runner behavior.
4. Add tests only when code or data files are introduced in a later slice.

This slice improves shared language and operator safety without expanding
execution authority.
