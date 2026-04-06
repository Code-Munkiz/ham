# Ham — Vision & Architecture

## What Ham Is

Ham is an open-source, multi-agent autonomous developer swarm that executes
the full Software Development Life Cycle (SDLC). It is not a chatbot wrapper.
It is an opinionated assembly line: plan, build, review, learn, repeat.

## The Five Pillars

### 1. The Orchestrator — CrewAI

CrewAI manages the workflow graph. It routes tasks between agents, enforces
sequencing (sequential or hierarchical process), and owns the agent lifecycle.
Every agent in the swarm is a CrewAI `Agent`; every unit of work is a CrewAI
`Task`. CrewAI is the spine — nothing moves without it.

### 2. The Muscle — Factory Droid CLI

Factory Droid CLI is the execution engine, wrapped as a CrewAI `@tool` so
agents can trigger massive parallel shell execution. When the Commander agent
needs to scaffold 40 files, run a test matrix, or batch-apply refactors, it
delegates to Droid via `subprocess`. Droid is pure throughput — it does not
think, it executes.

### 3. The Critic / Learner — Hermes

The **Critic** pillar (`src/hermes_feedback.py`) runs a code review pass after
execution-oriented work. Today it uses a **minimal LLM-backed** reviewer with a
stable output schema and conservative fallback when critique cannot complete
confidently. **Durable learning** (e.g. FTS5-backed persistence) is part of the
long-term vision but is **not implemented yet** — see `GAPS.md`.

### 4. The Context Engine — memory_heist.py

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

### 5. LLM Routing — LiteLLM / OpenRouter

LiteLLM provides the model-agnostic API layer. OpenRouter provides the BYOK
(bring your own key) gateway. Together they let Ham hot-swap models on the
fly — use a fast model for planning, a strong model for code generation, a
cheap model for summarization. Model selection is config-driven, not hardcoded.

## How They Connect

```
User Prompt
    │
    ▼
┌─────────────────────────────────────────────┐
│  CrewAI Orchestrator                        │
│                                             │
│  ┌───────────┐  ┌───────────┐  ┌─────────┐ │
│  │ Architect │→ │ Commander │→ │ Hermes  │ │
│  │  (plan)   │  │ (execute) │  │ (review)│ │
│  └───────────┘  └─────┬─────┘  └────┬────┘ │
│                       │              │      │
│                       ▼              ▼      │
│               ┌──────────────┐  ┌────────┐  │
│               │ Droid CLI    │  │ FTS5   │  │
│               │ (subprocess) │  │ (learn)│  │
│               └──────────────┘  └────────┘  │
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

## Current State

The skeleton is assembled. Each pillar has a module:

| Pillar         | Module                     | Status     |
|----------------|----------------------------|------------|
| Orchestrator   | `src/swarm_agency.py`      | Wired — single `ProjectContext.discover()`, per-agent render budgets |
| Muscle         | `src/tools/droid_executor.py` | Scaffold |
| Critic         | `src/hermes_feedback.py`   | MVP — LLM-backed `HermesReviewer.evaluate()`, stable schema, conservative fallback; FTS5 / durable learning **deferred** |
| Context Engine | `src/memory_heist.py`      | Hardened + Phase 1 — caps, marker coupling, instruction scanning, tool-output pruning, config-driven session compaction; 18 tests in `tests/test_memory_heist.py` |
| LLM Routing    | `src/llm_client.py`        | Working    |

**Tests**: `tests/test_memory_heist.py` + `tests/test_hermes_feedback.py` — **25** regression/guardrail cases (run both files with pytest).

**Next milestone**: wire Droid CLI end-to-end, add context refresh after Droid
mutations, expand task graph beyond single kickoff task, validate a full swarm
run on a real prompt. **Deferred:** FTS5 critic persistence, second orchestration
harness, orchestration redesign.

## Design Principles

1. **Agents don't freestyle** — every agent gets grounded context from
   memory_heist before it touches anything. No hallucinating about repo state.
2. **Execution is dumb, review is smart** — Droid executes fast and blind;
   Hermes catches mistakes after the fact. Speed + quality without bottleneck.
3. **Learning compounds** — Hermes persists lessons in FTS5. The swarm gets
   better at *this specific project* over time.
4. **Models are disposable** — swap providers, swap models, swap pricing.
   The architecture doesn't care which LLM is behind the API.
5. **Local-first** — no cloud dependencies for context, memory, or learning.
   Everything runs against the local filesystem and local DBs.
