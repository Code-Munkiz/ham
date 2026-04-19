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

Shipped muscle today centers on **Bridge + Droid executor** (`src/tools/droid_executor.py`, `src/bridge/`). Reference notes (patterns only, not parity targets): `docs/reference/factory-droid-reference.md`, `docs/reference/openclaw-reference.md`, `docs/reference/elizaos-reference.md`. Ham remains **HAM-native** in naming and contracts; see `PRODUCT_DIRECTION.md`.

## Architecture

- `VISION.md` — canonical architecture, core pillars, design principles

## Pillar modules

- `src/hermes_feedback.py` — Hermes supervisory core + critic/learner surface (`HermesReviewer` MVP complete; supervisory wiring still transitional)
- `src/tools/droid_executor.py` — Droid execution engine (implementation-heavy execution; local self-orchestration while executing)
- `src/memory_heist.py` — Context Engine (repo scan, git state, config, sessions)
- `src/llm_client.py` — LiteLLM / OpenRouter wiring
- `src/swarm_agency.py` — transitional orchestration scaffold pending migration to Hermes-supervised flow
- `src/registry/droids.py` — `DroidRecord` + `DroidRegistry` + `DEFAULT_DROID_REGISTRY` (builder, reviewer)
- `src/persistence/run_store.py` — read-side `RunStore` over `.ham/runs/*.json`
- `src/api/server.py` — thin FastAPI read API (`/api/status`, `/api/runs`, `/api/runs/{run_id}`, `/api/profiles`, `/api/droids`, `/api/context-engine`, `/api/projects/{id}/context-engine`)

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
- Run: `python -m pytest` — full suite (115 passed, 1 skipped as of Phase 10)
- Other tests under `tests/` as added; bootstrap with `/test-context-regressions` for Context Engine focus
