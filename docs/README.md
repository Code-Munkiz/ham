# Ham documentation index

Canonical architecture and agent context live at the repo root: [VISION.md](../VISION.md), [AGENTS.md](../AGENTS.md), [GAPS.md](../GAPS.md), [SWARM.md](../SWARM.md).

Use this page to find **topic-specific** docs under `docs/`.

## API, deploy, and handoff

| Doc | Purpose |
|-----|---------|
| [DEPLOY_CLOUD_RUN.md](DEPLOY_CLOUD_RUN.md) | GCP Artifact Registry, Cloud Run deploy, env vars, private Hermes |
| [DEPLOY_HANDOFF.md](DEPLOY_HANDOFF.md) | Vercel + Cloud Run checklist (CORS, secrets, verify script) |
| [examples/ham-api-cloud-run-env.yaml](examples/ham-api-cloud-run-env.yaml) | Example env file for `--env-vars-file` |

## Chat, gateway, and capabilities

| Doc | Purpose |
|-----|---------|
| [HAM_CHAT_CONTROL_PLANE.md](HAM_CHAT_CONTROL_PLANE.md) | Dashboard chat, skills intent mapping, roadmap |
| [HERMES_GATEWAY_CONTRACT.md](HERMES_GATEWAY_CONTRACT.md) | Server-side OpenAI-compatible adapter contract |
| [HERMES_GATEWAY_BROKER.md](HERMES_GATEWAY_BROKER.md) | Command Center broker snapshot (Path B/C) |
| [TEAM_HERMES_STATUS.md](TEAM_HERMES_STATUS.md) | API vs desktop operator story and boundaries |
| [capabilities/capability_bundle_directory_v1.md](capabilities/capability_bundle_directory_v1.md) | Capability bundle directory spec |
| [capabilities/computer_control_pack_v1.md](capabilities/computer_control_pack_v1.md) | Computer control pack v1 spec |

## Desktop, local control, and browser

| Doc | Purpose |
|-----|---------|
| [desktop/local_control_v1.md](desktop/local_control_v1.md) | Local Control v1 spec |
| [desktop/local_control_sidecar_protocol_v1.md](desktop/local_control_sidecar_protocol_v1.md) | Sidecar protocol (design) |
| [desktop/local_web_bridge_mvp.md](desktop/local_web_bridge_mvp.md) | Web app → local Windows bridge MVP |
| [desktop/live_browser_copilot_v1.md](desktop/live_browser_copilot_v1.md) | Live Browser Copilot (desktop) |
| [desktop/RELEASE_PIPELINE.md](desktop/RELEASE_PIPELINE.md) | Desktop tagged release pipeline |
| [BROWSER_RUNTIME_PLAYWRIGHT.md](BROWSER_RUNTIME_PLAYWRIGHT.md) | API Playwright browser runtime setup |
| [goham/browser_smoke.md](goham/browser_smoke.md) | Historical / future GoHAM browser smoke notes |

## Control plane, missions, and contracts

| Doc | Purpose |
|-----|---------|
| [CONTROL_PLANE_RUN.md](CONTROL_PLANE_RUN.md) | `ControlPlaneRun` durable launch record (v1) |
| [ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) | Managed Cloud Agent + mission record roadmap |
| [HAM_CLOUD_AGENT_ROUTING_SMOKE.md](HAM_CLOUD_AGENT_ROUTING_SMOKE.md) | Cloud Agent routing smoke (workspace chat) |
| [FACTORY_DROID_CONTRACT.md](FACTORY_DROID_CONTRACT.md) | Factory Droid contract notes |
| [HAM_DROID_RUNNER_SERVICE.md](HAM_DROID_RUNNER_SERVICE.md) | Droid runner service notes |
| [HARNESS_PROVIDER_CONTRACT.md](HARNESS_PROVIDER_CONTRACT.md) | Harness provider contract |

## Hardening, config, and recovery

| Doc | Purpose |
|-----|---------|
| [HAM_HARDENING_REMEDIATION.md](HAM_HARDENING_REMEDIATION.md) | Context Engine audit, remediation order |
| [config_trust_model.md](config_trust_model.md) | Config trust and validation model |
| [RUNBOOK_HAM_MODEL_RECOVERY.md](RUNBOOK_HAM_MODEL_RECOVERY.md) | Model recovery runbook |

## HAM-on-X (social agent)

| Doc | Purpose |
|-----|---------|
| [ham-x-agent/architecture.md](ham-x-agent/architecture.md) | Phase 1 architecture |
| [ham-x-agent/phase-1-supervised-loop.md](ham-x-agent/phase-1-supervised-loop.md) | Supervised loop |
| [ham-x-agent/runbook.md](ham-x-agent/runbook.md) | Operator runbook |
| [ham-x-agent/env.md](ham-x-agent/env.md) | Environment variables |
| [ham-x-agent/safety-policy.md](ham-x-agent/safety-policy.md) | Safety policy |
| [ham-x-agent/smoke-testing.md](ham-x-agent/smoke-testing.md) | Smoke testing |

## Reference (patterns, not parity targets)

| Doc | Purpose |
|-----|---------|
| [reference/factory-droid-reference.md](reference/factory-droid-reference.md) | Factory / Droid patterns |
| [reference/openclaw-reference.md](reference/openclaw-reference.md) | OpenClaw patterns |
| [reference/elizaos-reference.md](reference/elizaos-reference.md) | ElizaOS patterns |
| [reference/hermes-agent-reference.md](reference/hermes-agent-reference.md) | Hermes / hermes-agent pointer |

## Plans, workspace, and misc

| Doc | Purpose |
|-----|---------|
| [WORKSPACE_JOBS_TASKS_BRIDGE.md](WORKSPACE_JOBS_TASKS_BRIDGE.md) | Jobs & tasks bridge |
| [WORKSTATION_P1_MULTI_ROOT.md](WORKSTATION_P1_MULTI_ROOT.md) | Deferred multi-root workstation notes |
| [WHOLE_HERMES_WORKSPACE_LIFT_PLAN.md](WHOLE_HERMES_WORKSPACE_LIFT_PLAN.md) | Hermes workspace lift strategy |
| [PHASE0_HERMES_WORKSPACE_INVENTORY.md](PHASE0_HERMES_WORKSPACE_INVENTORY.md), [PHASE1_IMPLEMENTATION.md](PHASE1_IMPLEMENTATION.md) | Phase inventory / implementation |
| [HERMES_WORKSPACE_FEATURE_MATRIX.md](HERMES_WORKSPACE_FEATURE_MATRIX.md), [HERMES_WORKSPACE_FILES_TERMINAL_BRIDGE.md](HERMES_WORKSPACE_FILES_TERMINAL_BRIDGE.md), [HERMES_WORKSPACE_FULL_IA_INVENTORY.md](HERMES_WORKSPACE_FULL_IA_INVENTORY.md) | Workspace feature and IA notes |
| [TERMINAL_PTY_PARITY.md](TERMINAL_PTY_PARITY.md) | Terminal PTY parity |
| [RELEVANCE_SCORING.md](RELEVANCE_SCORING.md) | Context relevance scoring |
| [VOICE_MVP_README.md](VOICE_MVP_README.md) | Voice MVP notes |
| [LOCAL_COMPANION_FUTURE.md](LOCAL_COMPANION_FUTURE.md) | Local companion future direction |
| [HAM_SHELL_PRESERVING_REBUILD_PLAN.md](HAM_SHELL_PRESERVING_REBUILD_PLAN.md) | Shell-preserving rebuild plan |
| [OPENCODE_VERIFICATION.md](OPENCODE_VERIFICATION.md), [OPENCODE_VERIFICATION_RESULT.md](OPENCODE_VERIFICATION_RESULT.md) | OpenCode verification |
| [HERMES_UPSTREAM_CONTRACT_AUDIT.md](HERMES_UPSTREAM_CONTRACT_AUDIT.md) | Upstream contract audit |
| [forensics/hermes_workspace_cleanup_audit.md](forensics/hermes_workspace_cleanup_audit.md) | Legacy forensic cleanup audit |

New docs should be linked here when they are meant for general navigation (optional for tiny one-off notes).
