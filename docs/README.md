# Ham documentation index

## Docs governance (what belongs where)

**`docs/` (tracked, canonical prose)** — Operational truth and design decisions the team revises together: roadmap, contracts, deploy runbooks, recovery runbooks, active architecture investigations that gate implementation, and **checked-in** examples (for example `examples/ham-api-cloud-run-env.yaml`). Root [`README.md`](../README.md) and this file are the primary entry points.

**Canonical doc freshness + links:** [`scripts/check_docs_freshness.py`](../scripts/check_docs_freshness.py) walks the tracked allowlist (`CANONICAL_DOCS` in that script—root `README.md`, `AGENTS.md`, `VISION.md`, `PRODUCT_DIRECTION.md`, `GAPS.md`, and this index), checks each was touched in git within **180 days**, and flags unresolved relative markdown targets. Run `python scripts/check_docs_freshness.py` locally before large doc-only changes; CI runs the same script as **warning-only** until the team promotes it.

**`docs/archive/` (tracked, when used)** — Superseded or historical write-ups we keep for auditability (moved here instead of deleted). **Do not** move a doc into `archive/` if [`HAM_ROADMAP.md`](HAM_ROADMAP.md), root `README.md`, deploy docs, or an active runbook still link to it without updating those links first.

**`docs/_scratch/` (local only, never commit)** — AI handoff notes, one-off verification dumps, draft bullets, and scratch planning. This path is **gitignored**; copy anything worth keeping into real doc paths and delete the scratch copy.

**`docs/_generated/` (local only, never commit)** — Regenerated inventories, repomix-style dumps, or machine-exported lists you do not want in history. **Gitignored.** Prefer small curated references under `docs/reference/` when a pattern doc is needed.

**Repomix / bundle dumps** — `docs/repomix-*` is **ignored** by [`.gitignore`](../.gitignore); **`repomix-output-*.txt`** at the **repository root** is also ignored. If another doc cites a repomix filename, treat it as an **optional local artifact** to regenerate, not a committed dependency.

**Never commit** — Provider keys, tokens, live env dumps, raw `gs://` object paths in user-facing artifacts, local desktop smoke binaries (see `desktop/live-smoke/` ignore), `node_modules` under SDK lab scripts, or Cursor **personal** settings / **plan** scratch under `.cursor/` (team rules and skills under `.cursor/rules/` and `.cursor/skills/` **remain tracked** when they are project defaults).

---

Canonical architecture and agent context live at the repo root: [`VISION.md`](../VISION.md), [`AGENTS.md`](../AGENTS.md), [`SWARM.md`](../SWARM.md), [`GAPS.md`](../GAPS.md).

**Not source of truth:** generated exports and tool-local settings (for example [`CURSOR_EXACT_SETUP_EXPORT.md`](../CURSOR_EXACT_SETUP_EXPORT.md), or the gitignored .cursor/settings.json file) are snapshots or editor config—defer to git-tracked canonical docs unless you deliberately refresh an export script.

**Builder Platform (aspirational):** [`BUILDER_PLATFORM_NORTH_STAR.md`](BUILDER_PLATFORM_NORTH_STAR.md) — phased roadmap (orthogonal to workspace phases in [`HAM_ROADMAP.md`](HAM_ROADMAP.md)); shipped pillars remain [`VISION.md`](../VISION.md).

**Cursor / contributor setup:** rules, skills, subagents, and slash-command workflows are summarized in [`CURSOR_SETUP_HANDOFF.md`](../CURSOR_SETUP_HANDOFF.md) (canonical copies live under `.cursor/rules/` and `.cursor/skills/`).

**Cloud Agent / HAM VM Git:** these environments use **branch → push branch → open PR into `main`**. Direct **`git push origin main`** and **force-push to `main`** are forbidden — see [`AGENTS.md`](../AGENTS.md) (**Cloud Agent / HAM VM Git policy**).

**Overlapping docs-only PRs:** Prefer editing canonical docs in place instead of spawning duplicate PR churn; overlap checks and tokens live under [`AGENTS.md`](../AGENTS.md) and ship in deterministic launch prompts (`CURSOR_AGENT_BASE_REVISION` in `cursor_agent_workflow.py`). When you have GitHub CLI auth, run `gh pr list --repo <org>/<repo> --state open --limit 50` before a docs-only PR. If `gh` is unavailable or returns auth errors (for example **HTTP 401** / “Bad credentials”), you cannot complete the overlap scan from automation alone—coordinate with a human who has `gh auth login`, or extend an existing open PR or branch manually rather than opening parallel duplicates.

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

**HAM operator CLI** (diagnostics and packaging helpers, not chat/missions): `python -m src.ham_cli` or `./scripts/ham` — module tree `src/ham_cli/`; see [`AGENTS.md`](../AGENTS.md).

## Cursor Cloud Agent and managed missions

| Doc | Purpose |
|-----|---------|
| [ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) | Shipped vs partial vs roadmap; SDK bridge vs REST fallbacks |
| [MISSION_AWARE_FEED_CONTROLS.md](MISSION_AWARE_FEED_CONTROLS.md) | Feed + controls scoped by `mission_registry_id` |
| [CONTROL_PLANE_RUN.md](CONTROL_PLANE_RUN.md) | `ControlPlaneRun` substrate (factual runs, not a mission graph) |

## Chat, gateway, and capabilities

**Workspace Connected Tools (Claude Agent SDK):** no standalone doc — implementation is `src/api/workspace_tools.py` + `src/ham/worker_adapters/claude_agent_adapter.py`; operator env and semantics are in [`.env.example`](../.env.example) (search `CLAUDE_AGENT`) and the pillar index in [`AGENTS.md`](../AGENTS.md). This path is readiness + optional gated smoke only; it does not replace Bridge/Droid or Hermes supervision.

| Doc | Purpose |
|-----|---------|
| [HAM_ROADMAP.md](HAM_ROADMAP.md) | Workspace attachments, Phase 2B PDF export, voice/video/RAG sequencing (cross-cutting) |
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
| [HAM_PRELAUNCH_SMOKE_CHECKLIST.md](HAM_PRELAUNCH_SMOKE_CHECKLIST.md) | Human checklist before ship (adapted from quarantined rescue notes; Ham paths only) |
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
| [../.cursor/rules/hermes-workspace-repomix-ssot.mdc](../.cursor/rules/hermes-workspace-repomix-ssot.mdc) | Hermes Workspace UI/UX parity: repomix SSOT must exist before parity implementation |

## HAM-on-X (social / reactive)

| Path | Purpose |
|------|---------|
| [ham-x-agent/](ham-x-agent/) | Architecture, env, runbook, smoke, safety for HAM-on-X |

Other topical docs here (capabilities packs, workstation plans, etc.) remain discoverable by filename; search the repo when you need a subsystem not listed above.
