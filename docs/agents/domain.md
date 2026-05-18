# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Layout: single-context

```
/
├── CONTEXT.md           ← created lazily by /grill-with-docs
├── docs/adr/            ← ADRs for hard-to-reverse decisions
└── src/
```

This repo uses a single-context layout. There is no `CONTEXT-MAP.md` and no per-area `CONTEXT.md` files.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root if it exists.
- **`docs/adr/`** — read ADRs that touch the area you're about to work in.

If any of these don't exist yet, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The producer skill `/grill-with-docs` creates them lazily when terms or decisions actually get resolved during a grilling session.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal — either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/grill-with-docs`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders) — but worth reopening because…_

## Relationship to VISION.md and other root docs

`CONTEXT.md` (when created) is a **glossary of domain terms**. It does **not** replace:

- `VISION.md` — pillars, boundaries, component connections
- `AGENTS.md` — implementation map, git workflow, CI guardrails
- `SWARM.md` — coding instructions loaded by `memory_heist`
- `PRODUCT_DIRECTION.md` — product lens

If a term lives in `CONTEXT.md`, prefer the `CONTEXT.md` definition. If it lives in `VISION.md` and is not yet promoted to `CONTEXT.md`, the `VISION.md` usage is authoritative.
