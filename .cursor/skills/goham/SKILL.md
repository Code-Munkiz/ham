---
name: goham
description: >-
  Guides conversational navigation of the Ham dashboard: settings sections, projects,
  Droids/registry, runs and activity, and how to scaffold sub-agent workflows or new
  assets using existing APIs and configs. Use when the user wants natural-language help
  finding settings, understanding Hermes vs Droid roles, creating workflows or agents, or
  pairing chat with the workspace UI without reading raw logs.
---

# GoHam — conversational product navigation

## When to use

- User asks **where** something lives in Ham (settings, API, CLI).
- User wants **step-by-step** setup: project, Droid profile, run inspection, context engine.
- User is **designing or wiring** dashboard chat and needs **accurate** product truth (sections, routes, pillars).
- User mentions **sub-agent workflows** or **creating** registry/workspace artifacts—ground answers in this repo, not generic agent tutorials.

## Read order

1. `AGENTS.md` — where implementation lives.
2. `VISION.md` — pillars and boundaries.
3. This skill — **UI/API/workflow map** (keep in sync when navigation changes).
4. Repo `SWARM.md` — project coding instructions.

## Pillars (short)

| Piece | Module(s) | Role |
|-------|-----------|------|
| Supervisory / critic | `src/hermes_feedback.py` | Review, learning signals; not the primary chat product unless wired. |
| Execution | `src/tools/droid_executor.py`, Bridge | Heavy work via CLI subprocess; auth stays with the tool. |
| Context | `src/memory_heist.py` | Repo scan, git, config, sessions—inject for grounded NL. |
| LLM | `src/llm_client.py` | Model calls; keys server-side. |
| Hermes-supervised context | `src/swarm_agency.py` | Single shared `ProjectContext` discovery + per-role prompts; **Hermes-led** orchestration only (no CrewAI). |
| API | `src/api/server.py` | Dashboard backend; extend with chat when implemented. |

## Conversational layer (intent)

- **Skill alone** improves accuracy for agents (e.g. Cursor) that load it.
- **Product “talk to Ham”** still needs in-app chat wired to the backend plus optional **actions** (API calls, deep links). When chat is stub-only, tell the user the **exact** UI path or `curl`/endpoint.

## Guardrails

- Do not invent settings tabs or API paths—**read** `frontend` and `src/api/server.py` or documented reference when unsure.
- Do not expose secrets in chat; API keys stay server/env.
- If Hermes **Agent** (Nous product) vs **Hermes** (this repo critic) is ambiguous, disambiguate once.

## Verification

- Instructions match current `AGENTS.md` and actual routes/settings IDs after IA changes.
- Prefer linking to canonical docs over duplicating `VISION.md`.
