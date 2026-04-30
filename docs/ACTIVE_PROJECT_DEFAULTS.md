# Active project and project defaults

This note explains how **which project is active** relates to **per-project defaults** stored on the HAM project registry.

## Active project (workspace / chat)

The **active project** is whichever project the client sends as `project_id` on API calls (for example `POST /api/chat` and `POST /api/chat/stream` in `src/api/chat.py`). That id selects the project’s **root on disk** for repo-scoped behavior (browser policy, settings paths, context resolution).

There is **no** server-side “global active project” beyond what each request supplies. If the UI does not send a `project_id`, flows that need a bound repo may refuse or ask the operator to pick a project first (see operator messaging in `src/ham/chat_operator.py`).

## Defaults live on `ProjectRecord.metadata`

Registered projects live in the file-backed **`ProjectStore`** (`~/.ham/projects.json`; see `src/persistence/project_store.py`). Arbitrary **metadata** is merged with `PATCH /api/projects/{project_id}` (`src/api/server.py`). The following keys are **conventions** used by HAM today; others may be added over time.

| Metadata key | Purpose |
|--------------|---------|
| `default_deploy_approval_mode` | One of `off`, `audit`, `soft`, `hard`. Validated on patch. Drives **managed mission** deploy-approval **only at create time** when launch includes that `project_id` (see `src/ham/managed_deploy_approval_policy.py`, `src/ham/managed_mission_wiring.py`). Changing the project default **does not** retroactively change existing mission rows. |
| `cursor_cloud_ref`, `cursor_ref`, `default_branch`, `branch`, `git_branch` (first non-empty wins) | Default **git ref** for Cursor Cloud Agent style launches when the request does not specify a ref explicitly (`src/ham/chat_operator.py`, `_project_default_cursor_ref`). |

Missing or invalid values fall back to safe defaults (for example unknown deploy mode → `off`).

## Related docs

- `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md` — managed missions, deploy snapshot semantics, optional `project_id` on launch.
- `docs/HAM_CHAT_CONTROL_PLANE.md` — chat API and operator control plane.
