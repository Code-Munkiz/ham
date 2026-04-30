# Ham documentation index

First-time orientation: read [VISION.md](../VISION.md), [AGENTS.md](../AGENTS.md), and [SWARM.md](../SWARM.md). This page lists **tracked** docs under `docs/` (large local exports such as `docs/repomix-*` may be gitignored).

## Architecture and product

| Doc | Purpose |
|-----|---------|
| [CONTROL_PLANE_RUN.md](CONTROL_PLANE_RUN.md) | `ControlPlaneRun` v1 — factual provider-neutral launch record (not a mission graph). |
| [ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) | Cursor Cloud Agent + managed missions: shipped vs partial vs roadmap. |
| [HAM_CHAT_CONTROL_PLANE.md](HAM_CHAT_CONTROL_PLANE.md) | Chat operator path, skills intent, preview/launch contracts. |
| [HAM_HARDENING_REMEDIATION.md](HAM_HARDENING_REMEDIATION.md) | Context Engine / continuation coupling and remediation order. |
| [TEAM_HERMES_STATUS.md](TEAM_HERMES_STATUS.md) | API vs desktop operator story for Command Center and related UI. |
| [config_trust_model.md](config_trust_model.md) | Config and trust boundaries (high level). |

## Deploy and operations

| Doc | Purpose |
|-----|---------|
| [DEPLOY_CLOUD_RUN.md](DEPLOY_CLOUD_RUN.md) | GCP Cloud Run image, env vars, Firestore chat sessions, staging SOT. |
| [DEPLOY_HANDOFF.md](DEPLOY_HANDOFF.md) | Vercel + Cloud Run checklist and CORS. |
| [HERMES_GATEWAY_CONTRACT.md](HERMES_GATEWAY_CONTRACT.md) | Server-side chat adapter contract (streaming `http` mode). |
| [RUNBOOK_HAM_MODEL_RECOVERY.md](RUNBOOK_HAM_MODEL_RECOVERY.md) | Model / routing recovery runbook. |
| [examples/ham-api-cloud-run-env.yaml](examples/ham-api-cloud-run-env.yaml) | Example env YAML for deploy merges. |

## Cursor, harness, and browser

| Doc | Purpose |
|-----|---------|
| [HAM_CLOUD_AGENT_ROUTING_SMOKE.md](HAM_CLOUD_AGENT_ROUTING_SMOKE.md) | Manual smoke: Workspace Chat → `/api/chat/stream` → Cloud Agent router intents. |
| [HARNESS_PROVIDER_CONTRACT.md](HARNESS_PROVIDER_CONTRACT.md) | Harness/provider behavior (Cursor + Droid). |
| [FACTORY_DROID_CONTRACT.md](FACTORY_DROID_CONTRACT.md) | Factory Droid workflow contract (preview/launch). |
| [BROWSER_RUNTIME_PLAYWRIGHT.md](BROWSER_RUNTIME_PLAYWRIGHT.md) | In-process Playwright setup and caveats for `/api/browser/*`. |

## Desktop and local control

| Doc | Purpose |
|-----|---------|
| [desktop/local_control_v1.md](desktop/local_control_v1.md) | Local control v1 overview. |
| [desktop/local_control_sidecar_protocol_v1.md](desktop/local_control_sidecar_protocol_v1.md) | Sidecar protocol. |
| [desktop/RELEASE_PIPELINE.md](desktop/RELEASE_PIPELINE.md) | Desktop release pipeline notes. |

## Reference notes (patterns only)

| Doc | Purpose |
|-----|---------|
| [reference/factory-droid-reference.md](reference/factory-droid-reference.md) | Factory Droid patterns. |
| [reference/openclaw-reference.md](reference/openclaw-reference.md) | OpenClaw-informed patterns. |
| [reference/elizaos-reference.md](reference/elizaos-reference.md) | ElizaOS-flavored host patterns. |
| [reference/hermes-agent-reference.md](reference/hermes-agent-reference.md) | Hermes agent upstream notes. |

## Deeper tracks and audits

Subdirectories bundle related material: [ham-x-agent/](ham-x-agent/) (architecture, env, safety, runbook), [capabilities/](capabilities/) (capability packs), [goham/](goham/) (GoHAM / browser smoke), and planning or audit markdown at repo root / `docs/` (e.g. `PHASE1_IMPLEMENTATION.md`, `forensics/`). Prefer the tables above for day-to-day API and deploy work.
