# Ham documentation index

First-class narrative lives in the repo root (`VISION.md`, `AGENTS.md`, `SWARM.md`, `GAPS.md`, `PRODUCT_DIRECTION.md`). This page groups **`docs/`** by topic so you can jump to contracts, deploy, and feature notes without hunting filenames.

## Architecture and contracts

| Doc | What it covers |
|-----|----------------|
| [CONTROL_PLANE_RUN.md](CONTROL_PLANE_RUN.md) | `ControlPlaneRun` v1: durable operator launch records (Cursor/Droid), read APIs — not a mission graph |
| [HERMES_GATEWAY_CONTRACT.md](HERMES_GATEWAY_CONTRACT.md) | Server-side adapter to Hermes / OpenAI-compatible chat (streaming `http` mode) |
| [HERMES_GATEWAY_BROKER.md](HERMES_GATEWAY_BROKER.md) | Hermes gateway broker Path B snapshot + UI pointers |
| [HAM_CHAT_CONTROL_PLANE.md](HAM_CHAT_CONTROL_PLANE.md) | Chat + skills intent mapping, operator surface |
| [HARNESS_PROVIDER_CONTRACT.md](HARNESS_PROVIDER_CONTRACT.md) | Harness / provider contracts used by chat and launch flows |
| [FACTORY_DROID_CONTRACT.md](FACTORY_DROID_CONTRACT.md) | Factory Droid–style execution contract notes |
| [HAM_DROID_RUNNER_SERVICE.md](HAM_DROID_RUNNER_SERVICE.md) | Droid runner service notes |
| [config_trust_model.md](config_trust_model.md) | Config trust boundaries |

## Deploy and operations

| Doc | What it covers |
|-----|----------------|
| [DEPLOY_CLOUD_RUN.md](DEPLOY_CLOUD_RUN.md) | GCP Artifact Registry, Cloud Run, env vars, private Hermes |
| [DEPLOY_HANDOFF.md](DEPLOY_HANDOFF.md) | Vercel + Cloud Run checklist |
| [examples/ham-api-cloud-run-env.yaml](examples/ham-api-cloud-run-env.yaml) | Example env file for `--env-vars-file` |
| [BROWSER_RUNTIME_PLAYWRIGHT.md](BROWSER_RUNTIME_PLAYWRIGHT.md) | In-process Playwright `/api/browser*` setup and caveats |
| [HAM_HARDENING_REMEDIATION.md](HAM_HARDENING_REMEDIATION.md) | Context Engine audit summary and remediation order |

## Cursor Cloud Agent and managed missions

| Doc | What it covers |
|-----|----------------|
| [ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) | Shipped vs partial vs out of scope; phased gap closure |
| [HAM_CLOUD_AGENT_ROUTING_SMOKE.md](HAM_CLOUD_AGENT_ROUTING_SMOKE.md) | Workspace chat → operator → Cloud Agent routing smoke |
| [WORKSPACE_JOBS_TASKS_BRIDGE.md](WORKSPACE_JOBS_TASKS_BRIDGE.md) | Jobs / tasks / bridge orientation |

## Desktop and local control

| Doc | What it covers |
|-----|----------------|
| [desktop/local_control_v1.md](desktop/local_control_v1.md) | Local control v1 product and safety notes |
| [desktop/local_web_bridge_mvp.md](desktop/local_web_bridge_mvp.md) | Local web bridge MVP |
| [desktop/local_control_sidecar_protocol_v1.md](desktop/local_control_sidecar_protocol_v1.md) | Sidecar protocol v1 |
| [desktop/live_browser_copilot_v1.md](desktop/live_browser_copilot_v1.md) | Live browser copilot v1 |
| [desktop/RELEASE_PIPELINE.md](desktop/RELEASE_PIPELINE.md) | Desktop release pipeline |
| [goham/browser_smoke.md](goham/browser_smoke.md) | Browser smoke / historical notes |

## Capabilities and skills surfaces

| Doc | What it covers |
|-----|----------------|
| [capabilities/capability_bundle_directory_v1.md](capabilities/capability_bundle_directory_v1.md) | Capability bundle directory v1 |
| [capabilities/computer_control_pack_v1.md](capabilities/computer_control_pack_v1.md) | Computer control pack v1 |
| [TEAM_HERMES_STATUS.md](TEAM_HERMES_STATUS.md) | API vs desktop operator story for Command Center / Hermes setup |

## HAM-on-X (social agent)

| Doc | What it covers |
|-----|----------------|
| [ham-x-agent/architecture.md](ham-x-agent/architecture.md) | Architecture |
| [ham-x-agent/runbook.md](ham-x-agent/runbook.md) | Runbook |
| [ham-x-agent/env.md](ham-x-agent/env.md) | Environment |
| [ham-x-agent/safety-policy.md](ham-x-agent/safety-policy.md) | Safety policy |
| [ham-x-agent/smoke-testing.md](ham-x-agent/smoke-testing.md) | Smoke testing |
| [ham-x-agent/phase-1-supervised-loop.md](ham-x-agent/phase-1-supervised-loop.md) | Supervised loop phase notes |

## Reference (patterns only; not parity targets)

| Doc | What it covers |
|-----|----------------|
| [reference/factory-droid-reference.md](reference/factory-droid-reference.md) | Factory Droid patterns |
| [reference/openclaw-reference.md](reference/openclaw-reference.md) | OpenClaw-oriented reference |
| [reference/elizaos-reference.md](reference/elizaos-reference.md) | ElizaOS-oriented reference |
| [reference/hermes-agent-reference.md](reference/hermes-agent-reference.md) | Hermes agent reference |

## Audits, inventory, and long-form plans

Deeper audits and lift plans (use when you need historical context or IA inventory): `HERMES_WORKSPACE_*`, `PHASE0_HERMES_WORKSPACE_INVENTORY.md`, `WHOLE_HERMES_WORKSPACE_LIFT_PLAN.md`, `WORKSTATION_P1_MULTI_ROOT.md`, `forensics/`, and related files in this directory.

## Other topics

| Doc | What it covers |
|-----|----------------|
| [TERMINAL_PTY_PARITY.md](TERMINAL_PTY_PARITY.md) | Terminal PTY parity |
| [VOICE_MVP_README.md](VOICE_MVP_README.md) | Voice MVP |
| [RELEVANCE_SCORING.md](RELEVANCE_SCORING.md) | Relevance scoring |
| [RUNBOOK_HAM_MODEL_RECOVERY.md](RUNBOOK_HAM_MODEL_RECOVERY.md) | Model recovery runbook |
| [OPENCODE_VERIFICATION.md](OPENCODE_VERIFICATION.md) / [OPENCODE_VERIFICATION_RESULT.md](OPENCODE_VERIFICATION_RESULT.md) | OpenCode verification |

For **Cursor setup** (rules, skills, subagents), see `CURSOR_SETUP_HANDOFF.md` and `CURSOR_EXACT_SETUP_EXPORT.md` at the repository root.
