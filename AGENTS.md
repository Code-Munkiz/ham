# Ham — Agent Context Index

This file declares which files are first-class project context. Any agent
working on this repo should read these before proposing changes.

## Read order (recommended)

1. `VISION.md` — pillars, boundaries, and how components connect
2. This file — where implementation lives (see § *Git workflow* for direct-main testing; Cursor: `ham-direct-main-workflow.mdc`)
3. `SWARM.md` — repo coding instructions (loaded by `memory_heist`)
4. `PRODUCT_DIRECTION.md` — product lens: HAM-native model vs reference ecosystems
5. `docs/TEAM_HERMES_STATUS.md` (when changing Command Center, Activity, Capabilities, or desktop Hermes copy) — **API-side** vs **desktop-side** operator story, boundaries, troubleshooting

## Ham bet: memory, Hermes, and CLI-native muscle

Three ideas stay stable while execution backends evolve:

1. **Repo-grounded context (`memory_heist`)** — Workspace truth (scan, git, merged `.ham` config, instruction files, session compaction) is assembled once and injected into agents so supervision and planning do not hallucinate project state.

2. **Hermes learning loop (`hermes_feedback`)** — Critique and structured review over **evidence-shaped outcomes** (bridge/run envelopes, capped text). The goal is a compounding signal: routing and quality improve over time; durable institutional memory is still incremental (see `GAPS.md` and hardening docs).

3. **CLI-first execution surface** — Heavy work is delegated to **CLI-based agentic runtimes** (subprocess + framed IO), not re-embedded vendor HTTP stacks inside Ham. **Auth and account state stay with the tool** (its login flows, tokens on disk, device/browser steps). Ham supplies **scoped intent, policy limits, and capture**; Hermes reasons over **comparable envelopes** regardless of whether the muscle is Factory/Droid-style, Claude Code–style, ElizaOS-flavored hosts, OpenClaw-informed gateways, or future adapters—**one supervision vocabulary, many CLIs**.

**Narrow exception (interactive dashboard chat):** The Ham API may expose **`POST /api/chat`** with **HAM-native** JSON to the browser and implement it via a **server-side adapter** to an external OpenAI-compatible agent API (see `docs/HERMES_GATEWAY_CONTRACT.md`, `src/integrations/nous_gateway_client.py`). The browser **never** calls that gateway directly. This does **not** replace **`HermesReviewer`** / `main.py` critique-on-run flow—they stay separate.

Shipped muscle today centers on **Bridge + Droid executor** (`src/tools/droid_executor.py`, `src/bridge/`). Reference notes (patterns only, not parity targets): `docs/reference/factory-droid-reference.md`, `docs/reference/openclaw-reference.md`, `docs/reference/elizaos-reference.md`. Ham remains **HAM-native** in naming and contracts; see `PRODUCT_DIRECTION.md`.

## Architecture

- `.cursor/rules/ham-local-control-boundary.mdc` — local control boundary (web UI + Windows bridge, mandatory desktop/IDE lane, escalation patterns, ancillary cloud **`/api/browser`**, verify-first/minimal-diff; Linux **installers removed** — see rule file)
- `VISION.md` — canonical architecture, core pillars, design principles
- **`src/ham_cli/`** — HAM operator CLI v1 (`python -m src.ham_cli` or `./scripts/ham`): `doctor`, `status`, `api status`, **`desktop package win`** — diagnostics + **Windows** desktop packaging helpers; not chat/missions (see `main.py` for bridge/Hermes one-shot CLI)
- `docs/CONTROL_PLANE_RUN.md` — `ControlPlaneRun` substrate (v1 file-backed: `src/persistence/control_plane_run.py`): durable provider-neutral launch record (Cursor/Droid) + Cursor status updates, separate from bridge runs and audit JSONL; read API: `src/api/control_plane_runs.py` (`GET /api/control-plane-runs`, `GET /api/control-plane-runs/{ham_run_id}`) — not orchestration, queues, or mission graphs
- `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md` — what’s shipped vs partial vs out of scope for Cursor Cloud Agent + `ManagedMission`, and phased gap closure (correlation, optional Hermes-on-mission, honest E2E scope)
- `docs/MISSION_AWARE_FEED_CONTROLS.md` — mission-scoped live feed + operator controls (`mission_registry_id`); client transcript rendering over bounded feed `events`

## Pillar modules

- `src/hermes_feedback.py` — Hermes supervisory core + critic/learner surface (`HermesReviewer` MVP complete; supervisory wiring still transitional)
- `src/tools/droid_executor.py` — Droid execution engine (implementation-heavy execution; local self-orchestration while executing)
- `src/memory_heist.py` — Context Engine (repo scan, git state, config, sessions)
- `src/llm_client.py` — LiteLLM / OpenRouter wiring
- `src/swarm_agency.py` — Hermes-supervised **context assembly** (shared `ProjectContext` + per-role render budgets for Architect / routing / critic prompts); **not** a separate orchestration framework (no CrewAI)
- `src/registry/droids.py` — `DroidRecord` + `DroidRegistry` + `DEFAULT_DROID_REGISTRY` (builder, reviewer)
- `src/persistence/run_store.py` — read-side `RunStore` over `.ham/runs/*.json`
- `src/api/server.py` — FastAPI app: read API (`/api/status`, `/api/runs`, …) plus **`POST /api/chat`**, **`POST /api/chat/stream`** (see `src/api/chat.py` — optional `project_id` + **HAM active agent guidance** from Agent Builder; distinct from Cursor operator skills and Hermes CLI profiles), **`GET /api/cursor-skills`** (Cursor operator skills), **`GET /api/hermes-skills/*`** (Hermes **runtime** skills catalog + host probe + **Phase 2a** shared install preview/apply; see `src/api/hermes_skills.py`, `src/ham/hermes_skills_install.py`), **`GET /api/capability-library/*`** and **`POST .../save|remove|reorder`** (per-project **My library** of saved `hermes:` / `capdir:` catalog refs; `HAM_CAPABILITY_LIBRARY_WRITE_TOKEN`; see `src/api/capability_library.py`, `src/ham/capability_library/`), **`GET /api/cursor-subagents`**, **`GET /api/projects/{id}/agents`** (HAM agent builder profiles; on `app` in `src/api/server.py`), and **project settings** preview/apply (`src/api/project_settings.py`, `HAM_SETTINGS_WRITE_TOKEN` for mutating routes)
- `src/ham/cursor_skills_catalog.py` — loads `.cursor/skills` for chat control plane + API index (operator docs; **not** Hermes runtime skills)
- `src/ham/hermes_skills_catalog.py` — vendored Hermes-runtime catalog manifest (`src/ham/data/hermes_skills_catalog.json`)
- `scripts/build_hermes_skills_catalog.py` — regenerate catalog from pinned **NousResearch/hermes-agent** (`skills/` + `optional-skills/`); requires network unless `--repo-root` points at a checkout
- `src/ham/hermes_skills_probe.py` — read-only Hermes home / profile discovery (`HAM_HERMES_SKILLS_MODE=remote_only` for non-co-located APIs)
- `src/ham/hermes_skills_install.py` — Phase 2a shared-target install: HAM-managed bundles under `~/.hermes/ham-runtime-bundles/`, merge `skills.external_dirs` in Hermes `config.yaml`, atomic write, lock, backup + audit (`HAM_HERMES_SKILLS_SOURCE_ROOT` + `.ham-hermes-agent-commit` pin, `HAM_SKILLS_WRITE_TOKEN` for apply)
- `src/ham/cursor_subagents_catalog.py` — loads `.cursor/rules/subagent-*.mdc` for chat + **`GET /api/cursor-subagents`**
- `src/ham/ui_actions.py` — parse/validate `HAM_UI_ACTIONS_JSON` for chat → UI
- `src/ham/settings_write.py` — allowlisted writes to `.ham/settings.json` (backup + audit); includes **`agents`** subtree (HAM agent profiles + `primary_agent_id`)
- `src/ham/agent_profiles.py` — Pydantic models + validation for HAM agent profiles (Hermes runtime skill catalog ids on `skills: string[]`; not Hermes CLI profiles)
- `src/ham/active_agent_context.py` — compact **guidance** block from primary HAM agent profile + vendored Hermes catalog entries for `/api/chat` (context only; no install/execution)
- `docs/HAM_CHAT_CONTROL_PLANE.md` — chat + skills intent mapping roadmap

## Deploy (API on GCP)

- **Staging SOT:** GCP project **`clarity-staging-488201`**, region **`us-central1`**, Cloud Run **`ham-api`** — see `docs/DEPLOY_CLOUD_RUN.md` (Cursor key via **Secret Manager** `ham-cursor-api-key` → env `CURSOR_API_KEY`).
- `Dockerfile` — Cloud Run–style image (`uvicorn src.api.server:app`, `PORT` aware)
- `docs/DEPLOY_CLOUD_RUN.md` — Artifact Registry + `gcloud builds submit` + `gcloud run deploy` + env vars + **private Hermes on GCE** (Direct VPC egress preferred, Serverless VPC connector fallback)
- `docs/DEPLOY_HANDOFF.md` — Vercel + Cloud Run checklist (what to set in each host)
- `docs/examples/ham-api-cloud-run-env.yaml` — copy to `.gcloud/ham-api-env.yaml` for `--env-vars-file`
- `docs/HERMES_GATEWAY_CONTRACT.md` — server-side adapter to Hermes/OpenAI-compatible chat (streaming `http` mode)
- `scripts/verify_ham_api_deploy.sh` — CORS + `/api/chat` + stream smoke test; **fails if responses look like `mock`** unless `HAM_VERIFY_ALLOW_MOCK=1`
- `scripts/render_cloud_run_env.py` — merge `.env` secrets into env YAML for deploy (`OPENROUTER_API_KEY` for openrouter; **`HERMES_GATEWAY_API_KEY`** for `http` when set in `.env`)

## Configuration & entry

- `main.py` — runtime entrypoint (CLI arg parsing, env load, orchestration assembly)
- `SWARM.md` — project-level coding instructions (loaded by memory_heist)
- `AGENTS.md` — this file
- `requirements.txt` — Python dependencies
- `README.md` — project overview and pointers
- `.env.example` — environment variable template
- `.ham.json` / `.ham/settings.json` — project config (if present)

## Hardening & remediation

- `docs/HAM_HARDENING_REMEDIATION.md` — audit summary, continuation/parser coupling, remediation order, deferred work

## Git workflow (testing / direct-main)

For HAM testing work in this environment, prefer **`main` directly** — not feature branches or automatic PRs.

**Standing rule:** Do not create draft PRs by default. Do not run `gh pr create`, `gh pr ready`, `gh pr edit`, or suggest opening a PR / pushing a feature branch for review **unless** the user explicitly asks for a PR.

**Procedure:**

1. `git status --short --branch` and `git branch --show-current`.
2. If not on `main`: `git checkout main`, then `git pull origin main`.
3. Apply the requested change. Stage **only** intended files.
4. **Do not stage:** `.cursor/settings.json`, `desktop/live-smoke/`, repomix outputs, build artifacts, temp scripts, unrelated dirty files.
5. Run **scoped** tests for the touched area.
6. Commit on `main`: `git commit -m "<clear commit message>"`.
7. Push: `git push origin main`.

**Report:** commit hash, files changed, tests run, pushed yes/no, deploy/smoke status if applicable.

**If direct push to `main` is blocked** (branch protection, permissions): do **not** create a PR automatically. Stop and report `DIRECT_MAIN_PUSH_BLOCKED` with reason and required action.

**PR exception** — only when the user explicitly says e.g. “open a PR”, “make a draft PR”, “use feature branch”, or “do this as PR review”.

**Draft PRs:** Do not add PR clutter. Before substantial work, you may list and **classify** open draft PRs (superseded, docs-only safe to close, contains useful unmerged work, unknown); do **not** close or merge automatically until classified and the user approves a batch plan. Cursor enforces the short form of these rules in `.cursor/rules/ham-direct-main-workflow.mdc`.

**Separate cleanup run** — paste when you want a dedicated draft-PR audit (agents classify only; no auto-close/merge unless clearly safe):

```md
Clean up HAM draft PR clutter safely.

## Goal

There are many draft PRs for small docs notes. I want to stop accumulating PR clutter.

## Instructions

1. List all open draft PRs.

2. For each draft PR, classify:

- `SUPERSEDED_BY_MAIN`
- `DOCS_ONLY_SAFE_TO_CLOSE`
- `CONTAINS_UNMERGED_USEFUL_WORK`
- `UNKNOWN_REVIEW_NEEDED`

3. For each PR, report:
- PR number
- title
- branch
- changed files
- whether its commits are already in `main`
- recommended action

4. Do not close or merge anything yet unless clearly safe.

5. After classification, ask for approval with a batch plan:
- close these PRs
- merge these PRs
- leave these open
```

## Guidance

- `.cursor/rules/` — Cursor project rules (architecture, diffs, roles, vision sync)
- `.cursor/skills/` — eight reusable operator skills (see skills table in [`CURSOR_SETUP_HANDOFF.md`](CURSOR_SETUP_HANDOFF.md))
- `CURSOR_SETUP_HANDOFF.md` — human guide to rules, skills, subagents, commands
- `CURSOR_EXACT_SETUP_EXPORT.md` — verbatim snapshot of Cursor setup + first-class docs (regenerate via `python scripts/build_cursor_export.py`)
- `GAPS.md` — tracked gaps and active implementation notes

## Frontend (workspace UI)

- `desktop/` — Milestone 1 Electron shell (thin wrapper; see `desktop/README.md`); `npm start` after `npm run dev` in `frontend/`
- `frontend/` — Vite + React workspace; `npm run dev` (port 3000), `npm run lint` (`tsc --noEmit`)
- `frontend/src/pages/HermesSkills.tsx` — **Skills** catalog UI (`/skills`, redirect from `/hermes-skills`); distinct from Cursor operator skills; API remains `/api/hermes-skills/*`

## Tests

- `tests/test_memory_heist.py` — Context Engine + Phase 1/3 guardrails (23 cases)
- `tests/test_hermes_feedback.py` — Critic MVP + Phase 3 guardrails (7 cases)
- `tests/test_droid_registry.py` — Droid registry conventions (10 cases)
- Run: `python -m pytest` — full suite (`pytest.ini` sets `pythonpath = .`; run `pytest tests/ --collect-only -q` for current count — on the order of 1200+ tests)
- Other tests under `tests/` as added; bootstrap with `/test-context-regressions` for Context Engine focus

## Cursor Cloud specific instructions

### Services overview

| Service | Command | Port | Notes |
|---------|---------|------|-------|
| Backend API | `python3 scripts/run_local_api.py` | 8000 | Sets `HERMES_GATEWAY_MODE=mock` + loose Clerk by default |
| Frontend | `npm run dev` (in `frontend/`) | 3000 | Vite proxies `/api/*` to `:8000` automatically |

### Startup caveats

- **pytest is not in `requirements.txt`** — install separately: `pip install pytest`.
- The backend uses `scripts/run_local_api.py` for local dev (not bare `uvicorn`). It auto-loads `.env`, sets mock gateway mode, and disables Clerk auth enforcement. Alternatively use `python3 -m uvicorn src.api.server:app --host 0.0.0.0 --port 8000`.
- Create `.env` from `.env.example` before first run. Default mock mode needs no API keys.
- Frontend lint is `npm run lint --prefix frontend` (`tsc --noEmit`).
- Full test suite: `python3 -m pytest tests/ -q`. Some HAM-on-X reactive inbox tests may have pre-existing failures unrelated to setup.
- See `.cursor/skills/cloud-agent-starter/SKILL.md` for detailed per-area testing workflows and common quick fixes.

### HAM / Cursor Cloud Agent truth table

- **Cursor Cloud Agent** executes repo work (provider execution/runtime).
- **HAM** orchestrates missions — owns `ManagedMission` state, feed, audit, UI, follow-up/cancel controls.
- Browser never talks directly to Cursor: `Browser → HAM backend → Cursor SDK/API`.
- HAM remains the system of record; REST launch path remains primary.

### SDK bridge current truth

- SDK bridge is **live** (`HAM_CURSOR_SDK_BRIDGE_ENABLED=true`).
- It attaches to existing `bc-*` Cursor agents/runs via `src/integrations/cursor_sdk_bridge_client.py` + `bridge.mjs`.
- It streams provider-native events (`status`, `thinking`, `assistant_message`, `completed`) into HAM feed (backend bridge + SSE path to ingest; operators still poll `/feed` via HAM; no Cursor calls from the browser).
- Feed mode `sdk_stream_bridge`: native provider stream through backend bridge; frontend still talks only to HAM.
- Feed mode `rest_projection`: fallback REST refresh/projection (not provider-native streaming).
- Rollback: set `HAM_CURSOR_SDK_BRIDGE_ENABLED=false` — forces REST projection without changing launch path or frontend flow.

### Cloud Agent PR hygiene (prevent PR spam)

HAM appends deterministic PR/docs guardrails to **Cursor Cloud Agent** launch prompts (`src/ham/cursor_agent_workflow.py`, `CURSOR_AGENT_BASE_REVISION=cursor-agent-v2`). Humans and Cursor agents collaborating on Ham should behave the same way:

- **Default:** report or push commits to a branch **without** opening a PR unless the user explicitly requests one (`gh pr create` / “open a PR”).
- Do **not** open docs-only PRs unless explicitly requested. Prefer edits to **canonical** docs: `README.md`, `AGENTS.md`, `VISION.md`, `docs/README.md`, `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`, `docs/MISSION_AWARE_FEED_CONTROLS.md`, `docs/HAM_HARDENING_REMEDIATION.md`, `GAPS.md`, `.cursor/skills/**/SKILL.md`. **`CURSOR_EXACT_SETUP_EXPORT.md`** is regenerated via `python scripts/build_cursor_export.py` — not a hand-maintained prose source.
- Avoid duplicating identical “Cloud Agent truth” bullets across unrelated files when one canonical paragraph suffices.
- **One mission ↔ at most one GitHub PR** when a PR is explicitly allowed for that mission work.
- **Before opening a docs PR:** run  
  `gh pr list --repo <org>/<repo> --state open --limit 50`  
  and scan titles/branches (`gh pr view <n> --json files` helps). If overlapping docs intent exists → report **`OVERLAPPING_DOCS_PR_FOUND`** and extend the existing PR/list it — do **not** open parallel duplicates from the same automation.
- **Code vs docs cleanup:** do not lump unrelated observability/UI fixes together with unrelated doc sweeps unless the operator asked — separate PR scopes reduce reviewer noise.

When opening a permitted PR:

- Prefer titles like `docs(agent): …`, `fix(missions): …`, `feat(missions): …`, `chore(agent): …`.
- Mention **mission_registry_id / agent id** when known; list files touched; say **docs-only vs code-bearing**; list tests/commands run — see also direct-main discipline in `.cursor/rules/ham-direct-main-workflow.mdc` where applicable.
