# Conductor — mission control polish (docs note)

## What Conductor is

In the Hermes Workspace, **Conductor** (`/workspace/conductor`) is the **mission control** surface: create and manage **workspace missions** backed by the Ham API at `GET/POST /api/workspace/conductor/*`. State lives under the configured workspace root (see `src/api/workspace_conductor.py` — JSON file `.ham/workspace_state/conductor.json`).

The v1 API is a **local lift slice**: mission lifecycle (`draft` → `running` → `completed` / `failed`), quick presets, settings, and a **simulated** `POST .../run` worker pass (synthetic output / optional cost bump) — **not** a second orchestrator and **not** a replacement for Cursor’s Cloud Agent execution.

## What “mission control polish” means

**Mission control polish** is the product/documentation bucket for making that surface **clear and honest**: navigation and copy that distinguish **HAM-held mission records and UI** from **upstream Cursor execution**; consistent live status (e.g. managed-missions panel on Conductor vs Operations); settings and empty states that match real API behavior; and small UX fixes that do not change the architecture contract (Hermes supervises; Cursor remains upstream for real agent runs — see `VISION.md` and `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`).

Use this note when naming branches, PRs, or issues so **polish** (IA, copy, panels, accessibility) is not confused with **new orchestration** or **full mission graphs**, which are explicitly out of scope for Conductor v1 unless the roadmap expands.

## Where to read next

| Topic | Doc / code |
|--------|------------|
| Managed Cursor missions vs control plane | `docs/ROADMAP_CLOUD_AGENT_MANAGED_MISSIONS.md`, `docs/CONTROL_PLANE_RUN.md` |
| Conductor API behavior | `src/api/workspace_conductor.py` |
| Workspace UI entry | `frontend/src/features/hermes-workspace/screens/conductor/WorkspaceConductorScreen.tsx` |
| API tests | `tests/test_workspace_conductor.py` |
