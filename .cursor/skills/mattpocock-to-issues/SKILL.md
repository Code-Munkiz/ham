---
name: to-issues
description: Convert accepted plans/specs into independent vertical-slice GitHub issues with explicit dependencies.
---

# To Issues (HAM Local)

Break approved work into thin vertical slices (not horizontal layer splits).

## Workflow

1. Read `docs/agents/issue-tracker.md` and `docs/agents/triage-labels.md`.
2. Draft slice list with type (`AFK` or `HITL`) and dependencies.
3. Confirm granularity and order with the user.
4. Publish GitHub issues in dependency order.
5. Apply configured triage labels only when requested/appropriate.

Apply `docs/agents/ham-safety.md` constraints in any acceptance criteria touching auth, preview, or validation.

## Attribution

Adapted from [`mattpocock/skills`](https://github.com/mattpocock/skills), `skills/engineering/to-issues/SKILL.md` (MIT License).
