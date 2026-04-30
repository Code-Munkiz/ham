# Roadmap: Cloud Agent + managed missions in Ham

This document states **what works today**, what is **stub / partial / explicitly out of scope**, and a **phased roadmap** to close product gaps without collapsing architecture boundaries (Hermes supervises; Cursor remains upstream execution; no second orchestration framework).

**Related:** `GAPS.md`, `VISION.md` (transitional state table), `docs/CONTROL_PLANE_RUN.md` (factual run records vs. mission graph), `docs/MISSION_AWARE_FEED_CONTROLS.md` (feed + controls scoped per `mission_registry_id`).

---

## Live SDK bridge stabilization snapshot (2026-04-30)

- Decision: `SDK_BRIDGE_ENABLED_LIVE`
- Deploy evidence:
  - commit `88e2fd3`
  - revision `ham-api-00067-fgs`
  - service `https://ham-api-vlryahjzwa-uc.a.run.app`
  - env `HAM_CURSOR_SDK_BRIDGE_ENABLED=true`
- Production smoke evidence:
  - mission `eded524a-f6fa-47ea-a51e-d02f9fe79dfb`
  - agent `bc-de421c9e-b067-4bf8-b91d-937505c1b7ac`
  - `/feed` returned `provider_projection.mode=sdk_stream_bridge`, `native_realtime_stream=true`, `status=ok`
  - observed event kinds: `status`, `assistant_message`, `completed`
- Boundaries and fallback:
  - SDK bridge is backend-only (`src/integrations/cursor_sdk_bridge_client.py` + `bridge.mjs`)
  - browser path remains HAM-only (`/api/cursor/managed/missions/{id}/feed`), no direct browser calls to Cursor APIs
  - REST projection fallback remains active when bridge is unavailable/erroring (`provider_projection.mode=rest_projection` with reason)
- Rollback control:
  - set `HAM_CURSOR_SDK_BRIDGE_ENABLED=false` to force REST projection only without changing launch path or frontend flow

---

## 1. What works today (shipped)

| Area | What you get |
|------|----------------|
| **Launch** | `POST /api/cursor/agents/launch` proxies to Cursor; HAM-only fields (`mission_handling`, `uplink_id`, `project_id`) are **not** sent to Cursor. |
| **Poll / read** | Agent GET, conversation, models list — proxied; managed mission row updated on observe (`observe_mission_from_cursor_payload`). |
| **Managed mission record** | File-backed `ManagedMission` per `mission_registry_id`: cursor id, optional `control_plane_ham_run_id`, observed repo/ref, **server-mapped** lifecycle, bounded last-seen deploy/Vercel/post-deploy fields. |
| **Deploy approval snapshot** | `mission_deploy_approval_mode` set **once at managed create** from bound project’s valid `default_deploy_approval_mode` if `project_id` is provided; else `off`. **Not** live-synced to project after create. |
| **Deploy hook / approval API** | Managed deploy-approval status + decisions + hook path (`hard` enforces on server) — see `cursor_managed_deploy*`. |
| **Vercel / post-deploy (bounded)** | Server poll + mapping tiers; post-deploy check — API + future UI surfaces (legacy War Room UI removed Batch 2A). |
| **Control plane runs (separate)** | Durable `ControlPlaneRun` for operator/chat-committed launches + status; **read** APIs — **factual**, not a queue or graph. |
| **Read API: missions** | `GET /api/cursor/managed/missions` (list, optional filter by `cursor_agent_id`) and by `mission_registry_id` — full JSON includes `mission_deploy_approval_mode`. |
| **Mission feed projection** | Persisted `mission_feed_events` are merged on read-path sync from Cursor when a key is available: **optional** `@cursor/sdk` JSONL bridge when `HAM_CURSOR_SDK_BRIDGE_ENABLED=true` (Node on PATH, script at `src/integrations/cursor_sdk_bridge/bridge.mjs`); otherwise **REST** agent status + conversation mapping. Bridge is best-effort; errors fall back to REST. |
| **UI** | **Partial:** managed mission APIs and operator/chat flows remain; dedicated Cloud Agent / War Room panels were removed with legacy workbench (Batch 2A). Re-home mission UX in Hermes Workspace or Command Center as needed. |
| **Project registry** | `ProjectStore` + `PATCH` metadata for `default_deploy_approval_mode` (validated). |

---

## 2. Partial / limitations (not “stub,” but real gaps)

| Limitation | Detail |
|------------|--------|
| **No repo URL → project mapping** | Only optional `project_id` on launch links registry defaults. GitHub URL alone does not resolve a project. |
| **O(n) mission lookup** | `find_by_cursor_agent_id` scans JSON files (documented v1). |
| **Mission row only when new** | `create_mission_after_managed_launch` skips if a row already exists for that agent id (no duplicate). |
| **Managed “review” heuristics** | Server-side rules on polled Cursor payload (`src/ham/cursor_agent_workflow.py` and related) — **not** the same as `HermesReviewer.evaluate()` on bridge runs. Legacy client helpers were removed in Batch 2A. |
| **Hermes ↔ Cursor path** | `HermesReviewer` is strong on **bridge / `main.py`-style** flows; **not** a single automatic closed loop over every Cloud Agent turn. |
| **Chat** | `POST /api/chat` is **not** the Hermes reviewer; system prompt is explicit about that (`chat.py`). |

---

## 3. Stub or explicitly not in v1 (per architecture docs)

| Item | Status |
|------|--------|
| **Mission graph / queue / orchestrator** | **Out of scope** for `ControlPlaneRun` v1 and current managed mission store — see `CONTROL_PLANE_RUN.md`. |
| **Hermes driving next Cursor action** | **Not** implemented as automatic replan + inject; would be new product + policy. |
| **FTS5 / durable critic learning** | **Deferred** (`GAPS.md` #5). |
| **Full LLM session summarization in memory** | **Not started** (`GAPS.md` #4) — string compaction, not true summarization. |

---

## 4. Roadmap (close gaps in order)

Phases are **sequenced**: earlier items unblock honesty and operability; later items deepen “orchestration” only within Hermes/Droid boundary rules.

### Phase A — **Observability & honesty** (near-term, low risk)

- **Shipped:** `GET /api/cursor/managed/missions/{id}/truth` returns a stable JSON truth table (HAM vs Cursor). Hermes Workspace **Live Cloud Agent missions** panel loads this in the mission detail dialog and states HAM vs Cursor in the subtitle.
- **Optional:** Expose full `mission_registry_id` in list rows via tooltip (short id remains primary in dense tables).
- **Tests:** `tests/test_managed_mission.py` covers the truth endpoint.

**Exit:** Operators can answer “what does HAM know vs. what Cursor knows?” without reading source.

### Phase B — **Tighter correlation** (medium)

- **Shipped:** `GET /api/cursor/managed/missions/{id}/correlation` returns join hints and, when `control_plane_ham_run_id` is set, a bounded embed of the linked `ControlPlaneRun` public fields. Workspace mission detail shows the same block.
- **Performance (optional):** Index or small sidecar for `cursor_agent_id → mission_registry_id` if file scan becomes painful.

**Exit:** Less ambiguity between control-plane list and mission list.

### Phase C — **Supervisory value on the Cursor path (bounded)**

- **Shipped:** `POST /api/cursor/managed/missions/{id}/hermes-advisory` runs `HermesReviewer.evaluate()` on **capped** feed-derived text + mission context; persists **advisory-only** fields (`hermes_advisory_*`, `last_review_*` headline) and a feed event. Requires `HAM_MANAGED_MISSION_WRITE_TOKEN` (Bearer). Optional `HAM_MANAGED_MISSION_HERMES_STALE_SECONDS` (default 900) drives UI `hermes_advisory_stale` hint on GET detail.
- **GAPS #1:** Incremental “Hermes-owned routing” that still **defaults execution-heavy** work to Droid, not Cursor-in-HAM for repo mutation — unchanged scope item.

**Exit:** “Managed” includes an explicit operator-triggered Hermes signal path without overwriting provider truth.

### Phase D — **Product E2E (only if product commits)**

- **Shipped (narrow):** Operator-facing **board lane** only — `mission_board_state` ∈ `{backlog, active, archive}` on `ManagedMission`, `PATCH .../board` (token-gated), automatic **active → archive** when server-observed lifecycle hits a terminal mapping (does not move `backlog`). **Not** a mission graph, queue, or orchestrator.
- **Learning persistence (FTS5 or equivalent)** when Hermes wiring is stable (`GAPS.md`) — still deferred.

**Exit:** Lightweight E2E labeling for operators without implying a mission graph substrate.

---

## 5. What we are **not** planning here

- **No** second orchestration framework (per `VISION.md`).
- **No** required `project_id` for launch.
- **No** rewriting legacy mission files on disk for backfill.
- **No** collapsing Cursor’s API into a fake Droid: ambiguous repo execution on **your machine** still defaults to Droid in Ham’s general rules; Cloud Agent remains **upstream** execution in their environment.

---

## 6. Review cadence

When a milestone changes behavior (wiring, tests, or user-visible mission semantics), update `VISION.md` “Current Implementation State” and keep this file aligned or fold completed phases into `GAPS.md` “Completed.”
