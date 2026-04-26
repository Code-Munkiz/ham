# Workspace Jobs & Tasks (HAM bridge)

**Row IDs (IA coverage):** JOBS-001…JOBS-006, TASKS-001…TASKS-008 (Jobs/Tasks namespaced surface under `/workspace/*` with HAM APIs).

## Storage (local / dev)

Under `HAM_WORKSPACE_ROOT` (or legacy `HAM_WORKSPACE_FILES_ROOT`, or repo `.ham_workspace_sandbox`):

| Data | Path |
|------|------|
| Jobs | `.ham/workspace_state/jobs.json` |
| Tasks | `.ham/workspace_state/tasks.json` |

JSON documents are `{"jobs": { id: object }}` and `{"tasks": { id: object }}` with thread-locked read/write. No production DB; replace with persistent store in a follow-up if needed.

## API

- `GET/POST /api/workspace/jobs`, `GET/PATCH/DELETE /api/workspace/jobs/{id}`, `POST …/run|pause|resume`, query `?q=` on list
- `GET /api/workspace/tasks/summary` — `total`, `inProgress`, `overdue`, `done`, `donePercent`
- `GET/POST /api/workspace/tasks`, `GET/PATCH/DELETE /api/workspace/tasks/{id}` — `includeDone`, `q`, `status` on list

## Frontend

- `workspaceJobsAdapter` / `workspaceTasksAdapter` — same-origin `fetch` to the above (Vite dev proxy to FastAPI)
- `WorkspaceJobsScreen` / `WorkspaceTasksScreen` — no upstream Hermes, OpenAI, or `api/send-stream`

## Upstream pattern references (design only)

External Hermes workspace references used for UX alignment (not runtime coupling): `jobs-screen`, `tasks-screen` route shells as described in the workspace lift plan.
