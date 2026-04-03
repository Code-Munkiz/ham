# Ham — Agent Context Index

This file declares which files are first-class project context. Any agent
working on this repo should read these before proposing changes.

## Architecture

- `VISION.md` — canonical architecture, five pillars, design principles

## Pillar modules

- `src/memory_heist.py` — Context Engine (repo scan, git state, config, sessions)
- `src/swarm_agency.py` — CrewAI orchestrator (agent + task definitions)
- `src/hermes_feedback.py` — Hermes critic (review loop, FTS5 learning)
- `src/tools/droid_executor.py` — Droid CLI tool (parallel shell execution)
- `src/llm_client.py` — LiteLLM / OpenRouter wiring

## Configuration & entry

- `main.py` — runtime entrypoint (CLI arg parsing, env load, crew assembly)
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

## Tests

- `tests/` — regression tests (bootstrap with `/test-context-regressions`)
