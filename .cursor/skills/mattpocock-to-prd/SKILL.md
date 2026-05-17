---
name: to-prd
description: Turn current conversation context into a PRD-style implementation issue with explicit module and testing decisions.
---

# To PRD (HAM Local)

Synthesize current context into a PRD without re-interviewing by default.

## Workflow

1. Review current codebase and domain docs if present.
2. Draft problem, solution, user stories, implementation decisions, testing decisions, and out-of-scope.
3. Validate module assumptions with user when uncertainty is material.
4. Publish to GitHub issue tracker per `docs/agents/issue-tracker.md`.

Respect `docs/agents/ham-safety.md` when describing acceptance and validation.

## Attribution

Adapted from [`mattpocock/skills`](https://github.com/mattpocock/skills), `skills/engineering/to-prd/SKILL.md` (MIT License).
