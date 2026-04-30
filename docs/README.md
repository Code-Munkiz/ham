# Ham documentation index

Curated entry points for operators and contributors. For the full first-class file list, see [`AGENTS.md`](../AGENTS.md) in the repo root.

## Architecture and product

| Doc | Purpose |
|-----|---------|
| [`../VISION.md`](../VISION.md) | Pillars, boundaries, current vs target implementation |
| [`../GAPS.md`](../GAPS.md) | Active gaps; links to deeper roadmaps |
| [`../PRODUCT_DIRECTION.md`](../PRODUCT_DIRECTION.md) | Product lens (HAM-native vs reference ecosystems) |
| [`ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) | Cursor Cloud Agent + managed missions: shipped, limits, phased roadmap |
| [`CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md) | `ControlPlaneRun` substrate (durable launch records; not a mission graph) |

## Deploy and API

| Doc | Purpose |
|-----|---------|
| [`DEPLOY_CLOUD_RUN.md`](DEPLOY_CLOUD_RUN.md) | GCP Cloud Run build, deploy, env vars |
| [`DEPLOY_HANDOFF.md`](DEPLOY_HANDOFF.md) | Vercel + Cloud Run checklist |
| [`examples/ham-api-cloud-run-env.yaml`](examples/ham-api-cloud-run-env.yaml) | Example env file for `--env-vars-file` |
| [`HERMES_GATEWAY_CONTRACT.md`](HERMES_GATEWAY_CONTRACT.md) | Server-side chat gateway contract |

## Chat, skills, and capabilities

| Doc | Purpose |
|-----|---------|
| [`HAM_CHAT_CONTROL_PLANE.md`](HAM_CHAT_CONTROL_PLANE.md) | Chat + skills intent mapping roadmap |
| [`HERMES_GATEWAY_BROKER.md`](HERMES_GATEWAY_BROKER.md) | Hermes gateway broker (dashboard snapshot) |
| [`HAM_HARDENING_REMEDIATION.md`](HAM_HARDENING_REMEDIATION.md) | Context Engine hardening audit and remediation order |

## Desktop and local control

| Doc | Purpose |
|-----|---------|
| [`desktop/local_control_v1.md`](desktop/local_control_v1.md) | Local control v1 (policy, bridge, safety) |
| [`desktop/README.md`](../desktop/README.md) | Electron shell (from repo `desktop/`) |
| [`BROWSER_RUNTIME_PLAYWRIGHT.md`](BROWSER_RUNTIME_PLAYWRIGHT.md) | In-process Playwright / `/api/browser` setup |

## Deeper dives and reference

- [`reference/`](reference/) — Factory Droid, Hermes agent, OpenClaw, ElizaOS (patterns only, not parity targets)
- [`ham-x-agent/`](ham-x-agent/) — HAM-on-X social agent runbooks
- [`capabilities/`](capabilities/) — Capability bundle / directory specs

## Cursor / IDE setup

See [`../CURSOR_SETUP_HANDOFF.md`](../CURSOR_SETUP_HANDOFF.md) for rules, skills, and slash-command workflows. Cloud workspace quick start: [`.cursor/skills/cloud-agent-starter/SKILL.md`](../.cursor/skills/cloud-agent-starter/SKILL.md).
