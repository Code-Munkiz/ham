# Ham — Agent Context Index

This file declares which files are first-class project context. Any agent
working on this repo should read these before proposing changes.

## Read order (recommended)

1. `VISION.md` — pillars, boundaries, and how components connect
2. This file — where implementation lives
3. `SWARM.md` — repo coding instructions (loaded by `memory_heist`)
4. `PRODUCT_DIRECTION.md` — product lens: HAM-native model vs reference ecosystems

## Ham bet: memory, Hermes, and CLI-native muscle

Three ideas stay stable while execution backends evolve:

1. **Repo-grounded context (`memory_heist`)** — Workspace truth (scan, git, merged `.ham` config, instruction files, session compaction) is assembled once and injected into agents so supervision and planning do not hallucinate project state.

2. **Hermes learning loop (`hermes_feedback`)** — Critique and structured review over **evidence-shaped outcomes** (bridge/run envelopes, capped text). The goal is a compounding signal: routing and quality improve over time; durable institutional memory is still incremental (see `GAPS.md` and hardening docs).

3. **CLI-first execution surface** — Heavy work is delegated to **CLI-based agentic runtimes** (subprocess + framed IO), not re-embedded vendor HTTP stacks inside Ham. **Auth and account state stay with the tool** (its login flows, tokens on disk, device/browser steps). Ham supplies **scoped intent, policy limits, and capture**; Hermes reasons over **comparable envelopes** regardless of whether the muscle is Factory/Droid-style, Claude Code–style, ElizaOS-flavored hosts, OpenClaw-informed gateways, or future adapters—**one supervision vocabulary, many CLIs**.

**Narrow exception (interactive dashboard chat):** The Ham API may expose **`POST /api/chat`** with **HAM-native** JSON to the browser and implement it via a **server-side adapter** to an external OpenAI-compatible agent API (see `docs/HERMES_GATEWAY_CONTRACT.md`, `src/integrations/nous_gateway_client.py`). The browser **never** calls that gateway directly. This does **not** replace **`HermesReviewer`** / `main.py` critique-on-run flow—they stay separate.

Shipped muscle today centers on **Bridge + Droid executor** (`src/tools/droid_executor.py`, `src/bridge/`). Reference notes (patterns only, not parity targets): `docs/reference/factory-droid-reference.md`, `docs/reference/openclaw-reference.md`, `docs/reference/elizaos-reference.md`. Ham remains **HAM-native** in naming and contracts; see `PRODUCT_DIRECTION.md`.

## Architecture

- `VISION.md` — canonical architecture, core pillars, design principles

## Pillar modules

- `src/hermes_feedback.py` — Hermes supervisory core + critic/learner surface (`HermesReviewer` MVP complete; supervisory wiring still transitional)
- `src/tools/droid_executor.py` — Droid execution engine (implementation-heavy execution; local self-orchestration while executing)
- `src/memory_heist.py` — Context Engine (repo scan, git state, config, sessions)
- `src/llm_client.py` — LiteLLM / OpenRouter wiring
- `src/swarm_agency.py` — Hermes-supervised **context assembly** (shared `ProjectContext` + per-role render budgets for Architect / routing / critic prompts); **not** a separate orchestration framework (no CrewAI)
- `src/registry/droids.py` — `DroidRecord` + `DroidRegistry` + `DEFAULT_DROID_REGISTRY` (builder, reviewer)
- `src/persistence/run_store.py` — read-side `RunStore` over `.ham/runs/*.json`
- `src/api/server.py` — FastAPI app: read API (`/api/status`, `/api/runs`, …) plus **`POST /api/chat`**, **`POST /api/chat/stream`** (see `src/api/chat.py`), **`GET /api/cursor-skills`**, **`GET /api/cursor-subagents`**, and **project settings** preview/apply (`src/api/project_settings.py`, `HAM_SETTINGS_WRITE_TOKEN` for mutating routes)
- `src/ham/cursor_skills_catalog.py` — loads `.cursor/skills` for chat control plane + API index
- `src/ham/cursor_subagents_catalog.py` — loads `.cursor/rules/subagent-*.mdc` for chat + **`GET /api/cursor-subagents`**
- `src/ham/ui_actions.py` — parse/validate `HAM_UI_ACTIONS_JSON` for chat → UI
- `src/ham/settings_write.py` — allowlisted writes to `.ham/settings.json` (backup + audit)
- `docs/HAM_CHAT_CONTROL_PLANE.md` — chat + skills intent mapping roadmap

## Deploy (API on GCP)

- `Dockerfile` — Cloud Run–style image (`uvicorn src.api.server:app`, `PORT` aware)
- `docs/DEPLOY_CLOUD_RUN.md` — Artifact Registry + `gcloud builds submit` + `gcloud run deploy` + env vars
- `docs/DEPLOY_HANDOFF.md` — Vercel + Cloud Run checklist (what to set in each host)
- `docs/examples/ham-api-cloud-run-env.yaml` — copy to `.gcloud/ham-api-env.yaml` for `--env-vars-file`
- `scripts/verify_ham_api_deploy.sh` — CORS + `/api/chat` smoke test against a deployed API
- `scripts/render_cloud_run_env.py` — merge `.env` into `.gcloud/ham-api-env.yaml` for `gcloud run deploy --env-vars-file` (avoids committing OpenRouter keys)

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

## Guidance

- `.cursor/rules/` — Cursor project rules (architecture, diffs, roles, vision sync)
- `.cursor/skills/` — reusable agent skills (hardening, wiring, auditing, testing)
- `CURSOR_SETUP_HANDOFF.md` — human guide to rules, skills, subagents, commands
- `CURSOR_EXACT_SETUP_EXPORT.md` — verbatim snapshot of Cursor setup + first-class docs (regenerate via `python scripts/build_cursor_export.py`)
- `GAPS.md` — tracked gaps and active implementation notes

## Frontend (workspace UI)

- `frontend/` — Vite + React workspace; `npm run dev` (port 3000), `npm run lint` (`tsc --noEmit`)

## Tests

- `tests/test_memory_heist.py` — Context Engine + Phase 1/3 guardrails (18 cases)
- `tests/test_hermes_feedback.py` — Critic MVP + Phase 3 guardrails (7 cases)
- `tests/test_droid_registry.py` — Droid registry conventions (10 cases)
- Run: `python -m pytest` — full suite (`pytest.ini` sets `pythonpath = .`; 158+ cases as of UI actions)
- Other tests under `tests/` as added; bootstrap with `/test-context-regressions` for Context Engine focus
