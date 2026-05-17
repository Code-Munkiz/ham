---
name: tdd
description: Red-green-refactor loop using vertical slices and behavior-focused tests through public interfaces.
---

# TDD (HAM Local)

## Rules

- Test behavior through public interfaces, not implementation details.
- Use vertical slices (one failing test -> minimal fix -> pass), not horizontal batching.
- Refactor only after green.
- Keep scope focused; avoid speculative additions.

## Process

1. Confirm target interface and highest-value behaviors.
2. Write one failing test.
3. Implement minimal code to pass.
4. Repeat for next behavior.
5. Refactor safely with tests green.

Read `docs/agents/ham-safety.md` first and preserve its release/validation constraints.

## Attribution

Adapted from [`mattpocock/skills`](https://github.com/mattpocock/skills), `skills/engineering/tdd/SKILL.md` (MIT License).
