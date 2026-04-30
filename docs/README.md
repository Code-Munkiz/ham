# Ham documentation index

Canonical architecture and agent context live at the repo root: [VISION.md](../VISION.md), [AGENTS.md](../AGENTS.md), [SWARM.md](../SWARM.md), [GAPS.md](../GAPS.md).

## Operations and deploy

| Doc | Purpose |
|-----|---------|
| [DEPLOY_CLOUD_RUN.md](DEPLOY_CLOUD_RUN.md) | GCP Artifact Registry, Cloud Run deploy, env vars |
| [DEPLOY_HANDOFF.md](DEPLOY_HANDOFF.md) | Vercel + Cloud Run checklist |
| [HAM_CLOUD_AGENT_ROUTING_SMOKE.md](HAM_CLOUD_AGENT_ROUTING_SMOKE.md) | Routing / smoke notes for Cloud Agent paths |
| [RUNBOOK_HAM_MODEL_RECOVERY.md](RUNBOOK_HAM_MODEL_RECOVERY.md) | Model / gateway recovery runbook |

## Cursor Cloud Agent and managed missions

| Doc | Purpose |
|-----|---------|
| [ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) | Shipped vs partial vs roadmap; SDK bridge and feed modes |
| [MISSION_AWARE_FEED_CONTROLS.md](MISSION_AWARE_FEED_CONTROLS.md) | Feed and controls scoped by `mission_registry_id` |
| [CONTROL_PLANE_RUN.md](CONTROL_PLANE_RUN.md) | `ControlPlaneRun` substrate (factual runs, not a mission graph) |

## Chat, gateway, and capabilities

| Doc | Purpose |
|-----|---------|
| [HAM_CHAT_CONTROL_PLANE.md](HAM_CHAT_CONTROL_PLANE.md) | Dashboard chat + skills intent roadmap |
| [HERMES_GATEWAY_CONTRACT.md](HERMES_GATEWAY_CONTRACT.md) | Server-side Hermes / OpenAI-compatible adapter contract |
| [HERMES_GATEWAY_BROKER.md](HERMES_GATEWAY_BROKER.md) | Gateway broker snapshot (Command Center) |
| [FACTORY_DROID_CONTRACT.md](FACTORY_DROID_CONTRACT.md) | Factory Droid execution contract |
| [HAM_DROID_RUNNER_SERVICE.md](HAM_DROID_RUNNER_SERVICE.md) | Droid runner service notes |

## Browser, desktop, and local control

| Doc | Purpose |
|-----|---------|
| [BROWSER_RUNTIME_PLAYWRIGHT.md](BROWSER_RUNTIME_PLAYWRIGHT.md) | In-process Playwright setup and caveats |
| [desktop/local_control_v1.md](desktop/local_control_v1.md) | Local control v1 (Windows-first product path) |
| [desktop/local_web_bridge_mvp.md](desktop/local_web_bridge_mvp.md) | Web ↔ local bridge MVP |
| [goham/browser_smoke.md](goham/browser_smoke.md) | Browser smoke / GoHAM-related notes |

## Hardening and Hermes workspace

| Doc | Purpose |
|-----|---------|
| [HAM_HARDENING_REMEDIATION.md](HAM_HARDENING_REMEDIATION.md) | Context Engine hardening and remediation order |
| [TEAM_HERMES_STATUS.md](TEAM_HERMES_STATUS.md) | API vs desktop operator story for Command Center / Hermes |
| [HERMES_WORKSPACE_FILES_TERMINAL_BRIDGE.md](HERMES_WORKSPACE_FILES_TERMINAL_BRIDGE.md) | Workspace files and terminal bridge |

## Reference (patterns only)

| Doc | Purpose |
|-----|---------|
| [reference/factory-droid-reference.md](reference/factory-droid-reference.md) | Factory Droid patterns |
| [reference/openclaw-reference.md](reference/openclaw-reference.md) | OpenClaw-informed patterns |
| [reference/elizaos-reference.md](reference/elizaos-reference.md) | ElizaOS-flavored host patterns |
| [reference/hermes-agent-reference.md](reference/hermes-agent-reference.md) | Hermes agent upstream reference |

## HAM-on-X (social / reactive)

| Path | Purpose |
|------|---------|
| [ham-x-agent/](ham-x-agent/) | Architecture, env, runbook, smoke, safety for HAM-on-X |

Other topical docs in this directory (capabilities packs, voice MVP, workstation plans, etc.) are discoverable by filename; use repo search when you need a specific subsystem.
