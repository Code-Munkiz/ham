---
name: ham-qa-prompt-gate
description: Review executor prompts for red flags, alignment issues, blockers, scope drift, and evidence gaps before any non-trivial execution.
---

# HAM QA Prompt Gate

Use this skill before non-trivial implementation/deploy/debug/refactor/test/migration/cleanup prompts, and whenever the user asks to review or rewrite a prompt for safety.

## Purpose

Act as a Senior QA Engineer and Security Auditor for prompts:

- review prompt risk and scope
- rewrite unsafe or vague prompts when fixable
- proceed only when no blocker remains
- stop when a blocker requires human decision

## Required output (before execution)

1. Prompt review
 - Red flags:
 - Alignment:
 - Blockers:
 - Scope drift:
 - Evidence gaps:
2. Decision
 - `PROCEED AS-WRITTEN` | `PROCEED WITH REWRITE` | `STOP-BLOCKED`
3. Rewritten executor prompt (only when rewrite is needed)
4. Execution plan (only approved scope)
5. Validation/reporting requirements

## Classification rules

- Red flag: risky but fixable; rewrite and proceed only if blocker-free.
- Alignment issue: conflicts with current repo lane/policy; rewrite to align.
- Blocker: unsafe or missing decision; stop and request minimum human decision.
- Scope drift: unrelated expansion; remove from rewritten prompt.
- Evidence gap: overclaim risk; add proof/reporting requirements.

## Hard blockers

Stop immediately (`STOP-BLOCKED`) for any of the following:

- use of `git add -A`
- unapproved `--set-env-vars`
- env-file redeploys
- instructions to disable diagnostics
- requests to print/expose secrets or sensitive internal network/runtime details
- claims that unit tests alone prove live signed-in acceptance
- missing Clerk session treated as PASS instead of `MANUAL SESSION REQUIRED`
- persistent `CLERK_SESSION_INVALID` treated as PASS instead of `AUTH SESSION BLOCKER`
- move to export ZIP/GitHub push before Builder iteration, preview lifecycle, and workspace cleanup are stable
- broad architecture cleanup mixed into focused bugfix scope
- destructive cleanup/delete/migration without explicit target, rollback, and verification path

## HAM guardrails (must be enforced)

- Missing Clerk session -> `MANUAL SESSION REQUIRED`, never PASS.
- Persistent `CLERK_SESSION_INVALID` after refresh/sign-in -> `AUTH SESSION BLOCKER`; report endpoint/status/error code only.
- Unit tests alone never prove live signed-in acceptance.
- Preview 502 must be classified as bounded or unbounded.
- No export ZIP/GitHub push before Builder iteration, preview lifecycle, and workspace cleanup are stable.

## Rewrite rules

When rewrite is needed:

- preserve user intent
- narrow scope to approved lane
- remove unsafe commands and vague "fix everything" wording
- add preflight commands, validation commands, reporting requirements, and stop conditions
- split optional follow-up work from immediate scope
- do not invent unverifiable acceptance claims

## Proceed rules

- If `PROCEED AS-WRITTEN`, execute as written.
- If `PROCEED WITH REWRITE`, execute only the rewritten prompt.
- If `STOP-BLOCKED`, do not execute; report the blocker and minimum needed decision.
- If user says `review-only`, do not execute.
- If user says `rewrite-only`, do not execute.

## Usage example

User prompt:
"Fix the preview issue, deploy, and then start GitHub export."

Expected gate result:

- Red flag: mixed bugfix + deploy + export scope
- Scope drift: export blocked until Builder lifecycle acceptance
- Decision: `PROCEED WITH REWRITE`
- Rewritten prompt: fix preview lifecycle only, run targeted validation, report evidence, no export
