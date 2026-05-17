---
name: grill-with-docs
description: Grilling session for plan alignment against domain language and ADRs, with inline doc updates when decisions are finalized.
---

# Grill With Docs (HAM Local)

Interview the user one question at a time to clarify scope and trade-offs.

## Workflow

1. Read `docs/agents/ham-safety.md` first and apply it throughout.
2. Explore relevant code paths before asking questions that code can answer.
3. Use domain language from `CONTEXT.md` if present.
4. Use ADRs in `docs/adr/` if present.
5. Update docs only when decisions are final:
 - `CONTEXT.md` for glossary/language
 - `docs/adr/` for hard-to-reverse trade-offs

Create docs lazily. If `CONTEXT.md` or `docs/adr/` is absent, create only when needed by a confirmed decision.

## Attribution

Adapted from [`mattpocock/skills`](https://github.com/mattpocock/skills), `skills/engineering/grill-with-docs/SKILL.md` (MIT License).
