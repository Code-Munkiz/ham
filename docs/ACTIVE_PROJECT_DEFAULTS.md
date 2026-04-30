# Active project and project defaults

This note clarifies two related ideas that show up in **Hermes Workspace chat**, **settings**, and **managed Cloud Agent missions**: which project is *active* for the UI, and which *defaults* live on the project record.

---

## Active project (workspace UI)

In the Ham dashboard / Hermes Workspace, **“active project”** means the **registered Ham project id** (`project.*`) bound to the **same workspace root** the API reports for context and memory.

1. The UI loads the context-engine working directory (same notion as `GET /api/context-engine` — the API’s `cwd` for this session).
2. It resolves a project id with **find-or-register**: list projects from `GET /api/projects`, match `ProjectRecord.root` to that `cwd` (trailing slashes normalized), or **`POST /api/projects`** with that root if none exists yet.

Implementation reference: `ensureProjectIdForWorkspaceRoot` in `frontend/src/lib/ham/api.ts` (used by workspace chat and unified settings).

When a `project_id` is set, chat requests can include it (e.g. `POST /api/chat` body) so server-side features that need a registry project — **Cloud Agent preview/launch**, capability library, agent builder, project settings — receive the correct scope. If resolution fails, `project_id` may be omitted; operator flows that require a project then respond with errors such as *“No active project is selected for this workspace chat.”* (`src/ham/chat_operator.py`).

Deep links may also carry `project_id` in the query string; the app preserves it when navigating (`frontend/src/App.tsx`).

---

## Project defaults (registry metadata)

Beyond the id and `root`, each project has **`metadata`**: a shallow key/value bag merged via **`PATCH /api/projects/{project_id}`** (`src/api/server.py`).

### Deploy approval default (`default_deploy_approval_mode`)

For **managed** Cloud Agent missions, the server snapshots deploy-approval behavior **once at mission create** from the bound project’s metadata key **`default_deploy_approval_mode`**, but **only if** launch included a valid **`project_id`**. Allowed values: **`off`**, **`audit`**, **`soft`**, **`hard`**. Missing or invalid values are treated as **`off`**. Changing the project default later does **not** retroactively change existing mission rows.

- Policy resolution: `mission_deploy_approval_mode_from_project_metadata` in `src/ham/managed_deploy_approval_policy.py`
- Create-time snapshot: `resolve_mission_deploy_approval_mode_at_managed_create` in `src/ham/managed_mission_wiring.py`

UI labels for the same key live in `frontend/src/lib/ham/projectDeployPolicy.ts`.

---

## Related docs

- `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md` — shipped behavior, limitations, and roadmap for managed missions vs control-plane runs
- `AGENTS.md` — API surface for projects, chat, and capabilities
