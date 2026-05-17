---
name: setup-matt-pocock-skills
description: Repo-local setup for Matt Pocock engineering skills in HAM. Configures issue tracker, triage labels, and domain doc locations without touching runtime or deploy settings.
disable-model-invocation: true
---

# Setup Matt Pocock Skills (HAM Local)

This repository is preconfigured for local skill workflow docs:

- Issue tracker: GitHub
- Domain docs: `CONTEXT.md` (if/when needed) and `docs/adr/`
- Skill wiring docs: `docs/agents/`

## Steps

1. Read:
 - `docs/agents/issue-tracker.md`
 - `docs/agents/triage-labels.md`
 - `docs/agents/domain.md`
 - `docs/agents/ham-safety.md`
2. If any of those files are missing, recreate them using current HAM policy.
3. Do not modify runtime code, deploy config, env vars, hooks, or package behavior as part of this setup.

## Attribution

Adapted from [`mattpocock/skills`](https://github.com/mattpocock/skills), `skills/engineering/setup-matt-pocock-skills/SKILL.md` (MIT License).
