# Ham — Vision & Architecture

## What Ham Is

Ham is an open-source, multi-agent autonomous developer swarm that executes
the full Software Development Life Cycle (SDLC). It is not a chatbot wrapper.
It is an opinionated assembly line: plan, build, review, learn, repeat.

**Orchestration contract:** supervisory orchestration is **Hermes-led only**.
There is **no CrewAI** (or any other third-party orchestration framework) in
the architecture. `src/swarm_agency.py` assembles per-role context for
Hermes-supervised reasoning surfaces; it does not constitute a parallel
orchestrator.

## The Four Core Pillars

### 1. Supervisory Core — Hermes

Hermes is the supervisory control plane for the swarm. It coordinates droids,
routes jobs, critiques outputs, and accumulates learning signals over time.
Hermes owns orchestration and quality policy at the system level.

Hermes may self-handle only tiny, bounded, critic-native tasks (for example:
small review normalization or bounded policy checks). Hermes is not the
primary execution engine.

### 2. Execution Engine — Factory Droid CLI

Factory Droid CLI is the execution-heavy implementation engine. Droid performs
code and shell work (scaffolding, edits, tests, refactors, command execution)
and may self-orchestrate locally while executing delegated work.

Droid is not a dumb worker: it can perform bounded local planning and
sequencing inside an assigned execution job. Ambiguous execution work defaults
to Droid.

### 3. Context Engine — memory_heist.py

Adapted from Claude Code's context-awareness runtime. This module gives every
agent in the swarm a grounded understanding of the local repository:

- **Workspace scanning**: filesystem tree, file inventory, ignore rules.
- **Instruction file discovery**: hierarchical SWARM.md / AGENTS.md loading
  from project root up through ancestors.
- **Config discovery**: `.ham.json` / `.ham/settings.json` merge chain.
- **Git state capture**: status, diff, recent log — injected into prompts so
  agents know what changed and what's staged.
- **Session compaction**: conversation history summarization and persistence
  so agents can survive context window limits across long tasks (including
  tool-output pruning and config-driven compaction thresholds).
- **Instruction hygiene**: scanning of discovered instruction files for
  obvious injection patterns and invisible unicode before injection into
  rendered context.

The Context Engine does NOT make decisions. It assembles ground truth and
injects it into agent prompts so they don't hallucinate about repo state.

### 4. LLM Routing — LiteLLM / OpenRouter

LiteLLM and OpenRouter provide model/provider abstraction and routing. Model
selection stays config-driven and decoupled from orchestration and execution
roles.

## Responsibilities Matrix

| Component | Owns | Must Not Own |
|-----------|------|--------------|
| **Hermes (Supervisory Core)** | Job routing, supervisory orchestration, critique policy, learning policy, escalation/handoff decisions | Broad execution loops, heavy code/test/build operations, replacing Droid as execution engine |
| **Droid (Execution Engine)** | Implementation-heavy execution, shell/code operations, bounded local self-orchestration while executing delegated jobs | Global supervisory policy, long-horizon learning governance, replacing Hermes as control plane |
| **memory_heist (Context Engine)** | Repo truth, context discovery/plumbing, instruction/config/git/session context assembly | Execution orchestration policy, critique decision-making, execution ownership |
| **LiteLLM/OpenRouter (Model Routing)** | Provider abstraction, model access, configurable routing | Orchestration policy, execution ownership, critique ownership |

**Default routing rule:** if work may mutate code, invoke tools, or requires
non-trivial execution judgment, route it to Droid.

## Anti-Drift Guardrails (Separation of Duties)

1. **Hermes is not a monolith.** Hermes coordinates, critiques, and learns; it
   does not absorb all runtime behavior.
2. **Hermes is not a second execution engine.** Hermes may run only tiny,
   bounded, critic-native tasks directly.
3. **Orchestration refactors must not absorb execution.** Shifting control flow
   or framework choice must not move execution-heavy behavior into Hermes by
   default.
4. **Droid is not reduced to a dumb worker.** Droid retains bounded local
   self-orchestration authority during execution.
5. **Ambiguous execution defaults to Droid.** If ownership is unclear and task
   impact is execution-heavy, route to Droid first.
6. **No verdict-based role collapse.** Critique outcomes must not be used to
   justify shifting execution ownership away from Droid.

## How They Connect

```
User Prompt
    │
    ▼
┌─────────────────────────────────────────────┐
│  Hermes Supervisory Core                    │
│                                             │
│  ┌───────────────────────────────────────┐  │
│  │ route jobs / supervise / critique     │  │
│  └───────────────────────┬───────────────┘  │
│                          │                  │
│                          ▼                  │
│                 ┌──────────────────┐        │
│                 │ Droid CLI        │        │
│                 │ execute + local  │        │
│                 │ self-orchestration│       │
│                 └──────────────────┘        │
│                          │                  │
│                          ▼                  │
│                 ┌──────────────────┐        │
│                 │ Critique + learn │        │
│                 │ (Hermes)         │        │
│                 └──────────────────┘        │
│                                             │
│  ┌──────────────────────────────────────┐   │
│  │ memory_heist.py — Context Engine     │   │
│  │ (repo scan, git state, instructions, │   │
│  │  config, session memory)             │   │
│  └──────────────────────────────────────┘   │
│                                             │
│  ┌──────────────────────────────────────┐   │
│  │ LiteLLM / OpenRouter — LLM Routing   │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

## Architecture Target (North Star)

| Pillar | Target Owner | Target Role |
|--------|--------------|-------------|
| Supervisory Core | `src/hermes_feedback.py` (and Hermes supervisory wiring) | Supervisory orchestration + critique + learning |
| Execution Engine | `src/tools/droid_executor.py` | Execution-heavy implementation with bounded local self-orchestration |
| Context Engine | `src/memory_heist.py` | Repo truth and context plumbing |
| LLM Routing | `src/llm_client.py` | Model/provider abstraction and routing |

## Current Implementation State (Transitional)

| Area | Primary Module(s) | Current Status |
|------|--------------------|----------------|
| Supervisory orchestration | `src/hermes_feedback.py`, `main.py`, `src/swarm_agency.py` (context only) | **Hermes-led:** primary path uses profile selection, Bridge execution, and Hermes (`HermesReviewer`) review; `swarm_agency.py` provides shared `ProjectContext` render budgets for Architect / routing / critic prompts—**not** a separate orchestration engine |
| Execution engine | `src/tools/droid_executor.py` | Bridge v0 bounded backend implemented (`shell=False`, timeout, deterministic capture, capped output) |
| Bridge runtime/policy | `src/bridge/contracts.py`, `src/bridge/policy.py`, `src/bridge/runtime.py`, `src/registry/profiles.py`, `src/registry/backends.py`, `src/registry/droids.py` | Bridge v0 hardened: fail-closed policy gate with command-profile checks, env override restrictions, total-output cap enforcement, deterministic status mapping, mutation-aware refresh gating, and registry-backed profile selection seam with backend-registry executor resolution, plus structured run persistence to `.ham/runs/`; droid registry records for UI/API |
| Read API + run store | `src/api/server.py`, `src/persistence/run_store.py` | Thin FastAPI layer over `RunStore` (`.ham/runs/`): status, runs list/detail, profiles, droids; read-only Context Engine snapshot (`/api/context-engine`, `/api/projects/{id}/context-engine`) for dashboard wiring |
| Workspace UI | `frontend/` (Vite + React) | Extracted workspace; TypeScript types aligned with persisted run / bridge shapes |
| Context engine | `src/memory_heist.py` | Hardened + tested (Phase 1/3 guardrails complete) |
| LLM routing | `src/llm_client.py` | Working |
| Critique MVP | `src/hermes_feedback.py` | Implemented (`HermesReviewer.evaluate()`), conservative fallback, tested |

**Interpretation rule:** "Target" defines architecture direction; "Current"
reports implementation reality. Do not treat transitional scaffolding as
architecture contract.

### Registries

The shipped registry surface includes `IntentProfile`, `ProfileRegistry`, `Selector`, `KeywordSelector`, and `DEFAULT_PROFILE_REGISTRY` in `src/registry/profiles.py`, plus `DroidRecord`, `DroidRegistry`, and `DEFAULT_DROID_REGISTRY` in `src/registry/droids.py` (builder and reviewer droids; pure-data records per registry conventions). `IntentProfile` records are pure data with `id`, `version`, `argv`, and `metadata` fields. The selection seam is a `Protocol` with one method (`select(prompt) -> str`) and currently has one default implementation (`KeywordSelector`).

The shipped backend registry surface is `ExecutionBackend`, `LocalDroidBackend`, `BackendRecord`, `BackendRegistry`, `DEFAULT_BACKEND_ID`, and `DEFAULT_BACKEND_REGISTRY` in `src/registry/backends.py`. `BackendRecord` follows the same pure-data Pydantic convention as `IntentProfile` (`id`, `version`, `metadata`, no methods). Runtime backend resolution currently uses hardcoded `DEFAULT_BACKEND_ID` against a single registered backend; per-intent backend selection is deferred.

Completed runs are now persisted as structured JSON at `.ham/runs/<timestamp>-<run_id>.json`. Persisted records include `run_id`, `created_at`, `profile_id`, `profile_version`, `backend_id`, `backend_version`, `prompt_summary`, `bridge_result`, and `hermes_review`. `run_id` is canonical from `bridge_result.run_id` (never regenerated); the timestamp in the filename is metadata for sort/collision only. The stdout `RUNTIME_RESULT` envelope shape remains unchanged, and persistence is additive. `BackendRegistry.get_record()` is now the first public backend-record accessor.

**Tests**: full `pytest` suite including registry, bridge, main loop, droid registry, API/CORS, control-plane catalog, and persistence tests — **154 passed** regression/guardrail cases (`pytest.ini` sets `pythonpath = .`; GitHub Actions runs `pytest` + frontend `tsc`).

**Next milestone**: evolve **chat as control plane** (structured UI actions, safe settings mutations) on top of **`/api/cursor-skills`** + operator-skills injection in `POST /api/chat`; continue Bridge-profile hardening.

**Deferred:** FTS5 durable learning persistence, second orchestration harness,
architecture sprawl.

## Design Principles

1. **Agents don't freestyle** — every agent gets grounded context from
   memory_heist before it touches anything. No hallucinating about repo state.
2. **Separation of duties is enforced** — Hermes supervises and critiques;
   Droid executes and may self-orchestrate locally during execution.
3. **Learning compounds** — Hermes collects and applies learning signals over
   time; durable FTS5 persistence is a planned follow-up.
4. **Models are disposable** — swap providers, swap models, swap pricing.
   The architecture doesn't care which LLM is behind the API.
5. **Local-first** — no cloud dependencies for context, memory, or learning.
   Everything runs against the local filesystem and local DBs.
