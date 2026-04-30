# Ham documentation index

Repo-root narrative and architecture: [VISION.md](../VISION.md), [AGENTS.md](../AGENTS.md), [GAPS.md](../GAPS.md), [PRODUCT_DIRECTION.md](../PRODUCT_DIRECTION.md).

## Deploy and environments

- [DEPLOY_CLOUD_RUN.md](DEPLOY_CLOUD_RUN.md) — Artifact Registry, Cloud Run, secrets, private Hermes on GCE
- [DEPLOY_HANDOFF.md](DEPLOY_HANDOFF.md) — Vercel + Cloud Run checklist
- [examples/ham-api-cloud-run-env.yaml](examples/ham-api-cloud-run-env.yaml) — env file template for `--env-vars-file`

## Chat, gateway, and control plane

- [HAM_CHAT_CONTROL_PLANE.md](HAM_CHAT_CONTROL_PLANE.md) — chat skills intent and roadmap
- [HERMES_GATEWAY_CONTRACT.md](HERMES_GATEWAY_CONTRACT.md) — server-side OpenAI-compatible adapter
- [HERMES_GATEWAY_BROKER.md](HERMES_GATEWAY_BROKER.md) — dashboard broker snapshot (Path B/C)
- [CONTROL_PLANE_RUN.md](CONTROL_PLANE_RUN.md) — durable control-plane run records (read API)

## Cloud agents and missions

- [ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) — shipped vs partial vs out of scope

## Desktop, browser, and local control

- [desktop/local_control_v1.md](desktop/local_control_v1.md) — Windows bridge, policy, kill switch
- [BROWSER_RUNTIME_PLAYWRIGHT.md](BROWSER_RUNTIME_PLAYWRIGHT.md) — in-process Playwright / Chromium setup
- [desktop/README.md](../desktop/README.md) — Electron shell (see repo `desktop/`)

## Hardening and contracts

- [HAM_HARDENING_REMEDIATION.md](HAM_HARDENING_REMEDIATION.md) — Context Engine and critic remediation order
- [FACTORY_DROID_CONTRACT.md](FACTORY_DROID_CONTRACT.md) — Droid invocation modes and boundaries
- [TEAM_HERMES_STATUS.md](TEAM_HERMES_STATUS.md) — API vs desktop operator story

## HAM-on-X (experimental)

- [ham-x-agent/](ham-x-agent/) — architecture, env, runbook, smoke testing, safety policy
