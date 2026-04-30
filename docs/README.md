# Ham documentation index

Canonical architecture and agent context live at the repo root: [`VISION.md`](../VISION.md), [`AGENTS.md`](../AGENTS.md), [`SWARM.md`](../SWARM.md), [`GAPS.md`](../GAPS.md).

**Not source of truth:** generated exports and tool-local settings (for example [`CURSOR_EXACT_SETUP_EXPORT.md`](../CURSOR_EXACT_SETUP_EXPORT.md), `.cursor/settings.json`) are snapshots or editor config—defer to git-tracked canonical docs unless you deliberately refresh an export script.

**Cursor / contributor setup:** rules, skills, subagents, and slash-command workflows are summarized in [`CURSOR_SETUP_HANDOFF.md`](../CURSOR_SETUP_HANDOFF.md) (canonical copies live under `.cursor/rules/` and `.cursor/skills/`).

### Suggested read order (Cloud Agent + missions)

1. [`ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) — shipped capabilities, SDK bridge rollback, SSE/projection semantics.
2. [`MISSION_AWARE_FEED_CONTROLS.md`](MISSION_AWARE_FEED_CONTROLS.md) — `mission_registry_id` scoping and live transcript behavior.
3. [`HAM_CLOUD_AGENT_ROUTING_SMOKE.md`](HAM_CLOUD_AGENT_ROUTING_SMOKE.md) — Workspace chat routing smoke.
4. Examples: [`examples/managed_cloud_agent_phases/README.md`](examples/managed_cloud_agent_phases/README.md) — curl fixtures for Phase A–D APIs.

SDK bridge attaches to existing `bc-*` agents; **`HAM_CURSOR_SDK_BRIDGE_ENABLED`** toggles bridge vs REST projection; HAM `/feed` stays the browser contract (no Cursor API calls from the browser).

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
| [ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) | Shipped vs partial vs roadmap; SDK bridge vs REST fallbacks |
| [MISSION_AWARE_FEED_CONTROLS.md](MISSION_AWARE_FEED_CONTROLS.md) | Feed + controls scoped by `mission_registry_id` |
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
| [desktop/local_control_v1.md](desktop/local_control_v1.md) | Local control v1 (Windows-first path) |
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

Other topical docs here (capabilities packs, workstation plans, etc.) remain discoverable by filename; search the repo when you need a subsystem not listed above.
