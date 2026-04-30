# Roadmap: Cloud Agent + managed missions in Ham

This document states **what works today**, what is **stub / partial / explicitly out of scope**, and a **phased roadmap** to close product gaps without collapsing architecture boundaries (Hermes supervises; Cursor remains upstream execution; no second orchestration framework).

**Related:** `GAPS.md`, `VISION.md` (transitional state table), `docs/CONTROL_PLANE_RUN.md` (factual run records vs. mission graph).

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
| **Read API: missions** | `GET /api/cursor/managed/missions` (list, optional filter by `cursor_agent_id`) and `GET .../missions/{mission_registry_id}` — full JSON includes `mission_deploy_approval_mode`. |
| **Mission feed + controls** | `GET /api/cursor/managed/missions/{mission_registry_id}/feed` (capped event timeline + artifacts); `POST .../messages` (follow-up instruction proxied to Cursor when supported); `POST .../cancel` (cancel request + feed events). `POST /api/cursor/agents/{agent_id}/sync` re-fetches Cursor and returns the persisted `ManagedMission` only. |
| **UI** | **Hermes Workspace:** Operations and Conductor screens include a **Managed missions** live panel (list, detail, feed, sync-by-agent, follow-up, cancel when provider allows). Links open **Workspace chat** with `?mission_id=<mission_registry_id>` so the chat operator stays mission-scoped. Legacy dedicated Cloud Agent / War Room panels were removed with the old workbench (Batch 2A). |
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

- **Docs + UI copy:** One screen-level truth table: *Cursor owns execution* vs *HAM owns record + policy edges* (deploy snapshot is create-time, etc.).
- **Optional:** Expose `mission_registry_id` consistently in Workspace or Command Center when available (reduces “where is my mission?” confusion). **Partial:** Hermes Workspace managed-missions panel + chat deep link `mission_id` are shipped; Command Center parity is still optional.
- **Tests:** Keep mission + API regression tests green when touching cursor routes.

**Exit:** Operators can answer “what does HAM know vs. what Cursor knows?” without reading source.

### Phase B — **Tighter correlation** (medium)

- **ControlPlaneRun ⟷ ManagedMission:** Clearer join story in UI/docs when `control_plane_ham_run_id` is set vs null (UI-only launch).
- **Performance (optional):** Index or small sidecar for `cursor_agent_id → mission_registry_id` if file scan becomes painful.

**Exit:** Less ambiguity between control-plane list and mission list.

### Phase C — **Supervisory value on the Cursor path (bounded)**

- **Hermes:** Optional, explicit hook: e.g. run `HermesReviewer` on **capped** mission artifacts (summary + diffs) on **operator trigger** or **terminal transition**, with results stored as **advisory** fields (not overwriting provider truth). Must align with `CONTROL_PLANE_RUN` separation: judgment ≠ run lifecycle driver by default.
- **GAPS #1:** Incremental “Hermes-owned routing” that still **defaults execution-heavy** work to Droid, not Cursor-in-HAM for repo mutation.

**Exit:** “Managed” means measurably more than polling + heuristics, without faking full orchestration.

### Phase D — **Product E2E (only if product commits)**

- **Mission workspace:** Explicit states (backlog / active / archive), **if** a mission graph is approved — would be **new** substrate; contradicts current “no graph” v1 **unless** spec expands.
- **Learning persistence (FTS5 or equivalent)** when Hermes wiring is stable (`GAPS.md`).

**Exit:** E2E story is **an explicit product decision**, not an accidental accretion.

---

## 5. What we are **not** planning here

- **No** second orchestration framework (per `VISION.md`).
- **No** required `project_id` for launch.
- **No** rewriting legacy mission files on disk for backfill.
- **No** collapsing Cursor’s API into a fake Droid: ambiguous repo execution on **your machine** still defaults to Droid in Ham’s general rules; Cloud Agent remains **upstream** execution in their environment.

---

## 6. Review cadence

When a milestone changes behavior (wiring, tests, or user-visible mission semantics), update `VISION.md` “Current Implementation State” and keep this file aligned or fold completed phases into `GAPS.md` “Completed.”
