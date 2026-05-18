# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues on `Code-Munkiz/ham`. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v` — `gh` does this automatically when run inside a clone. If `gh` auth is unavailable, report the limitation and stop — do not guess.

## Label taxonomy

This repo uses a prefixed taxonomy managed by `scripts/sync_github_labels.sh` and documented in `AGENTS.md § Issue label taxonomy`. Apply labels from that taxonomy plus the canonical triage roles in [triage-labels.md](triage-labels.md).

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.
