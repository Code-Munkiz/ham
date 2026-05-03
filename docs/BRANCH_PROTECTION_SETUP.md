# Branch protection / ruleset setup (manual)

Phase B of the agent-readiness lift adds a branch protection plan **without**
toggling it on. This file documents the exact steps the repo admin should run
once PR2 is green on `main` for at least one full CI run.

Why deferred: enforcing required status checks before they exist on `main` =
broken CI. We wait until the new `python` job (with `pytest`, `large-file
guard`, ruff/mypy/coverage warning-only steps) and the new `secret scan / gitleaks`
workflow have a successful run on `main` so they can legitimately appear in the
required-status-checks list.

## Prerequisites

1. PR2 (`chore(repo): add CI lint/format/coverage warn-only + gitleaks`) is
   merged to `main`.
2. At least one push to `main` after the merge has succeeded for both
   workflows: `CI` (job names: `python`, `frontend`) and `Secret scan` (job
   name: `gitleaks`). Confirm with:
   ```bash
   gh run list --branch main --workflow ci.yml --limit 5 --json conclusion,name
   gh run list --branch main --workflow secret-scan.yml --limit 5 --json conclusion,name
   ```
3. You have admin access on `Code-Munkiz/ham`.

## Recommended: GitHub repository ruleset (modern)

Rulesets are GitHub's modern replacement for legacy branch protection. They
support bypass actors (preserving HAM's owner-local direct-`main` workflow)
and target `main` (and any future `release/*` branches) via patterns.

**UI path:** Repo → Settings → Rules → Rulesets → New branch ruleset.

**Recommended settings**

| Field | Value |
|---|---|
| Ruleset name | `main protection` |
| Enforcement status | `Active` |
| Bypass list | The owner GitHub account (so the AGENTS.md `owner-local canonical` direct-`main` workflow still works) and the `Code-Munkiz` org admin team |
| Target branches | `main` (and `master` if you keep the alias) |
| Restrict creations | off |
| Restrict updates | off (still allow normal pushes from bypass actors) |
| Restrict deletions | **on** |
| Require linear history | on (optional, prevents merge-commit clutter) |
| Require signed commits | off (HAM has agent commits without signing today) |
| Require pull request | **on** — Required approvals: `1`, Dismiss stale reviews on new commits: on, Require review from Code Owners: **on**, Require approval of the most recent reviewable push: on |
| Require status checks to pass | **on** — Strict (require branches to be up to date): on. Required checks (paste exact names): `python`, `frontend`, `gitleaks` |
| Block force pushes | **on** |
| Require code scanning results | off (Phase B does not enable GitHub Code Scanning; revisit in a later phase) |

**`gh` API equivalent (optional)**

```bash
gh api -X POST repos/Code-Munkiz/ham/rulesets \
  --input docs/examples/main-ruleset.json
```

(That JSON file is not committed; generate by exporting an existing ruleset
once it is in place.)

## Alternative: legacy branch protection

If your plan tier does not support rulesets, configure classic branch
protection on `main` with the same intent:

```bash
gh api -X PUT repos/Code-Munkiz/ham/branches/main/protection \
  -f required_status_checks.strict=true \
  -F required_status_checks.contexts='["python","frontend","gitleaks"]' \
  -f enforce_admins=false \
  -F required_pull_request_reviews.required_approving_review_count=1 \
  -F required_pull_request_reviews.require_code_owner_reviews=true \
  -F required_pull_request_reviews.dismiss_stale_reviews=true \
  -F restrictions= \
  -F allow_force_pushes=false \
  -F allow_deletions=false
```

`enforce_admins=false` is intentional: it preserves the owner-local
direct-`main` workflow described in `AGENTS.md`. **Do not** flip it to
`true` without the owner's explicit consent.

## Enable GitHub native secret scanning (free for public repos)

Independent of the ruleset:

```bash
# Enable secret scanning + push protection (replace ham with project name).
gh api -X PATCH repos/Code-Munkiz/ham \
  -F security_and_analysis.secret_scanning.status=enabled \
  -F security_and_analysis.secret_scanning_push_protection.status=enabled
```

This is in addition to the in-CI gitleaks workflow added by PR2.
GitHub native scanning catches commits **after** push; gitleaks-in-CI catches
them **before** merge. Both are cheap; run both.

## Validation checklist

After enabling:

- [ ] Open a throwaway PR with a trivial whitespace change. CI runs `python`,
      `frontend`, `gitleaks`. PR cannot merge until all three pass.
- [ ] Confirm CODEOWNERS approval is required on a file owned by
      `@abundy1 @Gio2050`.
- [ ] Confirm the owner can still push directly to `main` (bypass works).
- [ ] Confirm a force-push is rejected for non-bypass actors.

## Rollback

Rulesets and branch protection can be disabled or deleted entirely from the
same UI/API path with no data loss. Existing PRs remain merge-able; only the
gating logic goes away.

## Out of scope for this PR

- Strict mypy / ESLint blocking gates (Phase A.2 / Phase C).
- Required status check `coverage` (Phase B does coverage as warning-only).
- Required status check `secret-scan` (this is the workflow file name, not a
  job name; the **job** check name is `gitleaks`).
- DAST, code-scanning, supply-chain attestations (out of scope for the
  product-shape-fluid window).
