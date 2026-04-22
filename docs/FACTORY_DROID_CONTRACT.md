# Factory Droid execution contract (HAM ↔ runner)

This document describes the **Phase 1** integration between Ham’s chat/API control plane and Factory **`droid exec`**. It is descriptive; **policy source of truth** is code under `src/ham/droid_workflows/` and `src/ham/chat_operator.py`.

## Roles

| Layer | Responsibility |
|-------|----------------|
| **HAM API** | Allowlisted `workflow_id`, preview (digest + registry revision), launch gating (`confirmed`, bearer for mutating runs), structured `operator_result`, audit append. |
| **Runner host** | `droid` on `PATH`, `FACTORY_API_KEY` (or equivalent Factory auth) in the process environment, read/write access to the **registered project root**. Ham **never** sends `FACTORY_API_KEY` to the browser or embeds it in prompts. |
| **Client** | Natural language or structured `operator` payloads; **no raw shell**; for mutating workflows, `Authorization: Bearer` matching **`HAM_DROID_EXEC_TOKEN`** on launch only. |

## Execution modes

1. **Local (default)** — The API process invokes `droid` via `src/tools/droid_executor.py` (`subprocess`, `shell=False`). Only valid when the API is **co-located** with the repo and Factory credentials (e.g. dev machine or single VM running both).

2. **Remote seam (optional)** — Set **`HAM_DROID_RUNNER_URL`** (base URL) and **`HAM_DROID_RUNNER_TOKEN`**. The API POSTs JSON to `{base}/v1/ham/droid-exec` with `Authorization: Bearer <HAM_DROID_RUNNER_TOKEN>`.  
   **Body (minimum):** `argv`, `cwd`, `timeout_sec`. **Optional correlation fields** (sent by Ham when using remote mode): `workflow_id`, `audit_id` (Ham-generated id for this launch, matches project audit row), `project_id`, `proposal_digest`; `session_id` reserved for future chat wiring.  
   **Shipped runner:** `src/ham/droid_runner/service.py` enforces bearer auth, **optional cwd allowlist** (`HAM_DROID_RUNNER_ALLOWED_ROOTS`), argv validation, and **runner-local JSONL audit** (`HAM_DROID_RUNNER_AUDIT_FILE`). Set **`HAM_DROID_RUNNER_SERVICE_TOKEN`** on the runner to the same secret as **`HAM_DROID_RUNNER_TOKEN`** on Ham. See **`docs/HAM_DROID_RUNNER_SERVICE.md`**.

Optional: **`HAM_DROID_RUNNER_ID`** — opaque label included in previews and audit rows (defaults: `local` or `remote`).

## Workflow registry

- **Revision:** `REGISTRY_REVISION` in `src/ham/droid_workflows/registry.py` (bump when definitions change).
- **Workflows:** `readonly_repo_audit`, `safe_edit_low` (see registry for `tier`, `mutates`, `requires_launch_token`, templates).

Custom Factory Droids: a workflow may set `custom_droid_name`; preview **fails closed** if `.factory/droids/<slug>.md` is missing on disk under the project root.

## Chat / API flow

1. **Preview** — `operator.phase=droid_preview` with `project_id`, `droid_workflow_id`, `droid_user_prompt`, or NL: `preview factory droid <workflow_id>: <focus>`.  
   Response includes **`pending_droid`**: `proposal_digest`, `base_revision` (registry revision), `summary_preview`, `mutates`, etc.

2. **Launch** — `operator.phase=droid_launch` with `confirmed=true`, same `project_id`, `droid_workflow_id`, `droid_user_prompt`, `droid_proposal_digest`, `droid_base_revision`.  
   - **`safe_edit_low`:** requires **`HAM_DROID_EXEC_TOKEN`** bearer.  
   - **`readonly_repo_audit`:** no droid exec token; still requires **`confirmed=true`** and matching digest.

3. **Verify** — `verify_launch_against_preview()` recomputes the digest; mismatch or stale `droid_base_revision` blocks launch (no pretend success).

## Command construction

- argv is built only from the registry: `droid exec --cwd <resolved> --output-format json [--auto low] … <prompt>`.
- **`--skip-permissions-unsafe`** is forbidden in code paths.
- User text is only interpolated into the allowlisted **`prompt_template`** as `{user_focus}` (sanitized); there is no arbitrary argv from chat.

## Audit and results

Each executed launch appends one JSON line to **`<project_root>/.ham/_audit/droid_exec.jsonl`** with at least: `workflow_id`, `runner_id`, `cwd`, `exit_code`, `duration_ms`, `summary`, capped stdout/stderr, `parsed_json` when parseable, `audit_id`, `project_id` / `proposal_digest` when present, optional `session_id`, `ok`, `timed_out`.  
Failures (non-zero exit, timeout, runner errors) are recorded with **real** exit codes / stderr where available.

**Remote runner:** the same Ham audit file is still written by the API after it receives the runner response. The runner host additionally appends **append-only JSONL** to **`HAM_DROID_RUNNER_AUDIT_FILE`** (see runner doc): no secrets, no argv/prompt, structured **blocked** vs **executed** outcomes and correlation ids (`runner_request_id`, optional `ham_audit_id`).

## Environment summary

| Variable | Purpose |
|----------|---------|
| `HAM_DROID_EXEC_TOKEN` | Bearer for **mutating** `droid_launch` (`safe_edit_low`). Server-only. |
| `HAM_DROID_RUNNER_URL` | Optional remote runner base URL. |
| `HAM_DROID_RUNNER_TOKEN` | Bearer for Ham → runner HTTP (not Factory). |
| `HAM_DROID_RUNNER_ID` | Optional audit label. |
| `HAM_DROID_RUNNER_ALLOWED_ROOTS` | **Runner host only:** comma-separated absolute roots; resolved cwd must be contained under one (production). |
| `HAM_DROID_RUNNER_AUDIT_FILE` | **Runner host only:** JSONL audit path (default `~/.ham/droid_runner_audit.jsonl`). |

`FACTORY_API_KEY` belongs **only** on the runner host environment, not in Ham frontend env files or chat payloads.
