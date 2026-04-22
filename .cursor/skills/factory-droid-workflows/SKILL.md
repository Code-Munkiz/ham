---
name: factory-droid-workflows
description: How Ham previews and launches allowlisted Factory droid exec workflows from chat (readonly audit vs low-risk edit), runner assumptions, and hard security limits. Instructional only — policy lives in code.
---

# Factory Droid workflows (Ham chat)

## What this is

Ham can drive **two allowlisted** Factory **`droid exec`** workflows from the **server-side chat operator**, using **preview → confirm → launch**. This skill explains vocabulary and process for humans and agents. **It is not the policy source of truth** — see `src/ham/droid_workflows/registry.py` and `docs/FACTORY_DROID_CONTRACT.md`.

## Workflows (Phase 1)

| `workflow_id` | Tier | Mutates | Launch token |
|-----------------|------|---------|--------------|
| `readonly_repo_audit` | `readonly` | No | Not required |
| `safe_edit_low` | `low_edit` | Yes (`--auto low`) | **`HAM_DROID_EXEC_TOKEN`** bearer required |

## How to use from chat

1. **Preview** (natural language example):

   `preview factory droid readonly_repo_audit: focus on API security and tests`

   Include a registered project id in the message (e.g. `project.foo-bar`) or send chat with `project_id` set.

2. Read **`operator_result.pending_droid`**: `proposal_digest`, `base_revision`, `droid_user_prompt`, `mutates`, `summary_preview`.

3. **Launch** — send `operator` JSON with:

   - `phase`: `droid_launch`
   - `confirmed`: `true`
   - `project_id`, `droid_workflow_id`, `droid_user_prompt` (same as preview)
   - `droid_proposal_digest`, `droid_base_revision` from `pending_droid`
   - For **`safe_edit_low`**: `Authorization: Bearer <HAM_DROID_EXEC_TOKEN>`

Structured preview without NL: `phase: droid_preview` with `droid_workflow_id` + `droid_user_prompt`.

## Prerequisites

- **Runner host** has `droid` installed, Factory auth (e.g. `FACTORY_API_KEY`), and filesystem access to the **registered project root** the API uses.
- **Phase 1** assumes **co-location** (API runs `droid` locally) unless you deploy the documented **remote runner** HTTP seam (`HAM_DROID_RUNNER_URL`).
- Custom Droid names in a workflow must exist under **`.factory/droids/*.md`** on that repo; otherwise preview **blocks** (fail closed).

## Tier meanings

- **`readonly`:** no `--auto`; intended for audits and read-only analysis.
- **`low_edit`:** `droid exec --auto low` — tightly scoped doc/comment/typo class edits per registry template; not a general coding agent.

## What is explicitly not allowed

- **No arbitrary shell** from chat — only registry-built argv and templated prompts.
- **No** `--skip-permissions-unsafe` (forbidden in code).
- **No** `FACTORY_API_KEY` in the browser, chat prompts, or Ham logs.
- **No** mutating launch without **preview**, **confirm** (`confirmed=true`), and **bearer** where required.
- **No** launching on unknown `workflow_id`, bad digest, stale registry revision, or inaccessible project root.
- **No** Custom Droid authoring from chat in Phase 1.

## Where to read more

- Contract: `docs/FACTORY_DROID_CONTRACT.md`
- Control plane: `docs/HAM_CHAT_CONTROL_PLANE.md`
- Code: `src/ham/droid_workflows/`, `src/integrations/droid_runner_client.py`, `src/ham/chat_operator.py`
