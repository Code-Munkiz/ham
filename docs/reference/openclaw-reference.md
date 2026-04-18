# OpenClaw — reference summary

> Reference summary for future HAM adapter/context work. **Not** a source of shipped HAM truth. OpenClaw evolves quickly; verify against current upstream docs when implementing.

## SOUL.md

- Convention: a **SOUL** document captures personality, values, boundaries, and interaction style in prose (often markdown).
- Sits alongside code and config so agents have a **stable “who”** independent of model swaps.
- HAM parallel: **persona / identity** layers in the six-concern product model—**not** a requirement to adopt `SOUL.md` as a filename.

## MEMORY.md / memory model

- Separate **ephemeral** (session) vs **durable** (notes, summaries, user-specific stores) memory is common.
- File-based memory docs (`MEMORY.md` or similar) sometimes hold long-lived facts the user wants retained.
- HAM today uses **session compaction** and **run JSON**; durable institutional memory remains a **gap** (see `GAPS.md`), not an OpenClaw parity target.

## Skills

- Skills packages describe **when** and **how** to invoke specialized behavior (prompts + tool hooks).
- Useful reference for future HAM **plugin** or **profile** packaging—format not assumed.

## Model / provider choices

- Typically environment-driven API keys and model IDs; multi-provider switching is a first-class idea.
- Aligns with HAM’s **LiteLLM/OpenRouter** approach at a high level.

## Gateway / channel / workspace

- **Gateway** — Central process that routes messages between users, models, and tools (often multi-channel: chat apps, CLI, webhooks).
- **Channel** — A single ingress (e.g. Discord vs terminal) with its own auth and formatting rules.
- **Workspace** — Often maps to a repo or sandbox where tools run.
- HAM direction: **control surface** and **shared workspace**—conceptual overlap, different implementation.

## MCP / tooling

- Heavy use of **Model Context Protocol** and tool servers for filesystem, browser, and integrations.
- HAM’s Bridge/Droid path is **policy-gated execution**; MCP patterns may inform **future tool adapters**, not current code.

## Multi-agent / routing

- Patterns include **router agents**, **topic queues**, and **per-channel personas**.
- Useful for imagining **Hermes routing** and **team** UX—no implication HAM copies OpenClaw’s router design.

## Local-first

- Many flows emphasize **local execution**, user-owned keys, and optional cloud relay.
- Resonates with HAM’s **CLI-first** and **local repo truth** via `memory_heist`.

## HAM stance

OpenClaw informs **tool leverage**, **channels**, and **soul/memory flavor**. HAM does **not** adopt OpenClaw’s file layout or runtime as its own.
