# Launch a Cursor Cloud Agent from Ham

Ham does **not** replace Cursor’s Cloud Agent product. It **proxies** launches to Cursor’s API (`api.cursor.com`), keeps **durable records** (`ControlPlaneRun`, optional `ManagedMission`), and enforces Ham **policy** (preview digest, operator bearer, deploy hooks where configured). Execution stays **upstream** in Cursor’s environment.

**Related:** [`docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) (shipped vs gaps), [`docs/HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md) (honest harness model), [`docs/HAM_CHAT_CONTROL_PLANE.md`](HAM_CHAT_CONTROL_PLANE.md) (chat operator intents).

---

## Prerequisites

| Requirement | Purpose |
|-------------|---------|
| **`CURSOR_API_KEY`** | Server-side Cursor API auth (env or `POST /api/cursor/credentials`). Verify with `GET /api/cursor/credentials-status`. |
| **`HAM_CURSOR_AGENT_LAUNCH_TOKEN`** | Ham **operator** secret: required for **committed** launches from chat (`cursor_agent_launch`) so the browser cannot launch with only the Cursor key. For **`POST /api/cursor/agents/launch`**, policy may differ by deployment; set the token wherever launches must be gated. |

On **Cloud Run**, mount both from **Secret Manager** — see [`docs/DEPLOY_CLOUD_RUN.md`](DEPLOY_CLOUD_RUN.md) (§ Cursor Cloud API key, § Cloud Agent launch token) and [`docs/DEPLOY_HANDOFF.md`](DEPLOY_HANDOFF.md).

---

## Ways to launch

### 1) Direct API (CI, scripts, integrations)

**`POST /api/cursor/agents/launch`** — Ham forwards the body to Cursor’s agent create API after applying Ham-only side effects (managed mission record, etc.); Ham-only fields such as `mission_handling`, `uplink_id`, and `project_id` are **not** sent to Cursor.

- See in-repo references: `src/api/cursor_settings.py` (operator copy), `frontend/src/lib/ham/api.ts` (`launchCursorAgent`).

### 2) Dashboard chat (preview → confirm → launch)

Structured **`operator`** on **`POST /api/chat`** or **`POST /api/chat/stream`**:

1. **`cursor_agent_preview`** — Computes `cursor_proposal_digest` and `cursor_base_revision` without calling Cursor launch. Repository resolution order is documented in [`docs/HAM_CHAT_CONTROL_PLANE.md`](HAM_CHAT_CONTROL_PLANE.md).
2. **`cursor_agent_launch`** — Requires `confirmed=true`, matching digest and base revision, and **`Authorization: Bearer`** equal to **`HAM_CURSOR_AGENT_LAUNCH_TOKEN`**. On success, Ham calls Cursor via [`src/integrations/cursor_cloud_client.py`](../src/integrations/cursor_cloud_client.py) and writes audit / control-plane records as described in the harness contract.

If **`HAM_CURSOR_AGENT_LAUNCH_TOKEN`** is unset, the chat operator surfaces a note that launches are rejected until it is configured.

### 3) Hermes Workspace / managed wording

Managed missions use the **same** launch path with optional `project_id` for deploy-approval snapshot and registry defaults. UI for dedicated War Room panels was removed in Batch 2A; APIs remain. See [`docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) § “What works today.”

---

## After launch

- **Poll / status:** `GET /api/cursor/agents/{id}` (and related routes) proxy Cursor; Ham may update `ManagedMission` / control-plane rows on observe.
- **Read-only list:** `GET /api/control-plane-runs` — factual launch history, not a mission queue ([`docs/CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md)).

---

## Local development quick check

With API running and keys set:

```bash
curl -sS http://127.0.0.1:8000/api/cursor/credentials-status
```

For full local runbook (install, chat modes, tests), see [`.cursor/skills/cloud-agent-starter/SKILL.md`](../.cursor/skills/cloud-agent-starter/SKILL.md).
