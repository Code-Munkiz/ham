# Launching a Cursor Cloud Agent from Ham

This page is a **short operator runbook** for starting a **Cursor Cloud Agent** (remote execution on Cursor’s infrastructure) via Ham. Deep product state and gaps live in [`ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md); harness behavior and the two launch surfaces are in [`HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md).

---

## Prerequisites

1. **Cursor API key** — Ham must be able to call `https://api.cursor.com` as your team. Configure one of:
   - Environment: `CURSOR_API_KEY` (see [`.env.example`](../.env.example))
   - Or `POST /api/cursor/credentials` so the API persists the key server-side (then `GET /api/cursor/credentials-status` to verify)

2. **Protected routes** — `/api/cursor/*` uses the same Clerk gate as other dashboard APIs. When **`HAM_CLERK_REQUIRE_AUTH`** or **`HAM_CLERK_ENFORCE_EMAIL_RESTRICTIONS`** is on, send **`Authorization: Bearer`** with your **Clerk session JWT** (see [`HAM_CHAT_CONTROL_PLANE.md`](HAM_CHAT_CONTROL_PLANE.md) § Clerk). Use **`X-Ham-Operator-Authorization: Bearer …`** for Ham operator secrets (launch token, settings, droid) so they are not confused with the session header.

3. **Optional: managed missions** — To record a **managed** mission row and deploy-approval snapshot, pass **`mission_handling": "managed"`** and, if you use the project registry, **`project_id`** on launch. See the roadmap table for what is shipped vs partial.

---

## Path A — Direct HTTP launch (CI, scripts, curl)

Ham proxies **`POST https://api.cursor.com/v0/agents`**:

**`POST /api/cursor/agents/launch`**

Body (Ham shape; Ham-only fields are **not** forwarded to Cursor):

| Field | Required | Sent to Cursor |
|-------|----------|----------------|
| `prompt_text` | yes | `prompt.text` |
| `repository` | yes | `source.repository` (GitHub URL) |
| `ref` | no | `source.ref` (branch, tag, or commit) |
| `model` | no (default `"default"`) | `model` |
| `auto_create_pr` | no | `target.autoCreatePr` |
| `branch_name` | no | `target.branchName` |
| `mission_handling` | no | **Ham only** — `"direct"` / `"managed"` / omit |
| `uplink_id` | no | **Ham only** |
| `project_id` | no | **Ham only** — links registry defaults for managed missions |

Example (replace host, tokens, and repo):

```bash
curl -sS -X POST "https://YOUR_HAM_HOST/api/cursor/agents/launch" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_CLERK_SESSION_JWT_IF_REQUIRED" \
  -d '{
    "prompt_text": "Update docs for Cloud Agent launch; keep diffs small.",
    "repository": "https://github.com/your-org/your-repo",
    "ref": "main",
    "model": "default",
    "mission_handling": "managed",
    "project_id": "optional-registered-project-id"
  }'
```

Poll status with **`GET /api/cursor/agents/{agent_id}`** (same Cursor key on the server). OpenAPI: **`/docs`** on your Ham API.

---

## Path B — Dashboard chat operator (preview + digest + commit)

Hermes Workspace / **`POST /api/chat`** (and stream) can run the **chat operator** intents **`cursor_agent_preview`** then **`cursor_agent_launch`**. That path verifies a **proposal digest** and requires a **separate** Ham operator bearer **`HAM_CURSOR_AGENT_LAUNCH_TOKEN`** (not the Cursor API key). See [`HAM_CHAT_CONTROL_PLANE.md`](HAM_CHAT_CONTROL_PLANE.md) § operational chat and [`DEPLOY_CLOUD_RUN.md`](DEPLOY_CLOUD_RUN.md) § **Cloud Agent launch token** for Cloud Run.

---

## Cloud Run checklist

- Mount **`CURSOR_API_KEY`** and **`HAM_CURSOR_AGENT_LAUNCH_TOKEN`** from Secret Manager (`--set-secrets`); do not commit keys. Step-by-step: [`DEPLOY_CLOUD_RUN.md`](DEPLOY_CLOUD_RUN.md) (Cursor key + launch token sections) and [`DEPLOY_HANDOFF.md`](DEPLOY_HANDOFF.md).

---

## Related docs

| Topic | Document |
|--------|----------|
| Shipped vs partial / roadmap | [`ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) |
| Provider contract (two paths) | [`HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md) |
| Chat operator phases + Clerk | [`HAM_CHAT_CONTROL_PLANE.md`](HAM_CHAT_CONTROL_PLANE.md) |
| Control plane run records | [`CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md) |
