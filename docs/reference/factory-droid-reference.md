# Factory AI / Droid — reference summary

> Reference summary for future HAM adapter/context work. **Not** a source of shipped HAM truth. Factory/Droid products change frequently; verify against current vendor docs when implementing.

## Droids and specialists

- **Droid** — Cursor’s autonomous coding agent abstraction: a packaged worker that can plan, edit, run commands, and report back within policy.
- **Specialist / sub-agent patterns** — Work is often split by **role** (e.g. review vs implement) or **scope** (e.g. single feature, single directory). Useful mental model for HAM “teams” and mission-scoped workers even if HAM uses different nouns.

## Model choice

- Model selection is typically **per session or per task**, with vendor-managed routing in hosted flows.
- For HAM, parallels map to **LiteLLM/OpenRouter** config and per-run intent—not to a mandatory Factory model string.

## Reasoning effort / autonomy

- UIs often expose **how hard the agent thinks** (depth of planning) vs **how far it may go autonomously** (files touched, commands run).
- Maps conceptually to HAM’s **bounded execution**, **Bridge policy**, and **Hermes review**—not to a single “autonomy slider” in code today.

## Skills

- **Skills** (or skill packs) bundle prompts, tools, and conventions for a vertical task (e.g. migrations, tests, security review).
- Adapter thinking: HAM **intent profiles**, **registry records**, or future **plugin manifests** might align with “skill” packaging without copying Factory’s format.

## Allowlist / denylist behavior

- Strong emphasis on **what commands/tools are allowed**, **path scopes**, and **network** on/off.
- Aligns with HAM’s **Bridge policy** and **ExecutionIntent** scope/limit concepts—useful reference for future policy UX, not a spec match.

## AGENTS.md / orchestration

- Repos often use **`AGENTS.md`** (and similar) to steer agent behavior project-wide.
- HAM already loads instruction files via the Context Engine (`memory_heist` / `SWARM.md` / `AGENTS.md`); Factory’s conventions are **analogous**, not identical.

## Orchestration concepts

- **Handoff** between human and agent, **checkpointing** work, and **session transcripts** are common product patterns.
- HAM’s direction is **run records** under `.ham/runs/` and **Hermes review**—different implementation, similar “audit trail” goal.

## HAM stance

Factory/Droid informs **workforce and mission** language in product direction. HAM remains **HAM-native**; no requirement to embed Factory config or CLI semantics.
