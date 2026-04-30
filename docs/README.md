# Ham documentation index

Use this page to find the right doc without scanning all of `docs/`. For the full agent-oriented module map, see [AGENTS.md](../AGENTS.md) at the repo root. Architecture and pillar status live in [VISION.md](../VISION.md).

## Orientation

| Topic | Doc |
|--------|-----|
| Architecture, pillars, current vs target | [VISION.md](../VISION.md) |
| Agent context index (APIs, paths, deploy) | [AGENTS.md](../AGENTS.md) |
| Tracked gaps | [GAPS.md](../GAPS.md) |
| Repo coding instructions (loaded by Context Engine) | [SWARM.md](../SWARM.md) |
| Product lens (HAM-native vs reference ecosystems) | [PRODUCT_DIRECTION.md](../PRODUCT_DIRECTION.md) |

## Deploy and staging

| Topic | Doc |
|--------|-----|
| Vercel + Cloud Run handoff | [DEPLOY_HANDOFF.md](DEPLOY_HANDOFF.md) |
| GCP Cloud Run (build, deploy, env, Hermes on GCE) | [DEPLOY_CLOUD_RUN.md](DEPLOY_CLOUD_RUN.md) |
| Hermes gateway (server-side chat adapter contract) | [HERMES_GATEWAY_CONTRACT.md](HERMES_GATEWAY_CONTRACT.md) |

## Chat, operator, and control plane

| Topic | Doc |
|--------|-----|
| Chat control plane (skills intent, roadmap) | [HAM_CHAT_CONTROL_PLANE.md](HAM_CHAT_CONTROL_PLANE.md) |
| Workspace chat → Cloud Agent routing (smoke note) | [HAM_CLOUD_AGENT_ROUTING_SMOKE.md](HAM_CLOUD_AGENT_ROUTING_SMOKE.md) |
| Harness / provider contract | [HARNESS_PROVIDER_CONTRACT.md](HARNESS_PROVIDER_CONTRACT.md) |

## Cloud Agent and managed missions

| Topic | Doc |
|--------|-----|
| Managed missions roadmap (shipped vs partial vs out of scope) | [ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) |
| Control plane runs (v1 factual records, not a mission graph) | [CONTROL_PLANE_RUN.md](CONTROL_PLANE_RUN.md) |

## Desktop, bridge, and local control

| Topic | Doc |
|--------|-----|
| Desktop local control v1 | [desktop/local_control_v1.md](desktop/local_control_v1.md) |
| Local web bridge MVP | [desktop/local_web_bridge_mvp.md](desktop/local_web_bridge_mvp.md) |
| Sidecar protocol | [desktop/local_control_sidecar_protocol_v1.md](desktop/local_control_sidecar_protocol_v1.md) |
| Release pipeline (desktop) | [desktop/RELEASE_PIPELINE.md](desktop/RELEASE_PIPELINE.md) |
| Team operator story (API vs desktop Hermes) | [TEAM_HERMES_STATUS.md](TEAM_HERMES_STATUS.md) |

## Browser and capabilities

| Topic | Doc |
|--------|-----|
| Playwright `/api/browser` setup | [BROWSER_RUNTIME_PLAYWRIGHT.md](BROWSER_RUNTIME_PLAYWRIGHT.md) |
| Computer control pack | [capabilities/computer_control_pack_v1.md](capabilities/computer_control_pack_v1.md) |
| Capability bundle directory | [capabilities/capability_bundle_directory_v1.md](capabilities/capability_bundle_directory_v1.md) |

## Hermes workspace and gateway

| Topic | Doc |
|--------|-----|
| Hermes gateway broker (Path B snapshot, etc.) | [HERMES_GATEWAY_BROKER.md](HERMES_GATEWAY_BROKER.md) |
| Factory Droid contract | [FACTORY_DROID_CONTRACT.md](FACTORY_DROID_CONTRACT.md) |
| Droid runner service | [HAM_DROID_RUNNER_SERVICE.md](HAM_DROID_RUNNER_SERVICE.md) |

## HAM-on-X (social agent)

| Topic | Doc |
|--------|-----|
| Runbook | [ham-x-agent/runbook.md](ham-x-agent/runbook.md) |
| Safety policy | [ham-x-agent/safety-policy.md](ham-x-agent/safety-policy.md) |
| Architecture | [ham-x-agent/architecture.md](ham-x-agent/architecture.md) |

## Hardening and remediation

| Topic | Doc |
|--------|-----|
| Context Engine hardening / remediation order | [HAM_HARDENING_REMEDIATION.md](HAM_HARDENING_REMEDIATION.md) |

## Reference notes (patterns only)

| Topic | Doc |
|--------|-----|
| Factory Droid | [reference/factory-droid-reference.md](reference/factory-droid-reference.md) |
| Hermes agent | [reference/hermes-agent-reference.md](reference/hermes-agent-reference.md) |
| OpenClaw / ElizaOS | [reference/openclaw-reference.md](reference/openclaw-reference.md), [reference/elizaos-reference.md](reference/elizaos-reference.md) |

## Historical / planning (use with care)

Some files under `docs/` are inventories, lift plans, or verification notes. Prefer **VISION.md** and **AGENTS.md** for “what is shipped” truth; cross-check dates and filenames in long-lived planning docs before relying on them.
