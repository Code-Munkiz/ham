# Launching a Cursor Cloud Agent from Ham

This guide is for **operators** who want a **Cursor Cloud Agent** to work on a GitHub-backed repository while Ham handles **preview, commit gates, durable records**, and optional **managed mission** policy. Execution stays **upstream in Cursor’s environment**; Ham does not substitute for local Droid when you need mutations on your machine.

**Deeper context:** [`HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md) (two paths: digest-gated operator vs direct proxy), [`ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`](ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md) (shipped vs gaps), [`HAM_CHAT_CONTROL_PLANE.md`](HAM_CHAT_CONTROL_PLANE.md) (chat `operator` intents).

---

## Prerequisites

1. **Cursor Cloud API key** on the Ham API host (`CURSOR_API_KEY` or `POST /api/cursor/credentials`). See [`DEPLOY_CLOUD_RUN.md`](DEPLOY_CLOUD_RUN.md) § “Cursor Cloud API key”.
2. **Ham launch bearer** — `HAM_CURSOR_AGENT_LAUNCH_TOKEN` (env or Secret Manager on Cloud Run). This is **separate** from the Cursor key: it is Ham’s **commit** gate for `cursor_agent_launch`. See [`DEPLOY_CLOUD_RUN.md`](DEPLOY_CLOUD_RUN.md) § “Cloud Agent launch token”.
3. **Repository URL** Ham can resolve for the agent (operator `cursor_repository`, project metadata `cursor_cloud_repository`, or `HAM_CURSOR_DEFAULT_REPOSITORY` for preview flows — see control-plane doc above).

---

## Recommended path: chat operator (preview → confirm → launch)

1. Use **dashboard / Workspace chat** (or any client of `POST /api/chat` or `POST /api/chat/stream`) with structured **`operator`** payloads, not ad-hoc secrets in free text.
2. **Preview:** `operator.phase=cursor_agent_preview` with task text, model choice, and repository context per [`HAM_CHAT_CONTROL_PLANE.md`](HAM_CHAT_CONTROL_PLANE.md). Ham returns a **proposal digest** and **`cursor_base_revision`**; no agent is created yet.
3. **Launch:** send **`operator.phase=cursor_agent_launch`** with **`confirmed=true`**, fields that match the preview (digest, base revision, task prompt, `project_id` if you use managed defaults), and **`Authorization: Bearer <HAM_CURSOR_AGENT_LAUNCH_TOKEN>`** on the HTTP request to Ham.
4. After a successful launch, Ham records a **`ControlPlaneRun`** and append-only audit; with **`cursor_mission_handling: managed`**, a **`ManagedMission`** row may be created — see the roadmap doc.

If `HAM_CURSOR_AGENT_LAUNCH_TOKEN` is unset, Ham’s operator copy should note that **launches are rejected** until it is configured.

---

## Alternative: direct HTTP proxies (`/api/cursor/...`)

`POST /api/cursor/agents/launch` and related routes **proxy** Cursor’s API. They **do not** use the same digest + operator-bearer contract as `cursor_agent_launch`. Use them only when you accept that **distinct** policy surface (see **§3** and **“Distinct direct proxy surfaces”** in [`HARNESS_PROVIDER_CONTRACT.md`](HARNESS_PROVIDER_CONTRACT.md)).

---

## Writing the task the agent should run

Treat the **task prompt** (and any follow-up) like a normal Cursor Cloud Agent brief:

- State **repository / ref** expectations if not already implied by metadata.
- Name **scope** explicitly (e.g. “docs only”, “tests for module X”, “no API changes”).
- Point to **first-class docs** the agent should read (`VISION.md`, `AGENTS.md`, `SWARM.md`, relevant `docs/*.md`).
- For **managed** flows, optional **`project_id`** on launch snapshots **deploy approval mode** at create time only (not live-synced later) — see roadmap §1.

---

## Quick verification

- **`GET /api/cursor/credentials-status`** — Cursor API key usable.
- **`GET /api/status`** — API up.
- After launch: **`GET /api/control-plane-runs`** and, if managed: **`GET /api/cursor/managed/missions`** — see [`CONTROL_PLANE_RUN.md`](CONTROL_PLANE_RUN.md).

---

## Local development runbook

For installing Ham, env modes, and smoke tests in a fresh environment, see [`.cursor/skills/cloud-agent-starter/SKILL.md`](../.cursor/skills/cloud-agent-starter/SKILL.md).
