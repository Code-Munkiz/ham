# Ham documentation index

Use this page to find the right doc without searching the tree. Canonical architecture and agent context stay in the repo root: [`VISION.md`](../VISION.md), [`AGENTS.md`](../AGENTS.md), [`GAPS.md`](../GAPS.md).

## Architecture and control plane

| Topic | Doc |
|-------|-----|
| Control plane runs (durable launch records, read APIs) | [`CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md) |
| Cloud Cursor agent + managed missions (shipped vs partial vs roadmap) | [`ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) |
| Cloud agent routing smoke | [`HAM_CLOUD_AGENT_ROUTING_SMOKE.md`](HAM_CLOUD_AGENT_ROUTING_SMOKE.md) |
| Harness provider contract | [`HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md) |

## Deploy and operations

| Topic | Doc |
|-------|-----|
| Vercel + Cloud Run handoff (env, CORS) | [`DEPLOY_HANDOFF.md`](DEPLOY_HANDOFF.md) |
| GCP Cloud Run (build, deploy, secrets) | [`DEPLOY_CLOUD_RUN.md`](DEPLOY_CLOUD_RUN.md) |
| Example env YAML for Cloud Run | [`examples/ham-api-cloud-run-env.yaml`](examples/ham-api-cloud-run-env.yaml) |
| Model recovery runbook | [`RUNBOOK_HAM_MODEL_RECOVERY.md`](RUNBOOK_HAM_MODEL_RECOVERY.md) |

## Chat, gateway, and skills

| Topic | Doc |
|-------|-----|
| Dashboard chat control plane (skills roadmap) | [`HAM_CHAT_CONTROL_PLANE.md`](HAM_CHAT_CONTROL_PLANE.md) |
| Hermes gateway (server-side adapter contract) | [`HERMES_GATEWAY_CONTRACT.md`](HERMES_GATEWAY_CONTRACT.md) |
| Gateway broker notes | [`HERMES_GATEWAY_BROKER.md`](HERMES_GATEWAY_BROKER.md) |

## Hardening and remediation

| Topic | Doc |
|-------|-----|
| Context Engine hardening and remediation order | [`HAM_HARDENING_REMEDIATION.md`](HAM_HARDENING_REMEDIATION.md) |

## Desktop and local control

| Topic | Doc |
|-------|-----|
| Local control v1 | [`desktop/local_control_v1.md`](desktop/local_control_v1.md) |
| Local web bridge MVP | [`desktop/local_web_bridge_mvp.md`](desktop/local_web_bridge_mvp.md) |
| Sidecar protocol v1 | [`desktop/local_control_sidecar_protocol_v1.md`](desktop/local_control_sidecar_protocol_v1.md) |
| Release pipeline | [`desktop/RELEASE_PIPELINE.md`](desktop/RELEASE_PIPELINE.md) |
| Live browser copilot v1 | [`desktop/live_browser_copilot_v1.md`](desktop/live_browser_copilot_v1.md) |

## Browser and capabilities

| Topic | Doc |
|-------|-----|
| Playwright browser runtime setup | [`BROWSER_RUNTIME_PLAYWRIGHT.md`](BROWSER_RUNTIME_PLAYWRIGHT.md) |
| Computer control pack v1 | [`capabilities/computer_control_pack_v1.md`](capabilities/computer_control_pack_v1.md) |
| Capability bundle directory v1 | [`capabilities/capability_bundle_directory_v1.md`](capabilities/capability_bundle_directory_v1.md) |

## Operator and product

| Topic | Doc |
|-------|-----|
| Team Hermes status (API vs desktop story) | [`TEAM_HERMES_STATUS.md`](TEAM_HERMES_STATUS.md) |
| Factory Droid contract | [`FACTORY_DROID_CONTRACT.md`](FACTORY_DROID_CONTRACT.md) |
| Droid runner service | [`HAM_DROID_RUNNER_SERVICE.md`](HAM_DROID_RUNNER_SERVICE.md) |
| Config trust model | [`config_trust_model.md`](config_trust_model.md) |

## Reference ecosystems (patterns only)

| Topic | Doc |
|-------|-----|
| Factory Droid | [`reference/factory-droid-reference.md`](reference/factory-droid-reference.md) |
| Hermes agent | [`reference/hermes-agent-reference.md`](reference/hermes-agent-reference.md) |
| OpenClaw | [`reference/openclaw-reference.md`](reference/openclaw-reference.md) |
| ElizaOS | [`reference/elizaos-reference.md`](reference/elizaos-reference.md) |

## Ham × agent experiments

| Topic | Doc |
|-------|-----|
| Architecture | [`ham-x-agent/architecture.md`](ham-x-agent/architecture.md) |
| Runbook | [`ham-x-agent/runbook.md`](ham-x-agent/runbook.md) |
| Env | [`ham-x-agent/env.md`](ham-x-agent/env.md) |
| Safety policy | [`ham-x-agent/safety-policy.md`](ham-x-agent/safety-policy.md) |
| Smoke testing | [`ham-x-agent/smoke-testing.md`](ham-x-agent/smoke-testing.md) |
| Phase 1 supervised loop | [`ham-x-agent/phase-1-supervised-loop.md`](ham-x-agent/phase-1-supervised-loop.md) |

## Deeper plans and audits

Larger planning and inventory docs (Hermes workspace lift, terminal parity, forensics) live under [`docs/`](./); browse the directory or search by filename if you need a specific audit.
